"""Application service for lagoon management.

Thin orchestration layer: validates inputs, delegates to repositories,
publishes domain events, reads current state from shared memory.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


# ── Repository protocol (implemented by database.repositories) ──────────────

class LagoonRepository(Protocol):
    async def get(self, lagoon_id: UUID, org_id: UUID) -> dict[str, Any] | None: ...
    async def list(self, org_id: UUID, skip: int, limit: int) -> list[dict[str, Any]]: ...
    async def create(self, data: dict[str, Any]) -> dict[str, Any]: ...
    async def update(self, lagoon_id: UUID, data: dict[str, Any]) -> dict[str, Any]: ...
    async def get_objectives(self, lagoon_id: UUID) -> list[dict[str, Any]]: ...
    async def set_objectives(self, lagoon_id: UUID, objectives: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    async def get_performance_history(self, lagoon_id: UUID, days: int) -> list[dict[str, Any]]: ...


class EventBus(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class SharedMemory(Protocol):
    async def get_loop_states(self, lagoon_id: UUID) -> dict[str, Any]: ...
    async def get_recent_events(self, lagoon_id: UUID, limit: int) -> list[dict[str, Any]]: ...
    async def get_confidence_scores(self, lagoon_id: UUID) -> dict[str, float]: ...


# ── Service ─────────────────────────────────────────────────────────────────

class LagoonService:
    """Orchestrates all lagoon-related business operations."""

    def __init__(
        self,
        lagoon_repo: LagoonRepository,
        event_bus: EventBus,
        shared_memory: SharedMemory,
    ) -> None:
        self._repo = lagoon_repo
        self._bus = event_bus
        self._memory = shared_memory

    # ── Queries ──────────────────────────────────────────────────────────────

    async def get_lagoon(self, lagoon_id: UUID, org_id: UUID) -> dict[str, Any]:
        """Return a single lagoon scoped to the organisation.

        Raises ValueError if not found or org mismatch.
        """
        lagoon = await self._repo.get(lagoon_id, org_id)
        if lagoon is None:
            raise ValueError(f"Lagoon {lagoon_id} not found in organisation {org_id}")
        logger.debug("get_lagoon %s org=%s", lagoon_id, org_id)
        return lagoon

    async def list_lagoons(
        self,
        org_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return paginated lagoons for an organisation."""
        if limit > 500:
            limit = 500
        lagoons = await self._repo.list(org_id, skip, limit)
        logger.debug("list_lagoons org=%s count=%d", org_id, len(lagoons))
        return lagoons

    async def get_lagoon_status(self, lagoon_id: UUID, org_id: UUID) -> dict[str, Any]:
        """Return complete system state snapshot for a lagoon.

        Combines: all scientific loop states, confidence scores,
        recent events, and current operating objectives.
        """
        # Verify access first
        lagoon = await self.get_lagoon(lagoon_id, org_id)

        loop_states, recent_events, confidence = await _gather(
            self._memory.get_loop_states(lagoon_id),
            self._memory.get_recent_events(lagoon_id, limit=20),
            self._memory.get_confidence_scores(lagoon_id),
        )

        objectives = await self._repo.get_objectives(lagoon_id)

        return {
            "lagoon_id": str(lagoon_id),
            "lagoon_name": lagoon.get("name"),
            "timestamp": datetime.now(UTC).isoformat(),
            "loop_states": loop_states,
            "confidence_scores": confidence,
            "overall_confidence": _compute_overall_confidence(confidence),
            "recent_events": recent_events,
            "objectives": objectives,
            "operational_mode": lagoon.get("operational_mode", "normal"),
            "alert_level": _determine_alert_level(loop_states, confidence),
        }

    async def get_performance_history(
        self,
        lagoon_id: UUID,
        days: int = 30,
    ) -> dict[str, Any]:
        """Return performance metrics time series for the requested period."""
        if days > 365:
            days = 365
        records = await self._repo.get_performance_history(lagoon_id, days)
        return {
            "lagoon_id": str(lagoon_id),
            "period_days": days,
            "record_count": len(records),
            "records": records,
        }

    # ── Commands ─────────────────────────────────────────────────────────────

    async def create_lagoon(
        self,
        data: dict[str, Any],
        org_id: UUID,
        created_by: UUID,
    ) -> dict[str, Any]:
        """Create a new lagoon record and publish a creation event."""
        _validate_lagoon_data(data)

        lagoon_id = uuid4()
        record = {
            **data,
            "id": str(lagoon_id),
            "org_id": str(org_id),
            "created_by": str(created_by),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "is_active": True,
            "operational_mode": data.get("operational_mode", "normal"),
        }

        created = await self._repo.create(record)

        await self._bus.publish(
            "lagoon.created",
            {
                "lagoon_id": str(lagoon_id),
                "org_id": str(org_id),
                "created_by": str(created_by),
                "name": data.get("name"),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        logger.info("Lagoon created id=%s org=%s user=%s", lagoon_id, org_id, created_by)
        return created

    async def update_lagoon(
        self,
        lagoon_id: UUID,
        data: dict[str, Any],
        org_id: UUID,
    ) -> dict[str, Any]:
        """Update lagoon fields. Verifies org ownership before write."""
        # Verify existence and ownership
        await self.get_lagoon(lagoon_id, org_id)

        _validate_lagoon_data(data, partial=True)
        data["updated_at"] = datetime.now(UTC).isoformat()

        updated = await self._repo.update(lagoon_id, data)

        await self._bus.publish(
            "lagoon.updated",
            {
                "lagoon_id": str(lagoon_id),
                "org_id": str(org_id),
                "fields": list(data.keys()),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        logger.info("Lagoon updated id=%s org=%s", lagoon_id, org_id)
        return updated

    async def update_operating_objectives(
        self,
        lagoon_id: UUID,
        objectives: list[dict[str, Any]],
        org_id: UUID,
    ) -> list[dict[str, Any]]:
        """Replace all operating objectives for a lagoon."""
        await self.get_lagoon(lagoon_id, org_id)

        _validate_objectives(objectives)

        saved = await self._repo.set_objectives(lagoon_id, objectives)

        await self._bus.publish(
            "lagoon.objectives_updated",
            {
                "lagoon_id": str(lagoon_id),
                "org_id": str(org_id),
                "objective_count": len(objectives),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        logger.info("Operating objectives updated lagoon=%s count=%d", lagoon_id, len(objectives))
        return saved


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _gather(*coros):  # type: ignore[no-untyped-def]
    """Run coroutines concurrently and return results as a tuple."""
    import asyncio
    return await asyncio.gather(*coros)


def _compute_overall_confidence(confidence: dict[str, float]) -> float:
    """Geometric mean of loop confidence scores."""
    import math
    scores = [v for v in confidence.values() if isinstance(v, (int, float)) and 0 <= v <= 1]
    if not scores:
        return 0.0
    log_sum = sum(math.log(max(s, 1e-9)) for s in scores)
    return round(math.exp(log_sum / len(scores)), 3)


def _determine_alert_level(
    loop_states: dict[str, Any],
    confidence: dict[str, float],
) -> str:
    """Derive a single alert level from loop states and confidence scores.

    Returns: 'normal' | 'advisory' | 'warning' | 'critical'
    """
    min_confidence = min(confidence.values(), default=1.0)
    any_critical = any(
        s.get("alert_level") == "critical"
        for s in loop_states.values()
        if isinstance(s, dict)
    )
    any_warning = any(
        s.get("alert_level") in ("warning", "critical")
        for s in loop_states.values()
        if isinstance(s, dict)
    )

    if any_critical or min_confidence < 0.2:
        return "critical"
    if any_warning or min_confidence < 0.5:
        return "warning"
    if min_confidence < 0.7:
        return "advisory"
    return "normal"


def _validate_lagoon_data(data: dict[str, Any], partial: bool = False) -> None:
    """Raise ValueError for invalid lagoon fields."""
    if not partial:
        required = {"name", "surface_area_m2", "volume_m3", "latitude", "longitude"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

    if "surface_area_m2" in data and data["surface_area_m2"] <= 0:
        raise ValueError("surface_area_m2 must be positive")
    if "volume_m3" in data and data["volume_m3"] <= 0:
        raise ValueError("volume_m3 must be positive")
    if "latitude" in data and not -90 <= data["latitude"] <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if "longitude" in data and not -180 <= data["longitude"] <= 180:
        raise ValueError("longitude must be between -180 and 180")


def _validate_objectives(objectives: list[dict[str, Any]]) -> None:
    """Raise ValueError for invalid objective definitions."""
    valid_types = {"water_quality", "ecological", "infrastructure", "compliance", "operational"}
    for i, obj in enumerate(objectives):
        if "parameter" not in obj:
            raise ValueError(f"Objective {i}: missing 'parameter'")
        if "target" not in obj:
            raise ValueError(f"Objective {i}: missing 'target'")
        if "objective_type" in obj and obj["objective_type"] not in valid_types:
            raise ValueError(f"Objective {i}: unknown type '{obj['objective_type']}'")
