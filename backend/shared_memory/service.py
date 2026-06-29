"""
Shared Memory Service — operational memory of the Lagoons Operating System.

Uses Redis for short-term and working memory (fast, ephemeral).
Uses PostgreSQL for long-term, scientific and operational memory (persistent).

The database (raw facts) and shared memory (interpreted experience) are
intentionally separate: the database remembers what happened, shared memory
remembers what it means.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Redis key prefixes
_PREFIX_SHORT = "los:mem:short"
_PREFIX_WORKING = "los:mem:working"
_PREFIX_SCIENTIFIC = "los:mem:sci"

# Default TTLs
DEFAULT_SHORT_TTL_S = 3_600          # 1 hour
DEFAULT_WORKING_TTL_S = 7_200        # 2 hours (hypothesis working set)
DEFAULT_SCIENTIFIC_TTL_S = 3_600 * 6  # 6 hours


class SharedMemoryService:
    """
    Operational memory for the Lagoons Operating System.

    Memory hierarchy:
    ┌──────────────────────────────────────────────────────┐
    │ Short-Term  │ Redis, TTL=1h   │ Current state        │
    │ Working     │ Redis, TTL=2h   │ Active hypotheses    │
    │ Scientific  │ Redis, TTL=6h   │ Per-loop state       │
    │ Long-Term   │ PostgreSQL      │ Persistent knowledge │
    │ Operational │ PostgreSQL      │ Intervention history │
    │ Learning    │ PostgreSQL      │ Outcome records      │
    └──────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_session: AsyncSession | None = None,
    ) -> None:
        self._redis = redis_client
        self._db = db_session

    # ──────────────────────────────────────────────────────────────────────
    # Short-Term Memory (Redis)
    # ──────────────────────────────────────────────────────────────────────

    async def store_short_term(
        self,
        lagoon_id: UUID,
        key: str,
        value: Any,
        ttl_seconds: int = DEFAULT_SHORT_TTL_S,
    ) -> None:
        """Store a value in short-term memory with automatic expiry."""
        redis_key = f"{_PREFIX_SHORT}:{lagoon_id}:{key}"
        serialised = json.dumps(value, default=str)
        await self._redis.setex(redis_key, ttl_seconds, serialised)

    async def get_short_term(self, lagoon_id: UUID, key: str) -> Any | None:
        """Retrieve a value from short-term memory. Returns None if expired."""
        redis_key = f"{_PREFIX_SHORT}:{lagoon_id}:{key}"
        raw = await self._redis.get(redis_key)
        if raw is None:
            return None
        return json.loads(raw)

    async def delete_short_term(self, lagoon_id: UUID, key: str) -> None:
        """Delete a short-term memory entry."""
        await self._redis.delete(f"{_PREFIX_SHORT}:{lagoon_id}:{key}")

    # ──────────────────────────────────────────────────────────────────────
    # Working Memory (Redis) — for active hypothesis evaluation
    # ──────────────────────────────────────────────────────────────────────

    async def store_working_memory(
        self,
        lagoon_id: UUID,
        hypothesis_id: str,
        data: dict[str, Any],
        ttl_seconds: int = DEFAULT_WORKING_TTL_S,
    ) -> None:
        """Store hypothesis or reasoning context in working memory."""
        redis_key = f"{_PREFIX_WORKING}:{lagoon_id}:{hypothesis_id}"
        await self._redis.setex(redis_key, ttl_seconds, json.dumps(data, default=str))

    async def get_working_memory(self, lagoon_id: UUID) -> dict[str, Any]:
        """Retrieve all active working memory entries for a lagoon."""
        pattern = f"{_PREFIX_WORKING}:{lagoon_id}:*"
        keys = await self._redis.keys(pattern)
        result: dict[str, Any] = {}
        for key in keys:
            raw = await self._redis.get(key)
            if raw:
                hypothesis_id = key.split(":")[-1]
                result[hypothesis_id] = json.loads(raw)
        return result

    async def clear_working_memory(self, lagoon_id: UUID) -> None:
        """Clear all working memory for a lagoon (e.g. after reasoning cycle)."""
        pattern = f"{_PREFIX_WORKING}:{lagoon_id}:*"
        keys = await self._redis.keys(pattern)
        if keys:
            await self._redis.delete(*keys)

    # ──────────────────────────────────────────────────────────────────────
    # Scientific Memory (Redis) — per-loop current states
    # ──────────────────────────────────────────────────────────────────────

    async def store_scientific_memory(
        self,
        lagoon_id: UUID,
        loop: str,
        key: str,
        value: Any,
        ttl_seconds: int = DEFAULT_SCIENTIFIC_TTL_S,
    ) -> None:
        """Store the current state of a scientific loop."""
        redis_key = f"{_PREFIX_SCIENTIFIC}:{lagoon_id}:{loop}:{key}"
        await self._redis.setex(redis_key, ttl_seconds, json.dumps(value, default=str))

    async def get_scientific_memory(
        self,
        lagoon_id: UUID,
        loop: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve scientific memory.

        If loop is None, returns all loops.
        If loop is specified, returns only that loop's memory.
        """
        if loop:
            pattern = f"{_PREFIX_SCIENTIFIC}:{lagoon_id}:{loop}:*"
        else:
            pattern = f"{_PREFIX_SCIENTIFIC}:{lagoon_id}:*"

        keys = await self._redis.keys(pattern)
        result: dict[str, Any] = {}
        for key in keys:
            raw = await self._redis.get(key)
            if raw:
                # Key format: los:mem:sci:{lagoon_id}:{loop}:{key}
                parts = key.split(":")
                sub_key = ":".join(parts[5:])  # everything after lagoon_id and loop
                loop_name = parts[4] if len(parts) > 4 else "unknown"
                if loop_name not in result:
                    result[loop_name] = {}
                result[loop_name][sub_key] = json.loads(raw)
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Long-Term Memory (PostgreSQL)
    # ──────────────────────────────────────────────────────────────────────

    async def store_long_term(
        self,
        lagoon_id: UUID,
        memory_type: str,
        key: str,
        value: dict[str, Any],
        loop: str | None = None,
    ) -> None:
        """
        Persist a long-term memory entry to the database.

        Uses UPSERT to handle repeated updates gracefully.
        Increments version on each update.
        """
        if self._db is None:
            logger.warning("Long-term memory: no database session available")
            return

        from sqlalchemy import text
        query = text(
            """
            INSERT INTO shared_memory_entries
                (id, lagoon_id, memory_type, loop, key, value, version, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :lagoon_id, :memory_type, :loop, :key, :value::jsonb, 1,
                 NOW(), NOW())
            ON CONFLICT (lagoon_id, memory_type, key) DO UPDATE
            SET
                value = EXCLUDED.value,
                loop = EXCLUDED.loop,
                version = shared_memory_entries.version + 1,
                updated_at = NOW()
            """
        )
        await self._db.execute(
            query,
            {
                "lagoon_id": str(lagoon_id),
                "memory_type": memory_type,
                "loop": loop,
                "key": key,
                "value": json.dumps(value, default=str),
            },
        )
        await self._db.commit()

    async def get_long_term(
        self,
        lagoon_id: UUID,
        memory_type: str,
        key: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve long-term memory from the database."""
        if self._db is None:
            return {}

        from sqlalchemy import text
        if key:
            query = text(
                "SELECT key, value FROM shared_memory_entries "
                "WHERE lagoon_id = :lagoon_id AND memory_type = :memory_type AND key = :key"
            )
            result = await self._db.execute(
                query,
                {"lagoon_id": str(lagoon_id), "memory_type": memory_type, "key": key},
            )
            rows = result.fetchall()
        else:
            query = text(
                "SELECT key, value FROM shared_memory_entries "
                "WHERE lagoon_id = :lagoon_id AND memory_type = :memory_type"
            )
            result = await self._db.execute(
                query,
                {"lagoon_id": str(lagoon_id), "memory_type": memory_type},
            )
            rows = result.fetchall()

        return {row[0]: row[1] for row in rows}

    # ──────────────────────────────────────────────────────────────────────
    # Learning Memory (PostgreSQL)
    # ──────────────────────────────────────────────────────────────────────

    async def record_learning(
        self,
        lagoon_id: UUID,
        recommendation_id: UUID,
        predicted_outcome: str,
        actual_outcome: str,
        confidence_delta: float,
        success: bool,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Record the outcome of an intervention for continuous learning."""
        value = {
            "recommendation_id": str(recommendation_id),
            "predicted_outcome": predicted_outcome,
            "actual_outcome": actual_outcome,
            "confidence_delta": confidence_delta,
            "success": success,
            "evidence": evidence or {},
            "recorded_at": datetime.now(tz=UTC).isoformat(),
        }
        key = f"learning:{recommendation_id}"
        await self.store_long_term(lagoon_id, "learning", key, value)

    async def get_learning_history(
        self,
        lagoon_id: UUID,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Retrieve learning records for the past N days."""
        if self._db is None:
            return []

        from sqlalchemy import text
        query = text(
            """
            SELECT key, value, updated_at
            FROM shared_memory_entries
            WHERE lagoon_id = :lagoon_id
              AND memory_type = 'learning'
              AND updated_at >= NOW() - INTERVAL ':days days'
            ORDER BY updated_at DESC
            LIMIT 500
            """
        )
        try:
            result = await self._db.execute(
                query, {"lagoon_id": str(lagoon_id), "days": days}
            )
            rows = result.fetchall()
            return [{"key": row[0], **row[1], "updated_at": str(row[2])} for row in rows]
        except Exception as exc:
            logger.error("get_learning_history failed: %s", exc)
            return []

    # ──────────────────────────────────────────────────────────────────────
    # Lagoon Summary — all memory types combined
    # ──────────────────────────────────────────────────────────────────────

    async def get_lagoon_summary(self, lagoon_id: UUID) -> dict[str, Any]:
        """Return a comprehensive summary of all memory for a lagoon."""
        summary: dict[str, Any] = {}

        # Scientific loop states
        summary["scientific_memory"] = await self.get_scientific_memory(lagoon_id)

        # Working hypotheses
        summary["working_memory"] = await self.get_working_memory(lagoon_id)

        # Recent system state
        summary["current_state"] = await self.get_short_term(lagoon_id, "system_state") or {}

        # Recent recommendations context
        summary["recent_recommendations"] = (
            await self.get_short_term(lagoon_id, "recent_recommendations") or []
        )

        return summary

    # ──────────────────────────────────────────────────────────────────────
    # Protocol-compatible methods for lagoon_service.SharedMemory
    # ──────────────────────────────────────────────────────────────────────

    async def get_loop_states(self, lagoon_id: "UUID") -> dict[str, Any]:
        """Return per-loop states from scientific memory (empty if not yet populated)."""
        try:
            return await self.get_scientific_memory(lagoon_id) or {}
        except Exception:
            return {}

    async def get_recent_events(self, lagoon_id: "UUID", limit: int = 20) -> list[dict[str, Any]]:
        """Return recent events from short-term memory (empty if not yet populated)."""
        try:
            events = await self.get_short_term(lagoon_id, "recent_events")
            if isinstance(events, list):
                return events[:limit]
        except Exception:
            pass
        return []

    async def get_confidence_scores(self, lagoon_id: "UUID") -> dict[str, float]:
        """Return per-loop confidence scores from short-term memory."""
        try:
            scores = await self.get_short_term(lagoon_id, "confidence_scores")
            if isinstance(scores, dict):
                return {k: float(v) for k, v in scores.items()}
        except Exception:
            pass
        return {}
