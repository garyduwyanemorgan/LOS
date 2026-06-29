"""DBReportDataProvider — implements ReportDataProvider Protocol for ReportService."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from backend.database.models import (
    Intervention,
    Lagoon,
    Observation,
    Recommendation,
    ScientificModelRun,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Water quality parameters considered for WQ statistics
_WQ_PARAMS = (
    "temperature",
    "ph",
    "dissolved_oxygen",
    "do",
    "turbidity",
    "salinity",
    "conductivity",
    "tss",
    "bod",
    "cod",
    "ammonia",
    "nitrate",
    "phosphate",
    "tds",
)

# Ecological indicator parameters
_ECO_PARAMS = (
    "chlorophyll",
    "chlorophyll_a",
    "chl",
    "dissolved_oxygen",
    "do",
    "phytoplankton",
    "zooplankton",
    "turbidity",
    "secchi_depth",
)


def _since(days: int) -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=days)


class DBReportDataProvider:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_lagoon_summary(self, lagoon_id: uuid.UUID) -> dict[str, Any]:
        result = await self._session.execute(
            select(Lagoon).where(Lagoon.id == lagoon_id)
        )
        obj = result.scalar_one_or_none()
        if obj is None:
            return {}
        return {
            "id": str(obj.id),
            "name": obj.name,
            "slug": obj.slug,
            "location": obj.location,
            "volume_m3": obj.volume_m3,
            "surface_area_m2": obj.surface_area_m2,
            "max_depth_m": obj.max_depth_m,
            "is_active": obj.is_active,
        }

    async def get_water_quality_stats(self, lagoon_id: uuid.UUID, days: int) -> dict[str, Any]:
        """Aggregate min/avg/max per WQ parameter over the last `days` days."""
        cutoff = _since(days)
        result = await self._session.execute(
            select(
                Observation.parameter,
                func.min(Observation.value).label("min"),
                func.avg(Observation.value).label("avg"),
                func.max(Observation.value).label("max"),
                func.count(Observation.id).label("count"),
                func.max(Observation.unit).label("unit"),
            )
            .where(
                Observation.lagoon_id == lagoon_id,
                Observation.timestamp >= cutoff,
                Observation.parameter.in_(_WQ_PARAMS),
            )
            .group_by(Observation.parameter)
        )
        rows = result.all()
        return {
            row.parameter: {
                "min": row.min,
                "avg": float(row.avg) if row.avg is not None else None,
                "max": row.max,
                "count": row.count,
                "unit": row.unit,
            }
            for row in rows
        }

    async def get_ecological_indicators(self, lagoon_id: uuid.UUID, days: int) -> dict[str, Any]:
        """Subset of observations covering ecological indicator parameters."""
        cutoff = _since(days)
        result = await self._session.execute(
            select(
                Observation.parameter,
                func.min(Observation.value).label("min"),
                func.avg(Observation.value).label("avg"),
                func.max(Observation.value).label("max"),
                func.count(Observation.id).label("count"),
                func.max(Observation.unit).label("unit"),
            )
            .where(
                Observation.lagoon_id == lagoon_id,
                Observation.timestamp >= cutoff,
                Observation.parameter.in_(_ECO_PARAMS),
            )
            .group_by(Observation.parameter)
        )
        rows = result.all()
        return {
            row.parameter: {
                "min": row.min,
                "avg": float(row.avg) if row.avg is not None else None,
                "max": row.max,
                "count": row.count,
                "unit": row.unit,
            }
            for row in rows
        }

    async def get_intervention_log(self, lagoon_id: uuid.UUID, days: int) -> list[dict[str, Any]]:
        cutoff = _since(days)
        result = await self._session.execute(
            select(Intervention)
            .where(
                Intervention.lagoon_id == lagoon_id,
                Intervention.created_at >= cutoff,
            )
            .order_by(Intervention.created_at.desc())
        )
        return [
            {
                "id": str(row.id),
                "action": row.action,
                "status": row.status,
                "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                "implemented_at": row.implemented_at.isoformat() if row.implemented_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "observed_outcome": row.observed_outcome,
                "notes": row.notes,
            }
            for row in result.scalars().all()
        ]

    async def get_recommendation_summary(self, lagoon_id: uuid.UUID, days: int) -> dict[str, Any]:
        cutoff = _since(days)
        result = await self._session.execute(
            select(Recommendation.status, func.count(Recommendation.id).label("count"))
            .where(
                Recommendation.lagoon_id == lagoon_id,
                Recommendation.created_at >= cutoff,
            )
            .group_by(Recommendation.status)
        )
        counts = {row.status: row.count for row in result.all()}
        total = sum(counts.values())
        return {"total": total, "by_status": counts}

    async def get_compliance_status(self, lagoon_id: uuid.UUID, days: int) -> dict[str, Any]:
        """Basic compliance check — returns observation quality flag counts."""
        cutoff = _since(days)
        result = await self._session.execute(
            select(
                Observation.quality_flag,
                func.count(Observation.id).label("count"),
            )
            .where(
                Observation.lagoon_id == lagoon_id,
                Observation.timestamp >= cutoff,
            )
            .group_by(Observation.quality_flag)
        )
        flag_counts = {row.quality_flag: row.count for row in result.all()}
        total = sum(flag_counts.values())
        good = flag_counts.get("good", 0)
        compliance_rate = (good / total) if total > 0 else None
        return {
            "compliance_rate": compliance_rate,
            "total_observations": total,
            "by_quality_flag": flag_counts,
        }

    async def get_infrastructure_status(self, lagoon_id: uuid.UUID) -> dict[str, Any]:
        """MVP: return empty dict — no aggregation of infrastructure assets yet."""
        return {}

    async def get_loop_performance(self, lagoon_id: uuid.UUID, days: int) -> dict[str, Any]:
        """Summarise scientific model runs over the last `days` days."""
        cutoff = _since(days)
        result = await self._session.execute(
            select(
                ScientificModelRun.model_name,
                ScientificModelRun.status,
                func.count(ScientificModelRun.id).label("count"),
                func.avg(ScientificModelRun.confidence).label("avg_confidence"),
                func.avg(ScientificModelRun.execution_time_seconds).label("avg_execution_seconds"),
            )
            .where(
                ScientificModelRun.lagoon_id == lagoon_id,
                ScientificModelRun.created_at >= cutoff,
            )
            .group_by(ScientificModelRun.model_name, ScientificModelRun.status)
        )
        rows = result.all()
        summary: dict[str, Any] = {}
        for row in rows:
            if row.model_name not in summary:
                summary[row.model_name] = {}
            summary[row.model_name][row.status] = {
                "count": row.count,
                "avg_confidence": float(row.avg_confidence) if row.avg_confidence is not None else None,
                "avg_execution_seconds": (
                    float(row.avg_execution_seconds)
                    if row.avg_execution_seconds is not None
                    else None
                ),
            }
        return summary
