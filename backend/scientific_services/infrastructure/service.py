"""
Infrastructure service — continuous monitoring of pumps, aeration, and maintenance.

Tracks equipment health, aeration capacity, maintenance schedules,
and publishes InfrastructureState.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from ..base import ScientificService, ServiceStatus
from .models import (
    AeratorState,
    EquipmentStatus,
    InfrastructureState,
    MaintenanceItem,
    MaintenancePriority,
    PumpState,
)

logger = logging.getLogger(__name__)


class InfrastructureService(ScientificService):
    """
    Continuous infrastructure state monitoring and health assessment.

    Loop interval: configurable (default 60 s / 1 min — equipment state changes fast).
    """

    service_name = "infrastructure"
    loop_name = "equipment_health_loop"

    def __init__(
        self,
        shared_memory: Any,
        event_bus: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._shared_memory = shared_memory
        self._event_bus = event_bus
        self._config = config or {}
        self._interval_seconds: float = float(self._config.get("interval_seconds", 60))
        self._running = False
        self._task: asyncio.Task | None = None
        # Per-lagoon equipment registry and telemetry cache
        self._equipment_registry: dict[UUID, dict[str, Any]] = {}
        self._telemetry_cache: dict[str, dict[str, Any]] = {}  # equipment_id → latest
        self._status = ServiceStatus.INITIALIZING

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        logger.info("InfrastructureService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="infra_loop")
        if self._event_bus is not None:
            for topic in (
                "telemetry.pump",
                "telemetry.aerator",
                "event.equipment_alarm",
                "event.maintenance_completed",
                "config.equipment_registered",
            ):
                await self._event_bus.subscribe(topic, self.process_event)

    async def stop(self) -> None:
        logger.info("InfrastructureService stopping")
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
            topic: str = event.get("topic", "")
            data: dict[str, Any] = event.get("data", {})
            equipment_id: str = str(data.get("equipment_id", ""))

            if "config.equipment_registered" in topic:
                lagoon_id = UUID(str(event["lagoon_id"]))
                if lagoon_id not in self._equipment_registry:
                    self._equipment_registry[lagoon_id] = {"pumps": [], "aerators": []}
                eq_type = data.get("type", "pump")
                self._equipment_registry[lagoon_id][eq_type + "s"].append(data)
                return

            if "event.maintenance_completed" in topic and equipment_id:
                if equipment_id in self._telemetry_cache:
                    self._telemetry_cache[equipment_id]["hours_since_service"] = 0.0
                    self._telemetry_cache[equipment_id]["maintenance_due"] = False
                return

            if "event.equipment_alarm" in topic and equipment_id:
                if equipment_id not in self._telemetry_cache:
                    self._telemetry_cache[equipment_id] = {}
                self._telemetry_cache[equipment_id]["alarm"] = data.get("alarm_type", "unknown")
                self._telemetry_cache[equipment_id]["status"] = EquipmentStatus.DEGRADED.value

            if equipment_id:
                if equipment_id not in self._telemetry_cache:
                    self._telemetry_cache[equipment_id] = {}
                cache = self._telemetry_cache[equipment_id]
                float_fields = [
                    "flow_rate_m3_hr", "efficiency_pct", "power_kw",
                    "hours_since_service", "vibration_mm_s", "temperature_c",
                    "oxygen_transfer_rate_kg_hr", "do_at_outlet_mg_l",
                ]
                for field in float_fields:
                    if field in data:
                        cache[field] = float(data[field])
                if "status" in data:
                    cache["status"] = data["status"]
                if "lagoon_id" in event:
                    cache["lagoon_id"] = str(event["lagoon_id"])
                cache["last_ts"] = datetime.now(tz=UTC).isoformat()

        except Exception as exc:
            logger.warning("InfrastructureService.process_event error: %s", exc)
            self._error_count += 1

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        registry = self._equipment_registry.get(lagoon_id, {})
        notes: list[str] = []

        pumps: list[PumpState] = []
        aerators: list[AeratorState] = []
        maintenance_items: list[MaintenanceItem] = []

        # ---- Process registered pumps ----
        for pump_def in registry.get("pumps", []):
            eq_id = pump_def.get("equipment_id", str(uuid4()))
            tel = self._telemetry_cache.get(eq_id, {})

            hours = tel.get("hours_since_service", 0.0)
            interval = float(pump_def.get("service_interval_hours", 2000.0))
            maintenance_due = hours >= interval

            status_str = tel.get("status", EquipmentStatus.UNKNOWN.value)
            try:
                status = EquipmentStatus(status_str)
            except ValueError:
                status = EquipmentStatus.UNKNOWN

            flow = tel.get("flow_rate_m3_hr")
            design_flow = float(pump_def.get("design_flow_rate_m3_hr", 100.0))
            efficiency = None
            if flow is not None and design_flow > 0:
                efficiency = round(flow / design_flow * 100, 1)

            vib = tel.get("vibration_mm_s")
            if vib is not None and vib > 4.5:
                notes.append(f"Pump {pump_def.get('name', eq_id)}: vibration {vib:.1f} mm/s exceeds 4.5 mm/s alarm threshold")
                status = EquipmentStatus.DEGRADED

            pump = PumpState(
                equipment_id=eq_id,
                name=pump_def.get("name", f"Pump {eq_id[:8]}"),
                status=status,
                flow_rate_m3_hr=flow,
                design_flow_rate_m3_hr=design_flow,
                efficiency_pct=efficiency,
                power_kw=tel.get("power_kw"),
                hours_since_service=hours,
                service_interval_hours=interval,
                vibration_mm_s=vib,
                temperature_c=tel.get("temperature_c"),
                maintenance_due=maintenance_due,
            )
            pumps.append(pump)

            if maintenance_due:
                overdue = max(0.0, (hours - interval) / 24.0)
                priority = (
                    MaintenancePriority.URGENT if overdue > 14
                    else MaintenancePriority.HIGH if overdue > 7
                    else MaintenancePriority.ROUTINE
                )
                maintenance_items.append(
                    MaintenanceItem(
                        item_id=str(uuid4()),
                        equipment_id=eq_id,
                        equipment_name=pump.name,
                        task="Scheduled pump service (oil, impeller, seals)",
                        priority=priority,
                        due_date=None,
                        overdue_by_days=overdue,
                        estimated_downtime_hours=4.0,
                    )
                )

        # ---- Process registered aerators ----
        for aer_def in registry.get("aerators", []):
            eq_id = aer_def.get("equipment_id", str(uuid4()))
            tel = self._telemetry_cache.get(eq_id, {})

            hours = tel.get("hours_since_service", 0.0)
            interval = float(aer_def.get("service_interval_hours", 4000.0))
            maintenance_due = hours >= interval

            status_str = tel.get("status", EquipmentStatus.UNKNOWN.value)
            try:
                status = EquipmentStatus(status_str)
            except ValueError:
                status = EquipmentStatus.UNKNOWN

            otr = tel.get("oxygen_transfer_rate_kg_hr")
            design_otr = float(aer_def.get("design_otr_kg_hr", 10.0))

            aerator = AeratorState(
                equipment_id=eq_id,
                name=aer_def.get("name", f"Aerator {eq_id[:8]}"),
                aeration_type=aer_def.get("aeration_type", "surface"),
                status=status,
                oxygen_transfer_rate_kg_hr=otr,
                design_otr_kg_hr=design_otr,
                power_kw=tel.get("power_kw"),
                coverage_area_m2=float(aer_def.get("coverage_area_m2", 500.0)),
                do_at_outlet_mg_l=tel.get("do_at_outlet_mg_l"),
                hours_since_service=hours,
                service_interval_hours=interval,
                maintenance_due=maintenance_due,
            )
            aerators.append(aerator)

            if maintenance_due:
                overdue = max(0.0, (hours - interval) / 24.0)
                maintenance_items.append(
                    MaintenanceItem(
                        item_id=str(uuid4()),
                        equipment_id=eq_id,
                        equipment_name=aerator.name,
                        task="Scheduled aerator service (bearings, diffusers, motor)",
                        priority=MaintenancePriority.ROUTINE if overdue < 7 else MaintenancePriority.HIGH,
                        due_date=None,
                        overdue_by_days=overdue,
                        estimated_downtime_hours=6.0,
                    )
                )

        # ---- Aggregate metrics ----
        total_aer_cap = sum(a.design_otr_kg_hr for a in aerators)
        active_aer = sum(
            (a.oxygen_transfer_rate_kg_hr or 0.0)
            for a in aerators
            if a.status == EquipmentStatus.OPERATIONAL
        )
        # Surface area coverage
        lagoon_area = 0.0
        if self._shared_memory is not None:
            try:
                hydro = await self._shared_memory.get(f"hydro:{lagoon_id}")
                if hydro:
                    lagoon_area = float(hydro.get("surface_area_m2") or 0.0)
            except Exception:
                pass
        covered_area = sum(a.coverage_area_m2 for a in aerators if a.status == EquipmentStatus.OPERATIONAL)
        aeration_coverage = (covered_area / lagoon_area * 100) if lagoon_area > 0 else 0.0

        total_circ = sum(p.design_flow_rate_m3_hr for p in pumps)
        active_circ = sum(
            (p.flow_rate_m3_hr or 0.0)
            for p in pumps
            if p.status == EquipmentStatus.OPERATIONAL
        )
        circ_eff = (active_circ / total_circ * 100) if total_circ > 0 else 0.0

        total_power = sum(
            (p.power_kw or 0.0) for p in pumps
        ) + sum(
            (a.power_kw or 0.0) for a in aerators
        )

        # ---- Infrastructure health score (0–1) ----
        all_equipment = len(pumps) + len(aerators)
        operational = sum(
            1 for p in pumps if p.status == EquipmentStatus.OPERATIONAL
        ) + sum(
            1 for a in aerators if a.status == EquipmentStatus.OPERATIONAL
        )
        operational_ratio = operational / all_equipment if all_equipment > 0 else 1.0
        overdue_count = len([m for m in maintenance_items if m.overdue_by_days > 0])
        overdue_penalty = min(overdue_count * 0.05, 0.3)
        health_score = round(max(0.0, operational_ratio - overdue_penalty), 3)

        # Energy efficiency (OTR/kW — higher is better, normalize to 0–1)
        energy_eff = 0.0
        if total_power > 0 and active_aer > 0:
            otr_per_kw = active_aer / total_power  # kg O2/hr per kW
            # Typical range: 1.2–2.4 kg/kWh for surface aerators
            energy_eff = round(min(otr_per_kw / 2.4, 1.0), 3)

        # Next maintenance due
        next_due: datetime | None = None
        if maintenance_items:
            nearest = min(
                maintenance_items,
                key=lambda m: m.overdue_by_days if m.overdue_by_days > 0 else -m.overdue_by_days,
            )
            if nearest.overdue_by_days > 0:
                next_due = datetime.now(tz=UTC) - timedelta(days=nearest.overdue_by_days)
            else:
                next_due = datetime.now(tz=UTC)

        confidence = 0.7 if all_equipment > 0 else 0.2
        if len(self._telemetry_cache) > 0:
            confidence = min(confidence + 0.2, 1.0)

        state = InfrastructureState(
            lagoon_id=lagoon_id,
            timestamp=datetime.now(tz=UTC),
            pumps=pumps,
            aerators=aerators,
            total_aeration_capacity_kg_hr=total_aer_cap,
            active_aeration_kg_hr=active_aer,
            aeration_coverage_pct=round(aeration_coverage, 1),
            total_circulation_m3_hr=total_circ,
            active_circulation_m3_hr=active_circ,
            circulation_efficiency_pct=round(circ_eff, 1),
            maintenance_items=maintenance_items,
            overdue_maintenance_count=overdue_count,
            next_maintenance_due=next_due,
            infrastructure_health_score=health_score,
            total_power_consumption_kw=round(total_power, 2),
            energy_efficiency_score=energy_eff,
            confidence=confidence,
            notes=notes,
        )
        return state.to_dict()

    async def publish_state(self, lagoon_id: UUID) -> None:
        state_dict = await self.compute_state(lagoon_id)
        key = f"infra:{lagoon_id}"
        if self._shared_memory is not None:
            try:
                await self._shared_memory.set(key, state_dict, ttl_seconds=120)
            except Exception as exc:
                logger.warning("Shared memory write failed for %s: %s", key, exc)
        if self._event_bus is not None:
            try:
                await self._event_bus.publish(
                    topic="scientific.infrastructure.state",
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
                lagoon_ids = list(self._equipment_registry.keys())
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
                        logger.error("InfrastructureService loop error for %s: %s", lagoon_id, exc)
                        self._error_count += 1

                self._last_run = datetime.now(tz=UTC)
                self._run_count += 1

            except Exception as exc:
                logger.error("InfrastructureService loop unhandled error: %s", exc)
                self._status = ServiceStatus.ERROR
                self._error_count += 1
            finally:
                await asyncio.sleep(self._interval_seconds)
