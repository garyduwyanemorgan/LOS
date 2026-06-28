"""
Chemical service — continuous water quality computation for each lagoon.

Subscribes to water quality sensor events, computes ChemicalState,
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
    carbonate_system,
    do_saturation_percent,
    internal_loading_risk,
    nitrogen_speciation,
    nutrient_trophic_state,
    redox_classification,
    solubility_product_check,
)
from .models import ChemicalState

logger = logging.getLogger(__name__)

# Core parameters for data completeness scoring
_CORE_PARAMS = [
    "ph", "do_mg_l", "orp_mv", "temperature_c", "conductivity_us_cm",
    "tn_mg_l", "tp_mg_l", "nh4_mg_l",
]


class ChemicalService(ScientificService):
    """
    Continuous chemical / water quality state estimation service.

    Loop interval: configurable (default 300 s / 5 min).
    """

    service_name = "chemical"
    loop_name = "water_quality_loop"

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
        self._sensor_cache: dict[UUID, dict[str, Any]] = {}
        self._status = ServiceStatus.INITIALIZING

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("ChemicalService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="chem_loop")
        if self._event_bus is not None:
            for topic in (
                "sensor.water_quality",
                "sensor.nutrients",
                "sensor.ions",
                "sensor.do",
                "sensor.ph",
                "sensor.orp",
            ):
                await self._event_bus.subscribe(topic, self.process_event)

    async def stop(self) -> None:
        logger.info("ChemicalService stopping")
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

            if lagoon_id not in self._sensor_cache:
                self._sensor_cache[lagoon_id] = {}
            cache = self._sensor_cache[lagoon_id]

            # Direct pass-through for all numeric fields present in event data
            float_fields = [
                "ph", "do_mg_l", "orp_mv", "conductivity_us_cm", "temperature_c",
                "turbidity_ntu", "salinity_ppt",
                "tn_mg_l", "tp_mg_l", "nh4_mg_l", "no3_mg_l", "no2_mg_l",
                "po4_mg_l", "toc_mg_l", "bod5_mg_l", "cod_mg_l",
                "chlorophyll_a_ug_l",
                "alkalinity_meq_l", "ca_mg_l", "mg_mg_l", "na_mg_l",
                "cl_mg_l", "so4_mg_l",
            ]
            for field in float_fields:
                if field in data:
                    cache[field] = float(data[field])

            cache["last_event_ts"] = datetime.now(tz=UTC).isoformat()

        except Exception as exc:
            logger.warning("ChemicalService.process_event error: %s", exc)
            self._error_count += 1

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        cache = self._sensor_cache.get(lagoon_id, {})
        notes: list[str] = []

        # ---- Extract sensor values ----
        ph = cache.get("ph")
        do_mg_l = cache.get("do_mg_l")
        orp_mv = cache.get("orp_mv")
        temp_c = cache.get("temperature_c")
        salinity_ppt = cache.get("salinity_ppt", 0.0)
        conductivity = cache.get("conductivity_us_cm")
        turbidity = cache.get("turbidity_ntu")

        # Nutrients
        tn = cache.get("tn_mg_l")
        tp = cache.get("tp_mg_l")
        nh4 = cache.get("nh4_mg_l")
        no3 = cache.get("no3_mg_l")
        no2 = cache.get("no2_mg_l")
        po4 = cache.get("po4_mg_l")
        toc = cache.get("toc_mg_l")
        bod5 = cache.get("bod5_mg_l")
        cod = cache.get("cod_mg_l")
        chl_a = cache.get("chlorophyll_a_ug_l")

        # Ions
        alkalinity = cache.get("alkalinity_meq_l")
        ca = cache.get("ca_mg_l")
        mg = cache.get("mg_mg_l")
        na = cache.get("na_mg_l")
        cl = cache.get("cl_mg_l")
        so4 = cache.get("so4_mg_l")

        # ---- Derived calculations ----
        do_sat_pct: float | None = None
        if do_mg_l is not None and temp_c is not None:
            do_sat_pct = do_saturation_percent(do_mg_l, temp_c, salinity_ppt)

        redox: str | None = None
        if orp_mv is not None:
            redox = redox_classification(orp_mv)

        # Estimate salinity from conductivity if not measured
        if salinity_ppt == 0.0 and conductivity is not None:
            # Approximate: 1 ppt ≈ 1550 µS/cm for typical lagoon water
            salinity_ppt = conductivity / 1550.0
            notes.append("Salinity estimated from conductivity")

        # Internal loading risk
        il_risk: str | None = None
        if orp_mv is not None:
            # Fetch residence time from shared memory if available
            rt_days: float = 14.0  # conservative default
            if self._shared_memory is not None:
                try:
                    hydro = await self._shared_memory.get(f"hydro:{lagoon_id}")
                    if hydro and hydro.get("residence_time_days"):
                        rt_days = float(hydro["residence_time_days"])
                except Exception:
                    pass
            il_risk = internal_loading_risk(orp_mv, rt_days, tp)

        # Trophic state
        trophic = nutrient_trophic_state(tn, tp, chl_a)

        # Carbonate system
        hco3: float | None = None
        co3: float | None = None
        co2_aq: float | None = None
        tic: float | None = None
        lsi: float | None = None
        if ph is not None and alkalinity is not None:
            carb = carbonate_system(ph, alkalinity, temp_c or 25.0)
            hco3 = carb["HCO3_mg_l"]
            co3 = carb["CO3_mg_l"]
            co2_aq = carb["CO2_mg_l"]
            tic = carb["TIC_mg_l"]
            if ca is not None and co3 is not None:
                lsi_dict = solubility_product_check(ca, co3, temp_c or 25.0)
                lsi = lsi_dict["LSI"]

        # Free ammonia speciation
        nh3: float | None = None
        if nh4 is not None and ph is not None and temp_c is not None:
            spec = nitrogen_speciation(nh4, ph, temp_c)
            nh3 = spec["NH3_mg_l"]
            if spec["toxic_threshold_exceeded"]:
                notes.append(f"Free ammonia NH3 = {nh3:.3f} mg/L exceeds 0.02 mg/L toxicity threshold")

        # Estimate TN from components if not measured
        if tn is None and all(v is not None for v in (nh4, no3)):
            tn_est = (nh4 or 0.0) + (no3 or 0.0) + (no2 or 0.0)
            tn = tn_est
            notes.append("TN estimated as NH4+NO3+NO2 (TKN not measured)")

        # ---- Data completeness ----
        param_vals = {p: cache.get(p) for p in _CORE_PARAMS}
        present = sum(1 for v in param_vals.values() if v is not None)
        completeness = present / len(_CORE_PARAMS)

        # ---- Confidence ----
        confidence = completeness * 0.8
        if ph is not None and do_mg_l is not None and orp_mv is not None:
            confidence = min(confidence + 0.2, 1.0)
        confidence = round(confidence, 3)

        state = ChemicalState(
            lagoon_id=lagoon_id,
            timestamp=datetime.now(tz=UTC),
            ph=ph,
            do_mg_l=do_mg_l,
            do_saturation_pct=do_sat_pct,
            orp_mv=orp_mv,
            redox_class=redox,
            conductivity_us_cm=conductivity,
            temperature_c=temp_c,
            turbidity_ntu=turbidity,
            salinity_ppt=salinity_ppt if salinity_ppt != 0.0 else None,
            tn_mg_l=tn,
            tp_mg_l=tp,
            nh4_mg_l=nh4,
            nh3_mg_l=nh3,
            no3_mg_l=no3,
            no2_mg_l=no2,
            po4_mg_l=po4,
            toc_mg_l=toc,
            bod5_mg_l=bod5,
            cod_mg_l=cod,
            trophic_state=trophic,
            internal_loading_risk=il_risk,
            chlorophyll_a_ug_l=chl_a,
            alkalinity_meq_l=alkalinity,
            hco3_mg_l=hco3,
            co3_mg_l=co3,
            co2_mg_l=co2_aq,
            tic_mg_l=tic,
            langelier_index=lsi,
            ca_mg_l=ca,
            mg_mg_l=mg,
            na_mg_l=na,
            cl_mg_l=cl,
            so4_mg_l=so4,
            data_completeness_pct=round(completeness * 100, 1),
            confidence=confidence,
            notes=notes,
        )
        return state.to_dict()

    async def publish_state(self, lagoon_id: UUID) -> None:
        state_dict = await self.compute_state(lagoon_id)
        key = f"chem:{lagoon_id}"
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(key, state_dict, ttl_seconds=900)
            except Exception as exc:
                logger.warning("Shared memory write failed for %s: %s", key, exc)
        if self._event_bus is not None:
            try:
                await self._event_bus.publish(
                    topic="scientific.chemical.state",
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
                        logger.error("ChemicalService loop error for %s: %s", lagoon_id, exc)
                        self._error_count += 1

                self._last_run = datetime.now(tz=UTC)
                self._run_count += 1

            except Exception as exc:
                logger.error("ChemicalService loop unhandled error: %s", exc)
                self._status = ServiceStatus.ERROR
                self._error_count += 1
            finally:
                await asyncio.sleep(self._interval_seconds)
