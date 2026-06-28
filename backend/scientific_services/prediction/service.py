"""
Prediction service — multi-horizon lagoon state forecasting.

Uses trend extrapolation on rolling scientific state histories to
generate 7-, 14-, and 30-day bloom probability and water quality forecasts.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from collections import deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ..base import ScientificService, ServiceStatus
from .models import Forecast, LagoonForecast

logger = logging.getLogger(__name__)

# Rolling history window for trend computation (48 = 4h @ 5min)
_HISTORY_LEN = 288  # 24h at 5 min intervals


class PredictionService(ScientificService):
    """
    Continuous forecasting service.

    Maintains rolling history of scientific state, computes exponential
    smoothing trends, and extrapolates to 7/14/30-day horizons.

    Loop interval: configurable (default 1800 s / 30 min).
    """

    service_name = "prediction"
    loop_name = "forecast_loop"

    def __init__(
        self,
        shared_memory: Any,
        event_bus: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._shared_memory = shared_memory
        self._event_bus = event_bus
        self._config = config or {}
        self._interval_seconds: float = float(self._config.get("interval_seconds", 1800))
        self._running = False
        self._task: asyncio.Task | None = None
        # Per-lagoon rolling histories: param → deque of (timestamp, value)
        self._histories: dict[UUID, dict[str, deque[tuple[datetime, float]]]] = {}
        self._status = ServiceStatus.INITIALIZING

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("PredictionService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="predict_loop")
        if self._event_bus is not None:
            for topic in (
                "scientific.hydrological.state",
                "scientific.chemical.state",
                "scientific.ecological.state",
            ):
                await self._event_bus.subscribe(topic, self.process_event)

    async def stop(self) -> None:
        logger.info("PredictionService stopping")
        self._running = False
        self._status = ServiceStatus.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    # ------------------------------------------------------------------
    # Event handling — ingest scientific state into rolling histories
    # ------------------------------------------------------------------

    async def process_event(self, event: dict[str, Any]) -> None:
        try:
            lagoon_id = UUID(str(event["lagoon_id"]))
            state: dict[str, Any] = event.get("state", event.get("payload", {}).get("state", {}))
            now = datetime.now(tz=UTC)

            if lagoon_id not in self._histories:
                self._histories[lagoon_id] = {}

            hist = self._histories[lagoon_id]
            _TRACKED_PARAMS = [
                "bloom_probability", "do_mg_l", "do_saturation_pct",
                "residence_time_days", "tp_mg_l", "tn_mg_l", "orp_mv",
                "temperature_c", "water_level_m",
            ]
            for param in _TRACKED_PARAMS:
                val = state.get(param)
                if val is not None:
                    try:
                        float_val = float(val)
                        if param not in hist:
                            hist[param] = deque(maxlen=_HISTORY_LEN)
                        hist[param].append((now, float_val))
                    except (TypeError, ValueError):
                        pass

        except Exception as exc:
            logger.warning("PredictionService.process_event error: %s", exc)
            self._error_count += 1

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        forecast = await self._generate_forecast(lagoon_id)
        return forecast.to_dict()

    async def _generate_forecast(self, lagoon_id: UUID) -> LagoonForecast:
        hist = self._histories.get(lagoon_id, {})
        now = datetime.now(tz=UTC)
        forecasts: list[Forecast] = []
        confidence_sum = 0.0
        confidence_count = 0

        for param, horizons in [
            ("bloom_probability", [7, 14, 30]),
            ("do_mg_l", [7, 14]),
            ("tp_mg_l", [7, 14]),
            ("residence_time_days", [7, 14]),
            ("temperature_c", [7]),
        ]:
            series = list(hist.get(param, []))
            if len(series) < 3:
                continue

            values = [v for _, v in series]
            trend_dir, slope, alpha, smoothed = _exponential_smoothing_trend(values)

            for h in horizons:
                predicted = smoothed + slope * h * (len(values) / max(len(values), 1))
                # Clamp domain-specific bounds
                predicted = _clamp_param(param, predicted)
                uncertainty = abs(slope) * h * 0.5 + _rmse(values, alpha)
                lower = _clamp_param(param, predicted - uncertainty)
                upper = _clamp_param(param, predicted + uncertainty)
                conf = max(0.1, min(0.9, 1.0 - uncertainty / max(abs(predicted) + 0.001, 0.001)))

                forecasts.append(Forecast(
                    parameter=param,
                    horizon_days=h,
                    predicted_value=round(predicted, 4),
                    lower_bound=round(lower, 4),
                    upper_bound=round(upper, 4),
                    confidence=round(conf, 3),
                    trend=trend_dir,
                    timestamp=now,
                    method="exponential_smoothing",
                ))
                confidence_sum += conf
                confidence_count += 1

        # ---- Bloom probability forecasts ----
        bloom_series = [v for _, v in hist.get("bloom_probability", [])]
        bloom_7d = _extrapolate(bloom_series, 7, 0.0, 1.0)
        bloom_14d = _extrapolate(bloom_series, 14, 0.0, 1.0)
        bloom_30d = _extrapolate(bloom_series, 30, 0.0, 1.0)

        # ---- DO trend ----
        do_series = [v for _, v in hist.get("do_mg_l", [])]
        do_slope = _linear_slope(do_series)
        if do_slope > 0.05:
            do_trend = "improving"
        elif do_slope < -0.05:
            do_trend = "deteriorating"
        else:
            do_trend = "stable"

        # ---- Residence time trend ----
        rt_series = [v for _, v in hist.get("residence_time_days", [])]
        rt_slope = _linear_slope(rt_series)
        if rt_slope > 0.2:
            rt_trend = "increasing"
        elif rt_slope < -0.2:
            rt_trend = "decreasing"
        else:
            rt_trend = "stable"

        # ---- Overall trajectory ----
        if bloom_14d > 0.75 or (do_trend == "deteriorating" and bloom_14d > 0.5):
            trajectory = "critical"
        elif bloom_14d > 0.5 or do_trend == "deteriorating":
            trajectory = "deteriorating"
        elif do_trend == "improving" and bloom_14d < 0.25:
            trajectory = "improving"
        else:
            trajectory = "stable"

        overall_conf = round(confidence_sum / max(confidence_count, 1), 3)

        narrative = _build_narrative(bloom_7d, bloom_14d, bloom_30d, do_trend, rt_trend, trajectory)

        return LagoonForecast(
            lagoon_id=lagoon_id,
            generated_at=now,
            bloom_probability_7d=round(bloom_7d, 3),
            bloom_probability_14d=round(bloom_14d, 3),
            bloom_probability_30d=round(bloom_30d, 3),
            do_trend=do_trend,
            residence_time_trend=rt_trend,
            overall_trajectory=trajectory,
            confidence=overall_conf,
            forecasts=forecasts,
            narrative=narrative,
        )

    async def publish_state(self, lagoon_id: UUID) -> None:
        state_dict = await self.compute_state(lagoon_id)
        key = f"predict:{lagoon_id}"
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(key, state_dict, ttl_seconds=7200)
            except Exception as exc:
                logger.warning("Shared memory write failed for %s: %s", key, exc)
        if self._event_bus is not None:
            try:
                await self._event_bus.publish(
                    topic="scientific.prediction.forecast",
                    payload={"lagoon_id": str(lagoon_id), "forecast": state_dict},
                )
            except Exception as exc:
                logger.warning("Event bus publish failed for %s: %s", lagoon_id, exc)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            try:
                lagoon_ids = list(self._histories.keys())
                if not lagoon_ids and self._shared_memory is not None:
                    try:
                        registry = await self._shared_memory.get("lagoon:registry")
                        if registry:
                            lagoon_ids = [UUID(lid) for lid in registry.get("ids", [])]
                    except Exception:
                        pass

                for lagoon_id in lagoon_ids:
                    try:
                        await self.publish_state(lagoon_id)
                    except Exception as exc:
                        logger.error("PredictionService loop error for %s: %s", lagoon_id, exc)
                        self._error_count += 1

                self._last_run = datetime.now(tz=UTC)
                self._run_count += 1

            except Exception as exc:
                logger.error("PredictionService loop unhandled error: %s", exc)
                self._status = ServiceStatus.ERROR
                self._error_count += 1
            finally:
                await asyncio.sleep(self._interval_seconds)


# ------------------------------------------------------------------
# Statistical helpers
# ------------------------------------------------------------------

def _exponential_smoothing_trend(
    values: list[float], alpha: float = 0.3, beta: float = 0.1
) -> tuple[str, float, float, float]:
    """
    Double exponential smoothing (Holt's method).

    Returns: (trend_direction, slope_per_step, alpha_used, last_smoothed_value)
    """
    if not values:
        return "stable", 0.0, alpha, 0.0

    s = values[0]
    b = (values[-1] - values[0]) / max(len(values) - 1, 1)

    for v in values[1:]:
        s_prev = s
        s = alpha * v + (1 - alpha) * (s + b)
        b = beta * (s - s_prev) + (1 - beta) * b

    if b > 0.002:
        direction = "increasing"
    elif b < -0.002:
        direction = "decreasing"
    else:
        direction = "stable"

    return direction, b, alpha, s


def _linear_slope(values: list[float]) -> float:
    """Compute least-squares slope."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


def _extrapolate(values: list[float], horizon: int, lo: float, hi: float) -> float:
    """Extrapolate using Holt's method, clamped to [lo, hi]."""
    if not values:
        return (lo + hi) / 2
    _, slope, _, smoothed = _exponential_smoothing_trend(values)
    predicted = smoothed + slope * horizon
    return max(lo, min(hi, predicted))


def _rmse(values: list[float], alpha: float) -> float:
    """Compute RMSE of exponential smoothing fit."""
    if len(values) < 2:
        return 0.0
    errors: list[float] = []
    s = values[0]
    for v in values[1:]:
        errors.append(v - s)
        s = alpha * v + (1 - alpha) * s
    mse = sum(e**2 for e in errors) / len(errors)
    return math.sqrt(mse)


def _clamp_param(param: str, value: float) -> float:
    """Clamp parameter to physically meaningful range."""
    clamps = {
        "bloom_probability": (0.0, 1.0),
        "do_mg_l": (0.0, 20.0),
        "do_saturation_pct": (0.0, 150.0),
        "residence_time_days": (0.1, 999.0),
        "tp_mg_l": (0.0, 10.0),
        "tn_mg_l": (0.0, 100.0),
        "orp_mv": (-500.0, 800.0),
        "temperature_c": (-5.0, 50.0),
        "water_level_m": (-5.0, 20.0),
    }
    lo, hi = clamps.get(param, (-1e9, 1e9))
    return max(lo, min(hi, value))


def _build_narrative(
    bp7: float,
    bp14: float,
    bp30: float,
    do_trend: str,
    rt_trend: str,
    trajectory: str,
) -> str:
    parts: list[str] = []
    if bp7 > 0.6:
        parts.append(f"Bloom probability is {bp7:.0%} within 7 days — immediate attention required.")
    elif bp7 > 0.3:
        parts.append(f"Moderate bloom risk ({bp7:.0%}) within 7 days.")
    else:
        parts.append(f"Low bloom risk within 7 days ({bp7:.0%}).")

    if do_trend == "deteriorating":
        parts.append("DO is trending downward — aeration may be insufficient.")
    elif do_trend == "improving":
        parts.append("DO is improving.")

    if rt_trend == "increasing":
        parts.append("Residence time increasing — reduced flushing may concentrate nutrients.")

    trajectory_map = {
        "critical": "Overall trajectory is CRITICAL — urgent intervention recommended.",
        "deteriorating": "Overall trajectory is deteriorating — proactive management advised.",
        "stable": "System trajectory is stable.",
        "improving": "System trajectory is improving.",
    }
    parts.append(trajectory_map.get(trajectory, ""))
    return " ".join(p for p in parts if p)
