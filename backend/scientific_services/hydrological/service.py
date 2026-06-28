"""
Hydrological service — continuous water balance computation for each lagoon.

Subscribes to sensor and weather events, computes HydrologicalState,
publishes to shared memory and event bus.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ..base import ScientificService, ServiceStatus
from .calculations import (
    darcy_groundwater_flux,
    hydraulic_connectivity_score,
    penman_monteith_reference_et,
    residence_time_days,
)
from .calculations import (
    water_balance_detailed as water_balance,
)
from .models import HydrologicalState

logger = logging.getLogger(__name__)

# Parameters that contribute equally to data completeness
_COMPLETENESS_PARAMS = [
    "water_level_m",
    "volume_m3",
    "inflow_m3_day",
    "outflow_m3_day",
    "evaporation_mm_day",
    "groundwater_flux_m3_day",
    "precipitation_mm_day",
    "surface_area_m2",
]


class HydrologicalService(ScientificService):
    """
    Continuous hydrological state estimation service.

    Loop interval: configurable (default 300 s / 5 min).
    """

    service_name = "hydrological"
    loop_name = "water_balance_loop"

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
        # Per-lagoon sensor caches: lagoon_id → latest values
        self._sensor_cache: dict[UUID, dict[str, Any]] = {}
        self._status = ServiceStatus.INITIALIZING

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the continuous water balance loop."""
        logger.info("HydrologicalService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="hydro_loop")
        # Subscribe to relevant event topics
        if self._event_bus is not None:
            await self._event_bus.subscribe("sensor.water_level", self.process_event)
            await self._event_bus.subscribe("sensor.flow", self.process_event)
            await self._event_bus.subscribe("sensor.weather", self.process_event)
            await self._event_bus.subscribe("sensor.groundwater", self.process_event)

    async def stop(self) -> None:
        """Gracefully stop the service."""
        logger.info("HydrologicalService stopping")
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
        """
        Process an incoming sensor event and update the sensor cache.

        Expected event schema:
          {
            "topic": "sensor.water_level" | "sensor.flow" | ...,
            "lagoon_id": "<uuid>",
            "timestamp": "<iso>",
            "data": { ... measurement fields ... }
          }
        """
        try:
            lagoon_id = UUID(str(event["lagoon_id"]))
            data: dict[str, Any] = event.get("data", {})
            topic: str = event.get("topic", "")

            if lagoon_id not in self._sensor_cache:
                self._sensor_cache[lagoon_id] = {}

            cache = self._sensor_cache[lagoon_id]

            if "sensor.water_level" in topic:
                if "value_m" in data:
                    cache["water_level_m"] = float(data["value_m"])
                if "volume_m3" in data:
                    cache["volume_m3"] = float(data["volume_m3"])
                if "surface_area_m2" in data:
                    cache["surface_area_m2"] = float(data["surface_area_m2"])

            elif "sensor.flow" in topic:
                if "inflow_m3_day" in data:
                    cache["inflow_m3_day"] = float(data["inflow_m3_day"])
                if "outflow_m3_day" in data:
                    cache["outflow_m3_day"] = float(data["outflow_m3_day"])

            elif "sensor.weather" in topic:
                if "precipitation_mm_day" in data:
                    cache["precipitation_mm_day"] = float(data["precipitation_mm_day"])
                if "evaporation_mm_day" in data:
                    cache["evaporation_mm_day"] = float(data["evaporation_mm_day"])
                if "temp_mean_c" in data:
                    cache["temp_mean_c"] = float(data["temp_mean_c"])
                if "temp_min_c" in data:
                    cache["temp_min_c"] = float(data["temp_min_c"])
                if "temp_max_c" in data:
                    cache["temp_max_c"] = float(data["temp_max_c"])
                if "relative_humidity_pct" in data:
                    cache["relative_humidity_pct"] = float(data["relative_humidity_pct"])
                if "wind_speed_2m_ms" in data:
                    cache["wind_speed_2m_ms"] = float(data["wind_speed_2m_ms"])
                if "solar_radiation_mj_m2_day" in data:
                    cache["solar_radiation_mj_m2_day"] = float(data["solar_radiation_mj_m2_day"])

            elif "sensor.groundwater" in topic:
                if "flux_m3_day" in data:
                    cache["groundwater_flux_m3_day"] = float(data["flux_m3_day"])
                if "hydraulic_gradient" in data:
                    cache["hydraulic_gradient"] = float(data["hydraulic_gradient"])

            cache["last_event_ts"] = datetime.now(tz=UTC).isoformat()

        except Exception as exc:
            logger.warning("HydrologicalService.process_event error: %s", exc)
            self._error_count += 1

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        """Compute current hydrological state from cached sensor data."""
        cache = self._sensor_cache.get(lagoon_id, {})
        notes: list[str] = []

        # ---- Extract available values ----
        water_level = cache.get("water_level_m")
        volume = cache.get("volume_m3")
        inflow = cache.get("inflow_m3_day")
        outflow = cache.get("outflow_m3_day")
        evaporation = cache.get("evaporation_mm_day")
        precipitation = cache.get("precipitation_mm_day", 0.0)
        surface_area = cache.get("surface_area_m2")
        gw_flux = cache.get("groundwater_flux_m3_day", 0.0)

        # ---- Attempt ET0 calculation from met data ----
        et0: float | None = None
        if all(
            k in cache
            for k in (
                "temp_mean_c",
                "temp_min_c",
                "temp_max_c",
                "relative_humidity_pct",
                "wind_speed_2m_ms",
                "solar_radiation_mj_m2_day",
            )
        ):
            try:
                et0 = penman_monteith_reference_et(
                    temp_mean_c=cache["temp_mean_c"],
                    temp_min_c=cache["temp_min_c"],
                    temp_max_c=cache["temp_max_c"],
                    relative_humidity_pct=cache["relative_humidity_pct"],
                    wind_speed_2m_ms=cache["wind_speed_2m_ms"],
                    solar_radiation_mj_m2_day=cache["solar_radiation_mj_m2_day"],
                )
                if evaporation is None:
                    evaporation = et0 * 1.05  # open water factor
                    notes.append("Evaporation estimated from Penman-Monteith ET0 × 1.05")
            except Exception as e:
                logger.debug("ET0 calculation failed: %s", e)

        # ---- Darcy flux if gradient available but no direct measurement ----
        if gw_flux == 0.0 and "hydraulic_gradient" in cache and surface_area is not None:
            K = self._config.get("hydraulic_conductivity_m_day", 0.5)
            gw_flux = darcy_groundwater_flux(
                hydraulic_conductivity_m_day=K,
                hydraulic_gradient=cache["hydraulic_gradient"],
                area_m2=surface_area * 0.1,  # 10% of surface area as seepage face
            )
            notes.append(f"Groundwater flux estimated via Darcy: {gw_flux:.2f} m³/day")

        # ---- Water balance ----
        delta_storage: float | None = None
        balance_error: float | None = None
        if all(v is not None for v in (inflow, outflow, surface_area)):
            delta_storage, balance_error = water_balance(
                inflow_m3_day=inflow,  # type: ignore[arg-type]
                outflow_m3_day=outflow,  # type: ignore[arg-type]
                precipitation_mm_day=precipitation,
                surface_area_m2=surface_area,  # type: ignore[arg-type]
                evaporation_mm_day=evaporation if evaporation is not None else 0.0,
                groundwater_flux_m3_day=gw_flux,
            )

        # ---- Residence time ----
        rt: float | None = None
        if volume is not None and outflow is not None:
            rt = residence_time_days(volume, outflow)

        # ---- Hydraulic connectivity score ----
        hc_score: float | None = None
        if all(v is not None for v in (inflow, volume, outflow)):
            inflow_var = min(abs(inflow) / max(abs(outflow), 1.0), 1.0) if outflow else 0.0  # type: ignore
            gw_frac = min(abs(gw_flux) / max(abs(inflow), 1.0), 1.0) if inflow else 0.0  # type: ignore
            rain_corr = min(precipitation / 10.0, 1.0) if precipitation else 0.0
            hc_score = hydraulic_connectivity_score(inflow_var, gw_frac, rain_corr)

        # ---- Data completeness ----
        available_params = {
            "water_level_m": water_level,
            "volume_m3": volume,
            "inflow_m3_day": inflow,
            "outflow_m3_day": outflow,
            "evaporation_mm_day": evaporation,
            "groundwater_flux_m3_day": gw_flux if gw_flux != 0.0 else None,
            "precipitation_mm_day": precipitation if precipitation != 0.0 else None,
            "surface_area_m2": surface_area,
        }
        present = sum(1 for v in available_params.values() if v is not None)
        completeness = present / len(available_params)

        # ---- Confidence: scales with completeness + balance error quality ----
        confidence = completeness * 0.7
        if balance_error is not None:
            confidence += (1.0 - min(balance_error / 100.0, 1.0)) * 0.3
        confidence = round(min(max(confidence, 0.0), 1.0), 3)

        if balance_error is not None and balance_error > 20:
            notes.append(f"High water balance error: {balance_error:.1f}% — check sensor calibration")

        state = HydrologicalState(
            lagoon_id=lagoon_id,
            timestamp=datetime.now(tz=UTC),
            water_level_m=water_level,
            volume_m3=volume,
            inflow_m3_day=inflow,
            outflow_m3_day=outflow,
            residence_time_days=rt,
            delta_storage_m3_day=delta_storage,
            evaporation_mm_day=evaporation,
            groundwater_flux_m3_day=gw_flux if gw_flux != 0.0 else None,
            hydraulic_connectivity_score=hc_score,
            water_balance_error_pct=balance_error,
            surface_area_m2=surface_area,
            et0_mm_day=et0,
            data_completeness_pct=round(completeness * 100, 1),
            confidence=confidence,
            notes=notes,
        )
        return state.to_dict()

    async def publish_state(self, lagoon_id: UUID) -> None:
        """Compute and publish hydrological state to shared memory and event bus."""
        state_dict = await self.compute_state(lagoon_id)

        key = f"hydro:{lagoon_id}"
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(key, state_dict, ttl_seconds=900)
            except Exception as exc:
                logger.warning("Shared memory write failed for %s: %s", key, exc)

        if self._event_bus is not None:
            try:
                await self._event_bus.publish(
                    topic="scientific.hydrological.state",
                    payload={"lagoon_id": str(lagoon_id), "state": state_dict},
                )
            except Exception as exc:
                logger.warning("Event bus publish failed for %s: %s", lagoon_id, exc)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Continuous loop — compute and publish state for all known lagoons."""
        while self._running:
            try:
                lagoon_ids = list(self._sensor_cache.keys())
                if not lagoon_ids and self._shared_memory is not None:
                    # Bootstrap from shared memory registry
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
                        logger.error("HydrologicalService loop error for %s: %s", lagoon_id, exc)
                        self._error_count += 1

                self._last_run = datetime.now(tz=UTC)
                self._run_count += 1

            except Exception as exc:
                logger.error("HydrologicalService loop unhandled error: %s", exc)
                self._status = ServiceStatus.ERROR
                self._error_count += 1
            finally:
                await asyncio.sleep(self._interval_seconds)
