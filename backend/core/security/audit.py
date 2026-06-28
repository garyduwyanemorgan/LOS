"""Audit logging — writes immutable records to the audit_log table."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from backend.core.config.settings import settings
from backend.core.logging.logger import get_logger

log = get_logger(__name__)

# Raw asyncpg connection for fire-and-forget audit writes.
# We use asyncpg directly (not SQLAlchemy) so that audit writes are isolated
# from the application's ORM transaction and cannot be rolled back if the
# business transaction fails.

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # Convert asyncpg URL format: strip +asyncpg driver prefix if present
        url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        _pool = await asyncpg.create_pool(
            dsn=url,
            min_size=1,
            max_size=5,
            command_timeout=10,
        )
    return _pool


class AuditLogger:
    """Write structured audit events to the audit_log table.

    Each method corresponds to a category of auditable action.
    All writes are best-effort: failures are logged but never re-raised
    so that audit logging cannot break business operations.
    """

    async def _write(self, record: dict[str, Any]) -> None:
        """Insert a single audit record, silently absorbing errors."""
        try:
            pool = await _get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO audit_log (
                        id, user_id, action, resource_type, resource_id,
                        changes, ip_address, user_agent, timestamp
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    record["id"],
                    record.get("user_id"),
                    record["action"],
                    record.get("resource_type"),
                    record.get("resource_id"),
                    json.dumps(record.get("changes", {})),
                    record.get("ip_address"),
                    record.get("user_agent"),
                    record.get("timestamp", datetime.now(tz=UTC)),
                )
        except Exception as exc:
            # Never raise — audit logging must not disrupt business logic.
            log.error(
                "audit-write-failed",
                error=str(exc),
                action=record.get("action"),
                user_id=str(record.get("user_id")),
            )

    async def log_action(
        self,
        user_id: str | uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: str | uuid.UUID | None = None,
        changes: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Write a generic audit record.

        Args:
            user_id: UUID of the acting user.
            action: Machine-readable action string (e.g. "recommendation.approved").
            resource_type: Name of the entity type (e.g. "Recommendation").
            resource_id: UUID of the specific resource.
            changes: Snapshot of what changed; typically {"before": ..., "after": ...}.
            ip_address: Client IP from the request.
            user_agent: Client User-Agent header.
        """
        await self._write(
            {
                "id": uuid.uuid4(),
                "user_id": str(user_id) if user_id else None,
                "action": action,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "changes": changes or {},
                "ip_address": ip_address,
                "user_agent": user_agent,
                "timestamp": datetime.now(tz=UTC),
            }
        )

    async def log_login(
        self,
        user_id: str | uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
        success: bool = True,
    ) -> None:
        """Record a login attempt."""
        await self.log_action(
            user_id=user_id,
            action="auth.login.success" if success else "auth.login.failed",
            resource_type="User",
            resource_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_recommendation_decision(
        self,
        user_id: str | uuid.UUID,
        recommendation_id: str | uuid.UUID,
        decision: str,  # "approved" | "rejected"
        reason: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Record an approval or rejection of a recommendation."""
        await self.log_action(
            user_id=user_id,
            action=f"recommendation.{decision}",
            resource_type="Recommendation",
            resource_id=recommendation_id,
            changes={"decision": decision, "reason": reason},
            ip_address=ip_address,
        )

    async def log_simulation_run(
        self,
        user_id: str | uuid.UUID,
        model_run_id: str | uuid.UUID,
        model_name: str,
        lagoon_id: str | uuid.UUID,
        status: str,
    ) -> None:
        """Record a simulation run trigger."""
        await self.log_action(
            user_id=user_id,
            action=f"simulation.{status}",
            resource_type="ScientificModelRun",
            resource_id=model_run_id,
            changes={"model_name": model_name, "lagoon_id": str(lagoon_id)},
        )

    async def log_data_export(
        self,
        user_id: str | uuid.UUID,
        resource_type: str,
        filters: dict[str, Any],
        ip_address: str | None = None,
    ) -> None:
        """Record a data export event."""
        await self.log_action(
            user_id=user_id,
            action="data.export",
            resource_type=resource_type,
            changes={"filters": filters},
            ip_address=ip_address,
        )


# Module-level singleton.
audit_logger = AuditLogger()
