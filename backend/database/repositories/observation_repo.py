"""ObservationRepository — returns plain dicts (not ORM objects)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from backend.database.models import Observation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _observation_to_dict(obj: Observation) -> dict[str, Any]:
    return {
        "id": str(obj.id) if obj.id else None,
        "lagoon_id": str(obj.lagoon_id) if obj.lagoon_id else None,
        "sensor_id": str(obj.sensor_id) if obj.sensor_id else None,
        "parameter": obj.parameter,
        "value": obj.value,
        "unit": obj.unit,
        "timestamp": obj.timestamp.isoformat() if obj.timestamp else None,
        "depth_m": obj.depth_m,
        "source": obj.source,
        "quality_flag": obj.quality_flag,
        "confidence": obj.confidence,
        "metadata": obj.extra_metadata,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
    }


def _prepare_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remap 'metadata' key to 'extra_metadata' to match ORM attribute name."""
    prepared = dict(data)
    if "metadata" in prepared:
        prepared["extra_metadata"] = prepared.pop("metadata")
    return prepared


class ObservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: dict[str, Any]) -> dict[str, Any]:
        obj = Observation(**_prepare_data(record))
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return _observation_to_dict(obj)

    async def bulk_create(self, records: list[dict[str, Any]]) -> int:
        objs = [Observation(**_prepare_data(r)) for r in records]
        self._session.add_all(objs)
        await self._session.flush()
        return len(objs)

    async def get_latest(
        self, lagoon_id: uuid.UUID, parameters: list[str] | None = None
    ) -> dict[str, Any]:
        """Return {parameter: {value, unit, timestamp, sensor_id}} for latest obs per parameter."""
        stmt = (
            select(Observation)
            .where(Observation.lagoon_id == lagoon_id)
            .order_by(Observation.parameter, Observation.timestamp.desc())
            .distinct(Observation.parameter)
        )
        if parameters:
            stmt = stmt.where(Observation.parameter.in_(parameters))

        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        return {
            row.parameter: {
                "value": row.value,
                "unit": row.unit,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "sensor_id": str(row.sensor_id) if row.sensor_id else None,
            }
            for row in rows
        }

    async def get_time_series(
        self,
        lagoon_id: uuid.UUID,
        parameter: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Return observations ordered by timestamp asc."""
        result = await self._session.execute(
            select(Observation)
            .where(
                Observation.lagoon_id == lagoon_id,
                Observation.parameter == parameter,
                Observation.timestamp >= start,
                Observation.timestamp <= end,
            )
            .order_by(Observation.timestamp.asc())
        )
        return [
            {
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "value": row.value,
                "unit": row.unit,
                "quality_flag": row.quality_flag,
                "sensor_id": str(row.sensor_id) if row.sensor_id else None,
            }
            for row in result.scalars().all()
        ]
