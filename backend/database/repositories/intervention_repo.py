"""InterventionRepository — returns plain dicts (not ORM objects)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from backend.database.models import Intervention

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _intervention_to_dict(obj: Intervention) -> dict[str, Any]:
    return {
        "id": str(obj.id) if obj.id else None,
        "lagoon_id": str(obj.lagoon_id) if obj.lagoon_id else None,
        "recommendation_id": str(obj.recommendation_id) if obj.recommendation_id else None,
        "action": obj.action,
        "approved_by": str(obj.approved_by) if obj.approved_by else None,
        "approved_at": obj.approved_at.isoformat() if obj.approved_at else None,
        "implemented_by": str(obj.implemented_by) if obj.implemented_by else None,
        "implemented_at": obj.implemented_at.isoformat() if obj.implemented_at else None,
        "completed_at": obj.completed_at.isoformat() if obj.completed_at else None,
        "observed_outcome": obj.observed_outcome,
        "outcome_confidence": obj.outcome_confidence,
        "notes": obj.notes,
        "status": obj.status,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


class InterventionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, lagoon_id: uuid.UUID, skip: int, limit: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Intervention)
            .where(Intervention.lagoon_id == lagoon_id)
            .order_by(Intervention.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return [_intervention_to_dict(row) for row in result.scalars().all()]

    async def get(self, intervention_id: uuid.UUID, lagoon_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Intervention).where(
                Intervention.id == intervention_id,
                Intervention.lagoon_id == lagoon_id,
            )
        )
        obj = result.scalar_one_or_none()
        return _intervention_to_dict(obj) if obj else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        obj = Intervention(**data)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return _intervention_to_dict(obj)

    async def update(self, intervention_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Intervention).where(Intervention.id == intervention_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return _intervention_to_dict(obj)

    async def complete(self, intervention_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        """Convenience wrapper: set status to completed and apply any additional data."""
        merged = {**data, "status": "completed"}
        return await self.update(intervention_id, merged)
