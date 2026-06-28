"""Observation repository — time-series queries for sensor/lab data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text

from backend.database.models import Observation
from backend.database.repositories.base import BaseRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class ObservationRepository(BaseRepository[Observation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Observation, session)

    async def get_latest_by_parameter(
        self,
        lagoon_id: uuid.UUID,
        parameter: str,
        quality_flags: list[str] | None = None,
    ) -> Observation | None:
        """Fetch the most recent observation for a given parameter."""
        stmt = select(Observation).where(
            Observation.lagoon_id == lagoon_id,
            Observation.parameter == parameter,
        )
        if quality_flags:
            stmt = stmt.where(Observation.quality_flag.in_(quality_flags))
        else:
            stmt = stmt.where(Observation.quality_flag.in_(["good", "corrected"]))

        stmt = stmt.order_by(Observation.timestamp.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_date_range(
        self,
        lagoon_id: uuid.UUID,
        parameter: str,
        start: datetime,
        end: datetime,
        quality_flags: list[str] | None = None,
        sensor_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 10000,
    ) -> list[Observation]:
        """Fetch observations for a parameter within a time window."""
        stmt = select(Observation).where(
            Observation.lagoon_id == lagoon_id,
            Observation.parameter == parameter,
            Observation.timestamp >= start,
            Observation.timestamp <= end,
        )

        if quality_flags:
            stmt = stmt.where(Observation.quality_flag.in_(quality_flags))

        if sensor_id:
            stmt = stmt.where(Observation.sensor_id == sensor_id)

        stmt = stmt.order_by(Observation.timestamp.asc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_statistics(
        self,
        lagoon_id: uuid.UUID,
        parameter: str,
        start: datetime,
        end: datetime,
        quality_flags: list[str] | None = None,
    ) -> dict[str, float | int | None]:
        """Compute summary statistics for a parameter over a time window.

        Returns a dict with: count, mean, min, max, stddev, p25, p50, p75.
        """
        flags = quality_flags or ["good", "corrected"]

        # Basic aggregates
        stmt = select(
            func.count(Observation.value).label("count"),
            func.avg(Observation.value).label("mean"),
            func.min(Observation.value).label("min"),
            func.max(Observation.value).label("max"),
            func.stddev(Observation.value).label("stddev"),
        ).where(
            Observation.lagoon_id == lagoon_id,
            Observation.parameter == parameter,
            Observation.timestamp >= start,
            Observation.timestamp <= end,
            Observation.quality_flag.in_(flags),
        )

        result = await self.session.execute(stmt)
        row = result.mappings().one_or_none()

        if row is None or row["count"] == 0:
            return {"count": 0, "mean": None, "min": None, "max": None, "stddev": None,
                    "p25": None, "p50": None, "p75": None}

        # Percentiles via raw SQL (PostgreSQL-specific)
        pct_stmt = text(
            """
            SELECT
                percentile_cont(0.25) WITHIN GROUP (ORDER BY value) AS p25,
                percentile_cont(0.50) WITHIN GROUP (ORDER BY value) AS p50,
                percentile_cont(0.75) WITHIN GROUP (ORDER BY value) AS p75
            FROM observations
            WHERE lagoon_id = :lagoon_id
              AND parameter = :parameter
              AND timestamp BETWEEN :start AND :end
              AND quality_flag = ANY(:flags)
            """
        )
        pct_result = await self.session.execute(
            pct_stmt,
            {
                "lagoon_id": str(lagoon_id),
                "parameter": parameter,
                "start": start,
                "end": end,
                "flags": flags,
            },
        )
        pct_row = pct_result.mappings().one_or_none()

        return {
            "count": row["count"],
            "mean": float(row["mean"]) if row["mean"] is not None else None,
            "min": float(row["min"]) if row["min"] is not None else None,
            "max": float(row["max"]) if row["max"] is not None else None,
            "stddev": float(row["stddev"]) if row["stddev"] is not None else None,
            "p25": float(pct_row["p25"]) if pct_row and pct_row["p25"] is not None else None,
            "p50": float(pct_row["p50"]) if pct_row and pct_row["p50"] is not None else None,
            "p75": float(pct_row["p75"]) if pct_row and pct_row["p75"] is not None else None,
        }

    async def get_parameters_for_lagoon(self, lagoon_id: uuid.UUID) -> list[str]:
        """Return a sorted list of distinct parameter names with observations."""
        result = await self.session.execute(
            select(Observation.parameter)
            .where(Observation.lagoon_id == lagoon_id)
            .distinct()
            .order_by(Observation.parameter)
        )
        return [row[0] for row in result.all()]

    async def get_multi_parameter_latest(
        self,
        lagoon_id: uuid.UUID,
        parameters: list[str],
    ) -> dict[str, Observation | None]:
        """Fetch the latest good observation for each parameter in the list.

        Returns a dict of parameter → Observation (or None if no data).
        """
        results: dict[str, Observation | None] = {}
        for param in parameters:
            results[param] = await self.get_latest_by_parameter(lagoon_id, param)
        return results

    async def count_by_source(
        self, lagoon_id: uuid.UUID, start: datetime, end: datetime
    ) -> dict[str, int]:
        """Count observations grouped by source within a time window."""
        stmt = (
            select(Observation.source, func.count(Observation.id).label("n"))
            .where(
                Observation.lagoon_id == lagoon_id,
                Observation.timestamp >= start,
                Observation.timestamp <= end,
            )
            .group_by(Observation.source)
        )
        result = await self.session.execute(stmt)
        return {row.source: row.n for row in result.all()}

    async def get_recent_anomalies(
        self, lagoon_id: uuid.UUID, hours: int = 24
    ) -> list[Observation]:
        """Return observations flagged as suspect or bad in the last N hours."""
        from datetime import timedelta

        cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
        stmt = (
            select(Observation)
            .where(
                Observation.lagoon_id == lagoon_id,
                Observation.quality_flag.in_(["suspect", "bad"]),
                Observation.timestamp >= cutoff,
            )
            .order_by(Observation.timestamp.desc())
            .limit(500)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
