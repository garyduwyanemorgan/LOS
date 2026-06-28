"""Event repository — queries over the LOS event ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from backend.database.models import LOSEvent
from backend.database.repositories.base import BaseRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class EventRepository(BaseRepository[LOSEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(LOSEvent, session)

    async def get_by_correlation_id(
        self, correlation_id: uuid.UUID, limit: int = 100
    ) -> list[LOSEvent]:
        """Fetch all events sharing a correlation ID (same causal chain)."""
        result = await self.session.execute(
            select(LOSEvent)
            .where(LOSEvent.correlation_id == correlation_id)
            .order_by(LOSEvent.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_loop(
        self,
        lagoon_id: uuid.UUID,
        loop: str,
        hours: int = 24,
        limit: int = 500,
    ) -> list[LOSEvent]:
        """Fetch recent events from a specific scientific loop."""
        cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
        result = await self.session.execute(
            select(LOSEvent)
            .where(
                LOSEvent.lagoon_id == lagoon_id,
                LOSEvent.loop == loop,
                LOSEvent.created_at >= cutoff,
            )
            .order_by(LOSEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent(
        self,
        lagoon_id: uuid.UUID,
        hours: int = 24,
        priority: str | None = None,
        event_type: str | None = None,
        limit: int = 200,
    ) -> list[LOSEvent]:
        """Fetch recent events for a lagoon with optional filters."""
        cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
        stmt = select(LOSEvent).where(
            LOSEvent.lagoon_id == lagoon_id,
            LOSEvent.created_at >= cutoff,
        )

        if priority:
            stmt = stmt.where(LOSEvent.priority == priority)
        if event_type:
            stmt = stmt.where(LOSEvent.event_type == event_type)

        stmt = stmt.order_by(LOSEvent.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_critical_events(
        self, lagoon_id: uuid.UUID, hours: int = 6
    ) -> list[LOSEvent]:
        """Fetch critical-priority events from the last N hours."""
        return await self.get_recent(lagoon_id, hours=hours, priority="critical")

    async def get_event_type_counts(
        self, lagoon_id: uuid.UUID, hours: int = 24
    ) -> dict[str, int]:
        """Count events grouped by event_type over the last N hours."""
        from sqlalchemy import func

        cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
        result = await self.session.execute(
            select(LOSEvent.event_type, func.count(LOSEvent.id).label("n"))
            .where(LOSEvent.lagoon_id == lagoon_id, LOSEvent.created_at >= cutoff)
            .group_by(LOSEvent.event_type)
            .order_by(func.count(LOSEvent.id).desc())
        )
        return {row.event_type: row.n for row in result.all()}

    async def get_for_replay(
        self,
        lagoon_id: uuid.UUID,
        start: datetime,
        end: datetime,
        loop: str | None = None,
    ) -> list[LOSEvent]:
        """Fetch events in chronological order for event replay / audit."""
        stmt = select(LOSEvent).where(
            LOSEvent.lagoon_id == lagoon_id,
            LOSEvent.created_at >= start,
            LOSEvent.created_at <= end,
        )
        if loop:
            stmt = stmt.where(LOSEvent.loop == loop)
        stmt = stmt.order_by(LOSEvent.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
