"""SensorRepository — returns plain dicts (not ORM objects)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from backend.database.models import Sensor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _sensor_to_dict(obj: Sensor) -> dict[str, Any]:
    meta: dict[str, Any] = obj.extra_metadata or {}
    return {
        "id": str(obj.id) if obj.id else None,
        "lagoon_id": str(obj.lagoon_id) if obj.lagoon_id else None,
        "name": obj.name,
        "sensor_type": obj.sensor_type,
        # Expose parameter stored in metadata (seeded or via API)
        "parameter": meta.get("parameter", obj.sensor_type),
        "location_description": meta.get("location_description"),
        "latitude": meta.get("latitude"),
        "longitude": meta.get("longitude"),
        "depth_m": obj.depth_m,
        "unit": obj.unit,
        "sampling_interval_s": meta.get("sampling_interval_s", 900),
        "detection_limit": meta.get("detection_limit"),
        "accuracy": meta.get("accuracy"),
        "calibration_date": obj.calibration_date.isoformat() if obj.calibration_date else None,
        "calibration_factor": obj.calibration_factor,
        "calibration_offset": obj.calibration_offset,
        "manufacturer": obj.manufacturer,
        "model_number": obj.model_number,
        "serial_number": obj.serial_number,
        "is_active": obj.is_active,
        "status": obj.status,
        "metadata": meta,
        "last_reading_at": meta.get("last_reading_at"),
        "last_calibration_at": obj.calibration_date.isoformat() if obj.calibration_date else None,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


def _prepare_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remap 'metadata' key to 'extra_metadata' to match ORM attribute name."""
    prepared = dict(data)
    if "metadata" in prepared:
        prepared["extra_metadata"] = prepared.pop("metadata")
    return prepared


class SensorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, lagoon_id: uuid.UUID, skip: int, limit: int) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Sensor)
            .where(Sensor.lagoon_id == lagoon_id)
            .offset(skip)
            .limit(limit)
        )
        return [_sensor_to_dict(row) for row in result.scalars().all()]

    async def get(self, sensor_id: uuid.UUID, lagoon_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Sensor).where(Sensor.id == sensor_id, Sensor.lagoon_id == lagoon_id)
        )
        obj = result.scalar_one_or_none()
        return _sensor_to_dict(obj) if obj else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        obj = Sensor(**_prepare_data(data))
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return _sensor_to_dict(obj)

    async def update(
        self, sensor_id: uuid.UUID, lagoon_id: uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        result = await self._session.execute(
            select(Sensor).where(Sensor.id == sensor_id, Sensor.lagoon_id == lagoon_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        prepared = _prepare_data(data)
        for key, value in prepared.items():
            setattr(obj, key, value)
        await self._session.flush()
        await self._session.refresh(obj)
        return _sensor_to_dict(obj)

    async def deactivate(self, sensor_id: uuid.UUID, lagoon_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(Sensor).where(Sensor.id == sensor_id, Sensor.lagoon_id == lagoon_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return False
        obj.is_active = False
        obj.status = "inactive"
        await self._session.flush()
        return True

    async def create_calibration(self, sensor_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._session.execute(
            select(Sensor).where(Sensor.id == sensor_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return {}
        calibration: dict[str, Any] = {"id": str(uuid.uuid4()), **data}
        metadata = dict(obj.extra_metadata)
        calibrations: list[dict[str, Any]] = list(metadata.get("calibrations", []))
        calibrations.append(calibration)
        metadata["calibrations"] = calibrations
        obj.extra_metadata = metadata
        await self._session.flush()
        await self._session.refresh(obj)
        return calibration
