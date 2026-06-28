"""Application service for sensor observation ingestion and retrieval."""
from __future__ import annotations

import logging
import statistics
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

# ── Valid parameter registry ─────────────────────────────────────────────────

PARAMETER_RANGES: dict[str, dict[str, float]] = {
    "do_mg_l":         {"min": 0.0,   "max": 20.0},
    "ph":              {"min": 0.0,   "max": 14.0},
    "temperature_c":   {"min": -5.0,  "max": 50.0},
    "salinity_ppt":    {"min": 0.0,   "max": 60.0},
    "turbidity_ntu":   {"min": 0.0,   "max": 5000.0},
    "chlorophyll_ug_l":{"min": 0.0,   "max": 2000.0},
    "tss_mg_l":        {"min": 0.0,   "max": 10000.0},
    "tn_mg_l":         {"min": 0.0,   "max": 200.0},
    "tp_mg_l":         {"min": 0.0,   "max": 50.0},
    "nh4_mg_l":        {"min": 0.0,   "max": 100.0},
    "no3_mg_l":        {"min": 0.0,   "max": 100.0},
    "po4_mg_l":        {"min": 0.0,   "max": 20.0},
    "cod_mg_l":        {"min": 0.0,   "max": 5000.0},
    "bod_mg_l":        {"min": 0.0,   "max": 2000.0},
    "water_level_m":   {"min": -5.0,  "max": 20.0},
    "flow_m3_s":       {"min": 0.0,   "max": 1000.0},
    "conductivity_us_cm": {"min": 0.0, "max": 200000.0},
    "redox_mv":        {"min": -500.0, "max": 800.0},
    "h2s_ug_l":        {"min": 0.0,   "max": 10000.0},
    "toc_mg_l":        {"min": 0.0,   "max": 1000.0},
}


# ── Repository protocols ─────────────────────────────────────────────────────

class ObservationRepository(Protocol):
    async def create(self, record: dict[str, Any]) -> dict[str, Any]: ...
    async def bulk_create(self, records: list[dict[str, Any]]) -> int: ...
    async def get_latest(self, lagoon_id: UUID, parameters: list[str] | None) -> dict[str, Any]: ...
    async def get_time_series(
        self, lagoon_id: UUID, parameter: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]: ...


