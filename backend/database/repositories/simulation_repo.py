"""SimulationRepository — maps ScientificModelRun to/from simulation dicts."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from backend.database.models import ScientificModelRun

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Keys stored inside input_parameters._meta to preserve simulation-layer fields
# that have no direct column in ScientificModelRun.
_META_KEY = "_meta"
_META_FIELDS = ("scenario_name", "description", "start_date", "end_date", "submitted_by", "submitted_at")


def _simulation_to_dict(obj: ScientificModelRun) -> dict[str, Any]:
    """Unpack a ScientificModelRun into the simulation dict the service expects."""
    meta: dict[str, Any] = obj.input_parameters.get(_META_KEY, {})
    parameters = {k: v for k, v in obj.input_parameters.items() if k != _META_KEY}
    return {
        "id": str(obj.id) if obj.id else None,
        "lagoon_id": str(obj.lagoon_id) if obj.lagoon_id else None,
        "simulation_type": obj.model_name,
        "model_version": obj.model_version,
        "status": obj.status,
        "scenario_name": meta.get("scenario_name"),
        "description": meta.get("description"),
        "start_date": meta.get("start_date"),
        "end_date": meta.get("end_date"),
        "parameters": parameters,
        "submitted_by": meta.get("submitted_by"),
        "submitted_at": meta.get("submitted_at"),
        "output_results": obj.output_results,
        "confidence": obj.confidence,
        "assumptions": obj.assumptions,
        "limitations": obj.limitations,
        "execution_time_seconds": obj.execution_time_seconds,
        "error_message": obj.error_message,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
    }


def _build_model_run_kwargs(data: dict[str, Any]) -> dict[str, Any]:
    """Map simulation dict fields to ScientificModelRun column names."""
    # Separate meta fields from user-facing parameters
    meta: dict[str, Any] = {field: data.get(field) for field in _META_FIELDS}
    parameters: dict[str, Any] = dict(data.get("parameters") or {})
    input_parameters = {**parameters, _META_KEY: meta}

    kwargs: dict[str, Any] = {
        "model_name": data["simulation_type"],
        "input_parameters": input_parameters,
        "lagoon_id": data["lagoon_id"],
    }
    # Optional fields that have direct columns
    for field in ("id", "status", "confidence", "model_version"):
        if field in data and data[field] is not None:
            kwargs[field] = data[field]
    return kwargs


class SimulationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, lagoon_id: uuid.UUID, skip: int, limit: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(ScientificModelRun)
            .where(ScientificModelRun.lagoon_id == lagoon_id)
            .order_by(ScientificModelRun.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return [_simulation_to_dict(row) for row in result.scalars().all()]

    async def get(self, simulation_id: uuid.UUID, lagoon_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(ScientificModelRun).where(
                ScientificModelRun.id == simulation_id,
                ScientificModelRun.lagoon_id == lagoon_id,
            )
        )
        obj = result.scalar_one_or_none()
        return _simulation_to_dict(obj) if obj else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        obj = ScientificModelRun(**_build_model_run_kwargs(data))
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return _simulation_to_dict(obj)

    async def update(self, simulation_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(ScientificModelRun).where(ScientificModelRun.id == simulation_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        # Map any simulation-layer keys back to ORM columns before updating
        if "simulation_type" in data:
            obj.model_name = data.pop("simulation_type")
        if "parameters" in data:
            meta = obj.input_parameters.get(_META_KEY, {})
            obj.input_parameters = {**data.pop("parameters"), _META_KEY: meta}
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return _simulation_to_dict(obj)
