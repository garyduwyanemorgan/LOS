"""Intervention repository — physical action tracking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from backend.core.exceptions.exceptions import ValidationException
from backend.database.models import Intervention
from backend.database.repositories.base import BaseRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class InterventionRepository(BaseRepository[Intervention]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Intervention, session)

    async def get_active(self, lagoon_id: uuid.UUID) -> list[Intervention]:
        """Return interventions that are currently planned or in-progress."""
        result = await self.session.execute(
            select(Intervention)
            .where(
                Intervention.lagoon_id == lagoon_id,
                Intervention.status.in_(["planned", "in_progress"]),
            )
            .order_by(Intervention.approved_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_recommendation(
        self, recommendation_id: uuid.UUID
    ) -> list[Intervention]:
        """Fetch all interventions linked to a specific recommendation."""
        result = await self.session.execute(
            select(Intervention)
            .where(Intervention.recommendation_id == recommendation_id)
            .order_by(Intervention.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_in_progress(
        self,
        intervention_id: uuid.UUID,
        implemented_by: uuid.UUID,
    ) -> Intervention:
        """Transition an intervention from planned → in_progress."""
        intervention = await self.get_by_id_or_raise(intervention_id)
        if intervention.status != "planned":
            raise ValidationException(
                message="Intervention must be in 'planned' state to start.",
                detail={"current_status": intervention.status},
            )
        return await self.update(  # type: ignore[return-value]
            intervention_id,
            {
                "status": "in_progress",
                "implemented_by": implemented_by,
                "implemented_at": datetime.now(tz=UTC),
            },
        )

    async def complete(
        self,
        intervention_id: uuid.UUID,
        observed_outcome: str,
        outcome_confidence: float,
        notes: str | None = None,
    ) -> Intervention:
        """Mark an intervention as completed with its observed outcome."""
        intervention = await self.get_by_id_or_raise(intervention_id)
        if intervention.status not in ("planned", "in_progress"):
            raise ValidationException(
                message="Intervention must be planned or in_progress to complete.",
                detail={"current_status": intervention.status},
            )
        return await self.update(  # type: ignore[return-value]
            intervention_id,
            {
                "status": "completed",
                "completed_at": datetime.now(tz=UTC),
                "observed_outcome": observed_outcome,
                "outcome_confidence": outcome_confidence,
                "notes": notes,
            },
        )

    async def get_completed_with_outcomes(
        self, lagoon_id: uuid.UUID, days: int = 90
    ) -> list[Intervention]:
        """Fetch completed interventions with outcome data for learning cycles."""
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(Intervention)
            .where(
                Intervention.lagoon_id == lagoon_id,
                Intervention.status == "completed",
                Intervention.completed_at >= cutoff,
                Intervention.observed_outcome.isnot(None),
            )
            .order_by(Intervention.completed_at.desc())
        )
        return list(result.scalars().all())

    async def get_outcome_summary(
        self, lagoon_id: uuid.UUID, days: int = 90
    ) -> dict[str, int]:
        """Count interventions by status for a lagoon over a time window."""
        from sqlalchemy import func

        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(Intervention.status, func.count(Intervention.id).label("n"))
            .where(Intervention.lagoon_id == lagoon_id, Intervention.created_at >= cutoff)
            .group_by(Intervention.status)
        )
        return {row.status: row.n for row in result.all()}
