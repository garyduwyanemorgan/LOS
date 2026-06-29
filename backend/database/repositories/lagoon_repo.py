"""LagoonRepository — returns plain dicts (not ORM objects)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from backend.database.models import Lagoon, OperatingObjective

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _lagoon_to_dict(obj: Lagoon) -> dict[str, Any]:
    geo = obj.location or {}
    coords = geo.get("coordinates", [None, None])
    lng = coords[0] if len(coords) > 0 else None
    lat = coords[1] if len(coords) > 1 else None

    design = obj.design_info or {}
    params = obj.operating_parameters or {}

    city = design.get("city", "")
    country = design.get("country", "")

    return {
        "id": str(obj.id) if obj.id else None,
        "org_id": str(obj.org_id) if obj.org_id else None,
        "name": obj.name,
        "slug": obj.slug,
        "description": design.get("description"),
        "latitude": lat,
        "longitude": lng,
        # Frontend Lagoon type expects {lat, lng, city, country}
        "location": {"lat": lat, "lng": lng, "city": city, "country": country},
        "geometry": str(obj.geometry) if obj.geometry else None,
        "volume_m3": obj.volume_m3,
        "surface_area_m2": obj.surface_area_m2,
        "max_depth_m": obj.max_depth_m,
        "mean_depth_m": design.get("mean_depth_m"),
        "operational_mode": params.get("operational_mode", "normal"),
        "timezone": params.get("timezone", "UTC"),
        "salinity_type": params.get("salinity_type", "brackish"),
        "design_info": design,
        "infrastructure_config": obj.infrastructure_config,
        "operating_parameters": params,
        "is_active": obj.is_active,
        "created_by": None,
        "metadata": design.get("metadata"),
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


def _objective_to_dict(obj: OperatingObjective) -> dict[str, Any]:
    return {
        "id": str(obj.id) if obj.id else None,
        "lagoon_id": str(obj.lagoon_id) if obj.lagoon_id else None,
        "objective_type": obj.objective_type,
        "name": obj.name,
        "description": obj.description,
        "target_value": obj.target_value,
        "current_value": obj.current_value,
        "unit": obj.unit,
        "priority": obj.priority,
        "weight": obj.weight,
        "is_active": obj.is_active,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


class LagoonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, lagoon_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Lagoon).where(Lagoon.id == lagoon_id, Lagoon.org_id == org_id)
        )
        obj = result.scalar_one_or_none()
        return _lagoon_to_dict(obj) if obj else None

    async def list(self, org_id: uuid.UUID, skip: int, limit: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Lagoon)
            .where(Lagoon.org_id == org_id, Lagoon.is_active == True)  # noqa: E712
            .offset(skip)
            .limit(limit)
        )
        return [_lagoon_to_dict(row) for row in result.scalars().all()]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        obj = Lagoon(**data)
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return _lagoon_to_dict(obj)

    async def update(self, lagoon_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Lagoon).where(Lagoon.id == lagoon_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return _lagoon_to_dict(obj)

    async def get_objectives(self, lagoon_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(OperatingObjective)
            .where(OperatingObjective.lagoon_id == lagoon_id)
            .order_by(OperatingObjective.priority)
        )
        return [_objective_to_dict(row) for row in result.scalars().all()]

    async def set_objectives(
        self, lagoon_id: uuid.UUID, objectives: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        await self._session.execute(
            delete(OperatingObjective).where(OperatingObjective.lagoon_id == lagoon_id)
        )
        created: list[OperatingObjective] = []
        for obj_data in objectives:
            merged = {**obj_data, "lagoon_id": lagoon_id}
            obj = OperatingObjective(**merged)
            self._session.add(obj)
            created.append(obj)
        await self._session.flush()
        for obj in created:
            await self._session.refresh(obj)
        return [_objective_to_dict(obj) for obj in created]

    async def get_performance_history(self, lagoon_id: uuid.UUID, days: int) -> list[dict[str, Any]]:
        # No aggregation table yet; return empty list.
        return []
