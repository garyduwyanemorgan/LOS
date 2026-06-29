"""RecommendationRepository — returns plain dicts (not ORM objects)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from backend.database.models import Recommendation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _recommendation_to_dict(obj: Recommendation) -> dict[str, Any]:
    return {
        "id": str(obj.id) if obj.id else None,
        "lagoon_id": str(obj.lagoon_id) if obj.lagoon_id else None,
        "action": obj.action,
        "action_category": obj.action_category,
        "scientific_reason": obj.scientific_reason,
        "contributing_loops": obj.contributing_loops,
        "evidence": obj.evidence,
        "confidence": obj.confidence,
        "priority": obj.priority,
        "expected_outcome": obj.expected_outcome,
        "expected_timeframe_days": obj.expected_timeframe_days,
        "alternative_options": obj.alternative_options,
        "operating_objective_ids": obj.operating_objective_ids,
        "status": obj.status,
        "created_by_system": obj.created_by_system,
        "approved_by": str(obj.approved_by) if obj.approved_by else None,
        "approved_at": obj.approved_at.isoformat() if obj.approved_at else None,
        "rejection_reason": obj.rejection_reason,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


class RecommendationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        lagoon_id: uuid.UUID,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Recommendation)
            .where(Recommendation.lagoon_id == lagoon_id)
            .order_by(Recommendation.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(Recommendation.status == status)
        result = await self._session.execute(stmt)
        return [_recommendation_to_dict(row) for row in result.scalars().all()]

    async def get(self, rec_id: uuid.UUID, lagoon_id: uuid.UUID | None = None) -> dict[str, Any] | None:
        conditions = [Recommendation.id == rec_id]
        if lagoon_id is not None:
            conditions.append(Recommendation.lagoon_id == lagoon_id)
        result = await self._session.execute(select(Recommendation).where(*conditions))
        obj = result.scalar_one_or_none()
        return _recommendation_to_dict(obj) if obj else None

    async def update_status(
        self,
        recommendation_id: uuid.UUID,
        status: str,
        reviewed_by: uuid.UUID,
        notes: str | None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"status": status}
        if status == "approved":
            from datetime import UTC, datetime
            data["approved_by"] = reviewed_by
            data["approved_at"] = datetime.now(UTC)
        elif status == "rejected":
            data["rejection_reason"] = notes
        updated = await self.update(recommendation_id, data)
        if updated is None:
            raise ValueError(f"Recommendation {recommendation_id} not found")
        return updated

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        obj = Recommendation(**data)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return _recommendation_to_dict(obj)

    async def update(self, rec_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Recommendation).where(Recommendation.id == rec_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return _recommendation_to_dict(obj)

    async def approve(
        self, rec_id: uuid.UUID, approved_by: uuid.UUID, approved_at: datetime
    ) -> dict[str, Any] | None:
        return await self.update(
            rec_id,
            {
                "status": "approved",
                "approved_by": approved_by,
                "approved_at": approved_at,
            },
        )

    async def reject(
        self, rec_id: uuid.UUID, rejected_by: uuid.UUID, reason: str
    ) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Recommendation).where(Recommendation.id == rec_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        obj.status = "rejected"
        obj.rejection_reason = reason
        # Store rejected_by in evidence JSONB as there is no dedicated column.
        obj.evidence = {**obj.evidence, "rejected_by": str(rejected_by)}
        await self._session.flush()
        await self._session.refresh(obj)
        return _recommendation_to_dict(obj)
