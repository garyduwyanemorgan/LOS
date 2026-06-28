"""EventRepository — returns plain dicts (not ORM objects)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from backend.database.models import LOSEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _event_to_dict(obj: LOSEvent) -> dict[str, Any]:
    return {
        "id": str(obj.id) if obj.id else None,
        "lagoon_id": str(obj.lagoon_id) if obj.lagoon_id else None,
        "event_type": obj.event_type,
        "loop": obj.loop,
        "source": obj.source,
        "priority": obj.priority,
        "severity": obj.priority,  # alias for router compatibility
        "confidence": obj.confidence,
        "payload": obj.payload,
        "correlation_id": str(obj.correlation_id) if obj.correlation_id else None,
        "version": obj.version,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
    }


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        lagoon_id: uuid.UUID,
        skip: int,
        limit: int,
        severity: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(LOSEvent)
            .where(LOSEvent.lagoon_id == lagoon_id)
            .order_by(LOSEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        # severity maps to the priority column in the model
        if severity is not None:
            stmt = stmt.where(LOSEvent.priority == severity)
        if event_type is not None:
            stmt = stmt.where(LOSEvent.event_type == event_type)
        if since is not None:
            stmt = stmt.where(LOSEvent.created_at >= since)

        result = await self._session.execute(stmt)
        return [_event_to_dict(row) for row in result.scalars().all()]

    async def get(self, event_id: uuid.UUID, lagoon_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(LOSEvent).where(LOSEvent.id == event_id, LOSEvent.lagoon_id == lagoon_id)
        )
        obj = result.scalar_one_or_none()
        return _event_to_dict(obj) if obj else None

    async def acknowledge(
        self,
        event_id: uuid.UUID,
        acknowledged_by: uuid.UUID,
        acknowledged_at: datetime,
    ) -> dict[str, Any]:
        result = await self._session.execute(
            select(LOSEvent).where(LOSEvent.id == event_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return {}
        new_payload = {
            **obj.payload,
            "acknowledged_by": str(acknowledged_by),
            "acknowledged_at": acknowledged_at.isoformat(),
        }
        obj.payload = new_payload
        await self._session.flush()
        await self._session.refresh(obj)
        return _event_to_dict(obj)