class EventBus(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


# ── Service ──────────────────────────────────────────────────────────────────

class ObservationService:
    """Handles all observation ingestion and retrieval operations."""

    def __init__(self, observation_repo: ObservationRepository, event_bus: EventBus) -> None:
        self._repo = observation_repo
        self._bus = event_bus

    async def ingest_observation(
        self,
        data: dict[str, Any],
        lagoon_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """Validate, persist and publish a single observation.

        Raises ValueError for out-of-range or unknown parameters.
        """
        _validate_observation(data)

        record = {
            **data,
            "lagoon_id": str(lagoon_id),
            "source": "manual",
            "submitted_by": str(user_id),
            "ingested_at": datetime.now(UTC).isoformat(),
        }

        created = await self._repo.create(record)

        await self._bus.publish(
            "observation.ingested",
            {
                "lagoon_id": str(lagoon_id),
                "parameter": data.get("parameter"),
                "value": data.get("value"),
                "timestamp": data.get("timestamp"),
                "source": "manual",
                "user_id": str(user_id),
            },
        )

        logger.debug(
            "Observation ingested lagoon=%s param=%s value=%s",
            lagoon_id,
            data.get("parameter"),
            data.get("value"),
        )
        return created

    async def bulk_ingest(
        self,
        observations: list[dict[str, Any]],
        lagoon_id: UUID,
    ) -> dict[str, Any]:
        """Validate and batch-insert multiple observations.

        Returns a summary with accepted/rejected counts.
        """
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for i, obs in enumerate(observations):
            try:
                _validate_observation(obs)
                accepted.append(
                    {
                        **obs,
                        "lagoon_id": str(lagoon_id),
                        "source": obs.get("source", "bulk_import"),
                        "ingested_at": datetime.now(UTC).isoformat(),
                    }
                )
            except ValueError as exc:
                rejected.append({"index": i, "error": str(exc), "data": obs})

        inserted_count = 0
        if accepted:
            inserted_count = await self._repo.bulk_create(accepted)

        if inserted_count > 0:
            await self._bus.publish(
                "observation.bulk_ingested",
                {
                    "lagoon_id": str(lagoon_id),
                    "accepted": inserted_count,
                    "rejected": len(rejected),
                },
            )

        logger.info(
            "Bulk ingest lagoon=%s accepted=%d rejected=%d",
            lagoon_id,
            inserted_count,
            len(rejected),
        )
        return {
            "accepted": inserted_count,
            "rejected": len(rejected),
            "rejected_details": rejected[:50],  # cap detail to avoid huge payloads
        }

    async def get_latest_readings(
        self,
        lagoon_id: UUID,
        parameters: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return the most recent reading for each parameter.

        If parameters is None, returns all available parameters.
        """
        if parameters is not None:
            unknown = set(parameters) - PARAMETER_RANGES.keys()
            if unknown:
                raise ValueError(f"Unknown parameters: {unknown}")

        readings = await self._repo.get_latest(lagoon_id, parameters)
        return {
            "lagoon_id": str(lagoon_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "readings": readings,
        }

    async def get_time_series(
        self,
        lagoon_id: UUID,
        parameter: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Return ordered time series for a single parameter in [start, end]."""
        if parameter not in PARAMETER_RANGES:
            raise ValueError(f"Unknown parameter: '{parameter}'. Valid: {sorted(PARAMETER_RANGES)}")
        if end <= start:
            raise ValueError("end must be after start")
        if (end - start).days > 365:
            raise ValueError("Time range cannot exceed 365 days")

        return await self._repo.get_time_series(lagoon_id, parameter, start, end)

    async def get_statistics(
        self,
        lagoon_id: UUID,
        parameter: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Return descriptive statistics for a parameter over the past N days."""
        from datetime import timedelta

        if parameter not in PARAMETER_RANGES:
            raise ValueError(f"Unknown parameter: '{parameter}'")
        if days > 365:
            days = 365

        end = datetime.now(UTC)
        start = end - timedelta(days=days)

        records = await self._repo.get_time_series(lagoon_id, parameter, start, end)
        values = [r["value"] for r in records if r.get("value") is not None]

        if not values:
            return {
                "lagoon_id": str(lagoon_id),
                "parameter": parameter,
                "period_days": days,
                "count": 0,
                "statistics": None,
            }

        return {
            "lagoon_id": str(lagoon_id),
            "parameter": parameter,
            "period_days": days,
            "count": len(values),
            "statistics": {
                "mean": round(statistics.mean(values), 4),
                "median": round(statistics.median(values), 4),
                "std_dev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "p10": round(_percentile(values, 10), 4),
                "p25": round(_percentile(values, 25), 4),
                "p75": round(_percentile(values, 75), 4),
                "p90": round(_percentile(values, 90), 4),
            },
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_observation(data: dict[str, Any]) -> None:
    """Raise ValueError if observation data is invalid."""
    required = {"parameter", "value", "timestamp"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    param = data["parameter"]
    if param not in PARAMETER_RANGES:
        raise ValueError(f"Unknown parameter '{param}'. Valid: {sorted(PARAMETER_RANGES)}")

    value = data["value"]
    if not isinstance(value, (int, float)):
        raise ValueError(f"value must be numeric, got {type(value).__name__}")

    rng = PARAMETER_RANGES[param]
    if not rng["min"] <= value <= rng["max"]:
        raise ValueError(
            f"value {value} out of valid range [{rng['min']}, {rng['max']}] for {param}"
        )

    # Validate timestamp is parseable
    ts = data["timestamp"]
    if isinstance(ts, str):
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"timestamp '{ts}' is not a valid ISO 8601 datetime") from exc


def _percentile(values: list[float], pct: float) -> float:
    """Compute a percentile without scipy dependency."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    idx = (pct / 100.0) * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac
