"""Sensor repository — sensor management and status queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from backend.database.models import Sensor
from backend.database.repositories.base import BaseRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class SensorRepository(BaseRepository[Sensor]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Sensor, session)

    async def get_active_for_lagoon(
        self, lagoon_id: uuid.UUID, sensor_type: str | None = None
    ) -> list[Sensor]:
        """Fetch all active, non-faulty sensors for a lagoon."""
        stmt = select(Sensor).where(
            Sensor.lagoon_id == lagoon_id,
            Sensor.is_active.is_(True),
            Sensor.status.in_(["active", "calibrating"]),
        )
        if sensor_type:
            stmt = stmt.where(Sensor.sensor_type == sensor_type)
        stmt = stmt.order_by(Sensor.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_type(
        self, lagoon_id: uuid.UUID, sensor_type: str
    ) -> list[Sensor]:
        """Fetch all sensors of a given type for a lagoon."""
        result = await self.session.execute(
            select(Sensor)
            .where(Sensor.lagoon_id == lagoon_id, Sensor.sensor_type == sensor_type)
            .order_by(Sensor.depth_m.asc().nullsfirst())
        )
        return list(result.scalars().all())

    async def get_faulty(self, lagoon_id: uuid.UUID) -> list[Sensor]:
        """Fetch sensors with faulty or decommissioned status."""
        result = await self.session.execute(
            select(Sensor)
            .where(
                Sensor.lagoon_id == lagoon_id,
                Sensor.status.in_(["faulty", "inactive"]),
            )
            .order_by(Sensor.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_due_for_calibration(
        self, lagoon_id: uuid.UUID, within_days: int = 30
    ) -> list[Sensor]:
        """Return sensors whose calibration is due within N days."""
        cutoff = datetime.now(tz=UTC) - timedelta(days=365 - within_days)
        result = await self.session.execute(
            select(Sensor).where(
                Sensor.lagoon_id == lagoon_id,
                Sensor.is_active.is_(True),
                Sensor.calibration_date <= cutoff,
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self, sensor_id: uuid.UUID, status: str
    ) -> Sensor | None:
        """Update the operational status of a sensor."""
        valid_statuses = {"active", "inactive", "faulty", "calibrating", "decommissioned"}
        if status not in valid_statuses:
            from backend.core.exceptions.exceptions import ValidationException
            raise ValidationException(
                message=f"Invalid sensor status '{status}'.",
                detail={"valid_statuses": sorted(valid_statuses)},
            )
        return await self.update(sensor_id, {"status": status})

    async def get_sensor_type_summary(
        self, lagoon_id: uuid.UUID
    ) -> dict[str, int]:
        """Count sensors grouped by type for a lagoon."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(Sensor.sensor_type, func.count(Sensor.id).label("n"))
            .where(Sensor.lagoon_id == lagoon_id, Sensor.is_active.is_(True))
            .group_by(Sensor.sensor_type)
            .order_by(func.count(Sensor.id).desc())
        )
        return {row.sensor_type: row.n for row in result.all()}
