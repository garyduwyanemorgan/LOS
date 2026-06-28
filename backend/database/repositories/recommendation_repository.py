"""Recommendation repository — decision engine recommendation management."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from backend.core.exceptions.exceptions import ValidationException
from backend.database.models import Recommendation
from backend.database.repositories.base import BaseRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class RecommendationRepository(BaseRepository[Recommendation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Recommendation, session)

    async def get_pending(
        self,
        lagoon_id: uuid.UUID,
        priority: str | None = None,
        limit: int = 50,
    ) -> list[Recommendation]:
        """Fetch pending recommendations awaiting human review."""
        stmt = select(Recommendation).where(
            Recommendation.lagoon_id == lagoon_id,
            Recommendation.status == "pending",
        )
        if priority:
            stmt = stmt.where(Recommendation.priority == priority)

        # Order: critical first, then by confidence, then newest first.
        stmt = stmt.order_by(
            Recommendation.priority.asc(),  # critical < high < normal < low alphabetically — handled below
            Recommendation.confidence.desc(),
            Recommendation.created_at.desc(),
        ).limit(limit)

        result = await self.session.execute(stmt)
        recs = list(result.scalars().all())

        # Sort by priority severity (alphabetical ordering is wrong for priority).
        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        recs.sort(key=lambda r: (priority_order.get(r.priority, 9), -r.confidence))
        return recs

    async def get_by_status(
        self,
        lagoon_id: uuid.UUID,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Recommendation]:
        """Fetch recommendations filtered by status."""
        result = await self.session.execute(
            select(Recommendation)
            .where(Recommendation.lagoon_id == lagoon_id, Recommendation.status == status)
            .order_by(Recommendation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def approve(
        self,
        recommendation_id: uuid.UUID,
        approved_by_user_id: uuid.UUID,
    ) -> Recommendation:
        """Mark a recommendation as approved.

        Raises:
            ResourceNotFoundException: if the recommendation does not exist.
            ValidationException: if the recommendation is not in 'pending' state.
        """
        rec = await self.get_by_id_or_raise(recommendation_id)

        if rec.status != "pending":
            raise ValidationException(
                message=f"Recommendation cannot be approved: current status is '{rec.status}'.",
                detail={"current_status": rec.status, "required_status": "pending"},
            )

        return await self.update(
            recommendation_id,
            {
                "status": "approved",
                "approved_by": approved_by_user_id,
                "approved_at": datetime.now(tz=UTC),
            },
        )  # type: ignore[return-value]

    async def reject(
        self,
        recommendation_id: uuid.UUID,
        rejected_by_user_id: uuid.UUID,
        reason: str,
    ) -> Recommendation:
        """Mark a recommendation as rejected with a reason.

        Raises:
            ResourceNotFoundException: if the recommendation does not exist.
            ValidationException: if the recommendation is not in 'pending' state.
        """
        rec = await self.get_by_id_or_raise(recommendation_id)

        if rec.status != "pending":
            raise ValidationException(
                message=f"Recommendation cannot be rejected: current status is '{rec.status}'.",
                detail={"current_status": rec.status, "required_status": "pending"},
            )

        return await self.update(
            recommendation_id,
            {
                "status": "rejected",
                "rejection_reason": reason,
                "approved_by": rejected_by_user_id,
                "approved_at": datetime.now(tz=UTC),
            },
        )  # type: ignore[return-value]

    async def mark_implemented(self, recommendation_id: uuid.UUID) -> Recommendation:
        """Transition an approved recommendation to 'implemented'."""
        rec = await self.get_by_id_or_raise(recommendation_id)
        if rec.status != "approved":
            raise ValidationException(
                message="Only approved recommendations can be marked as implemented.",
                detail={"current_status": rec.status},
            )
        return await self.update(recommendation_id, {"status": "implemented"})  # type: ignore[return-value]

    async def supersede_older(
        self, lagoon_id: uuid.UUID, action_category: str
    ) -> int:
        """Mark all pending recommendations of the same category as superseded.

        Called when the decision engine generates a fresh recommendation for
        the same category, making older ones obsolete.
        Returns the number of superseded records.
        """
        pending = await self.get_by_status(lagoon_id, "pending")
        count = 0
        for rec in pending:
            if rec.action_category == action_category:
                await self.update(rec.id, {"status": "superseded"})
                count += 1
        return count

    async def get_high_confidence(
        self, lagoon_id: uuid.UUID, min_confidence: float = 0.8, limit: int = 20
    ) -> list[Recommendation]:
        """Fetch pending recommendations above a confidence threshold."""
        result = await self.session.execute(
            select(Recommendation)
            .where(
                Recommendation.lagoon_id == lagoon_id,
                Recommendation.status == "pending",
                Recommendation.confidence >= min_confidence,
            )
            .order_by(Recommendation.confidence.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
