"""
Ecological service — continuous ecosystem health assessment for each lagoon.

Integrates chemical and hydrological state from shared memory,
computes bloom risk and succession, publishes EcologicalState.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ..base import ScientificService, ServiceStatus
from .calculations import (
    bloom_probability,
    cyanobacteria_competitive_advantage,
    ecological_stability_score,
    recovery_potential,
    succession_stage,
)
from .models import EcologicalState

logger = logging.getLogger(__name__)

# Maximum historical bloom probability records for trend calculation
_HISTORY_WINDOW = 48  # ~24h at 30 min intervals


class EcologicalService(ScientificService):
    """
    Continuous ecological state estimation service.

    Loop interval: configurable (default 300 s / 5 min).
    """

    service_name = "ecological"
    loop_name = "ecosystem_health_loop"

    def __init__(
        self,
        shared_memory: Any,
        event_bus: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._shared_memory = shared_memory
        self._event_bus = event_bus
        self._config = config or {}
        self._interval_seconds: float = float(self._config.get("interval_seconds", 300))
        self._running = False
        self._task: asyncio.Task | None = None
        # Per-lagoon direct bio sensor cache
        self._sensor_cache: dict[UUID, dict[str, Any]] = {}
        # Historical bloom probabilities for trend detection
        self._bloom_history: dict[UUID, deque[float]] = {}
        # Historical bloom event counts per lagoon
        self._bloom_event_counts: dict[UUID, int] = {}
        self._status = ServiceStatus.INITIALIZING

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("EcologicalService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="eco_loop")
        if self._event_bus is not None:
            for topic in (
                "sensor.biological",
                "sensor.chlorophyll",
                "sensor.phycocyanin",
                "sensor.secchi",
                "event.bloom_confirmed",
            ):
                await self._event_bus.subscribe(topic, self.process_event)

    async def stop(self) -> None:
        logger.info("EcologicalService stopping")
        self._running = False
        self._status = ServiceStatus.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    async def process_event(self, event: dict[str, Any]) -> None:
        try:
            lagoon_id = UUID(str(event["lagoon_id"]))
            data: dict[str, Any] = event.get("data", {})
            topic: str = event.get("topic", "")

            if lagoon_id not in self._sensor_cache:
                self._sensor_cache[lagoon_id] = {}
            cache = self._sensor_cache[lagoon_id]

            float_fields = [
                "chlorophyll_a_ug_l", "phycocyanin_rfu", "secchi_depth_m",
                "macrophyte_cover_pct",
            ]
            for field in float_fields:
                if field in data:
                    cache[field] = float(data[field])

            if "event.bloom_confirmed" in topic:
                self._bloom_event_counts[lagoon_id] = (
                    self._bloom_event_counts.get(lagoon_id, 0) + 1
                )
                logger.info("Bloom event confirmed for lagoon %s (count=%d)", lagoon_id,
                            self._bloom_event_counts[lagoon_id])

            cache["last_event_ts"] = datetime.now(tz=UTC).isoformat()

        except Exception as exc:
            logger.warning("EcologicalService.process_event error: %s", exc)
            self._error_count += 1

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    async def _fetch_scientific_state(self, lagoon_id: UUID) -> dict[str, Any]:
        """Fetch chemical and hydrological state from shared memory."""
        result: dict[str, Any] = {}
        if self._shared_memory is None:
            return result
        for prefix in ("chem", "hydro"):
            try:
                state = await self._shared_memory.get(f"{prefix}:{lagoon_id}")
                if state:
                    result.update(state)
            except Exception as exc:
                logger.debug("Could not fetch %s state for %s: %s", prefix, lagoon_id, exc)
        return result

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        cache = self._sensor_cache.get(lagoon_id, {})
        sci = await self._fetch_scientific_state(lagoon_id)
        notes: list[str] = []

        # ---- Extract water quality parameters ----
        tp_mg_l: float | None = sci.get("tp_mg_l")
        tn_mg_l: float | None = sci.get("tn_mg_l")
        do_mg_l: float | None = sci.get("do_mg_l")
        do_sat_pct: float | None = sci.get("do_saturation_pct")
        orp_mv: float | None = sci.get("orp_mv")
        temp_c: float | None = sci.get("temperature_c")
        trophic: str | None = sci.get("trophic_state")
        rt_days: float | None = sci.get("residence_time_days")

        # Bio sensor values
        chl_a: float | None = cache.get("chlorophyll_a_ug_l") or sci.get("chlorophyll_a_ug_l")
        phyco: float | None = cache.get("phycocyanin_rfu")
        secchi: float | None = cache.get("secchi_depth_m")
        macrophyte: float | None = cache.get("macrophyte_cover_pct")

        # Override TP/TN from chlorophyll if not available (empirical)
        if tp_mg_l is None and chl_a is not None:
            tp_mg_l = chl_a * 0.002  # Vollenweider-type approximation
            notes.append("TP estimated from chlorophyll-a (Vollenweider approximation)")

        # ---- N:P ratio ----
        np_ratio: float | None = None
        if tn_mg_l is not None and tp_mg_l is not None and tp_mg_l > 0:
            np_ratio = tn_mg_l / tp_mg_l

        # ---- Core ecological calculations ----
        bloom_prob = bloom_probability(
            tp_mg_l=tp_mg_l,
            tn_mg_l=tn_mg_l,
            residence_time_days=rt_days,
            temp_c=temp_c,
            do_mg_l=do_mg_l,
            orp_mv=orp_mv,
        )

        cyano_adv = cyanobacteria_competitive_advantage(
            temp_c=temp_c,
            n_p_ratio=np_ratio,
            do_mg_l=do_mg_l,
        )

        hist_count = self._bloom_event_counts.get(lagoon_id, 0)

        succ = succession_stage(
            bloom_probability=bloom_prob,
            do_mg_l=do_mg_l,
            historical_bloom_count=hist_count,
        )

        eco_stability = ecological_stability_score(
            bloom_prob=bloom_prob,
            do_saturation=do_sat_pct,
            trophic_state=trophic,
            succession=succ,
        )

        rec_pot = recovery_potential(
            do_mg_l=do_mg_l,
            orp_mv=orp_mv,
            bloom_probability=bloom_prob,
            residence_time_days=rt_days,
        )

        # ---- Bloom probability trend ----
        if lagoon_id not in self._bloom_history:
            self._bloom_history[lagoon_id] = deque(maxlen=_HISTORY_WINDOW)
        hist = self._bloom_history[lagoon_id]
        hist.append(bloom_prob)
        bloom_trend = _compute_trend(list(hist))

        # ---- Fish kill risk ----
        fish_risk: str
        if do_mg_l is not None:
            if do_mg_l < 1.0:
                fish_risk = "critical"
            elif do_mg_l < 2.0:
                fish_risk = "high"
            elif do_mg_l < 3.0:
                fish_risk = "medium"
            else:
                fish_risk = "low"
        else:
            fish_risk = "unknown"

        # ---- Toxin risk (microcystin proxy from cyanobacteria advantage + bloom prob) ----
        toxin_score = bloom_prob * 0.6 + cyano_adv * 0.4
        if toxin_score >= 0.7:
            toxin_risk = "high"
        elif toxin_score >= 0.4:
            toxin_risk = "medium"
        else:
            toxin_risk = "low"

        # ---- Additional observations ----
        if phyco is not None and phyco > 100:
            notes.append(f"Phycocyanin elevated ({phyco:.0f} RFU) — cyanobacteria presence confirmed")
        if secchi is not None and secchi < 0.5:
            notes.append(f"Secchi depth critically low ({secchi:.1f} m) — severe turbidity/algae")

        # ---- Data completeness ----
        available = [tp_mg_l, tn_mg_l, do_mg_l, orp_mv, temp_c, rt_days, chl_a]
        present = sum(1 for v in available if v is not None)
        completeness = present / len(available)

        confidence = round(completeness * 0.8 + (0.2 if chl_a is not None else 0.0), 3)
        confidence = min(confidence, 1.0)

        state = EcologicalState(
            lagoon_id=lagoon_id,
            timestamp=datetime.now(tz=UTC),
            bloom_probability=bloom_prob,
            bloom_probability_trend=bloom_trend,
            cyanobacteria_advantage=cyano_adv,
            succession_stage=succ,
            ecological_stability_score=eco_stability,
            recovery_potential=rec_pot,
            trophic_state=trophic,
            chlorophyll_a_ug_l=chl_a,
            phycocyanin_rfu=phyco,
            secchi_depth_m=secchi,
            macrophyte_cover_pct=macrophyte,
            fish_kill_risk=fish_risk,
            toxin_risk=toxin_risk,
            historical_bloom_count=hist_count,
            data_completeness_pct=round(completeness * 100, 1),
            confidence=confidence,
            notes=notes,
        )
        return state.to_dict()

    async def publish_state(self, lagoon_id: UUID) -> None:
        state_dict = await self.compute_state(lagoon_id)
        key = f"eco:{lagoon_id}"
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(key, state_dict, ttl_seconds=900)
            except Exception as exc:
                logger.warning("Shared memory write failed for %s: %s", key, exc)
        if self._event_bus is not None:
            try:
                await self._event_bus.publish(
                    topic="scientific.ecological.state",
                    payload={"lagoon_id": str(lagoon_id), "state": state_dict},
                )
            except Exception as exc:
                logger.warning("Event bus publish failed for %s: %s", lagoon_id, exc)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            try:
                lagoon_ids = list(self._sensor_cache.keys())
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
                        logger.error("EcologicalService loop error for %s: %s", lagoon_id, exc)
                        self._error_count += 1

                self._last_run = datetime.now(tz=UTC)
                self._run_count += 1

            except Exception as exc:
                logger.error("EcologicalService loop unhandled error: %s", exc)
                self._status = ServiceStatus.ERROR
                self._error_count += 1
            finally:
                await asyncio.sleep(self._interval_seconds)


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _compute_trend(history: list[float]) -> str:
    """Compute simple linear trend direction from a list of values."""
    n = len(history)
    if n < 3:
        return "stable"
    # Simple least-squares slope
    x_mean = (n - 1) / 2.0
    y_mean = sum(history) / n
    numerator = sum((i - x_mean) * (history[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return "stable"
    slope = numerator / denominator
    if slope > 0.005:
        return "increasing"
    elif slope < -0.005:
        return "decreasing"
    return "stable"
