"""Compliance service — continuous environmental standards evaluation.

Evaluates current lagoon conditions against UAE Environmental Agency limits,
permit conditions, and internal KPIs. Publishes compliance status and alerts.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ..base import ScientificService, ServiceStatus
from .models import (
    ComplianceLevel,
    ComplianceStatus,
    ComplianceViolation,
    ParameterCompliance,
)

logger = logging.getLogger(__name__)

# ── Regulatory limits (UAE Environmental Agency, lagoon operational standards) ──
# All limits represent operational thresholds for an enclosed water body.
_LIMITS: dict[str, dict[str, Any]] = {
    "do_mg_l": {
        "limit_type": "min",
        "limit_value": 4.0,
        "critical_value": 2.0,
        "unit": "mg/L",
        "standard": "UAE EA — Aquatic Ecosystem Protection",
    },
    "ph": {
        "limit_type": "range",
        "limit_min": 6.5,
        "limit_max": 9.0,
        "warning_min": 7.0,
        "warning_max": 8.5,
        "unit": "pH",
        "standard": "UAE EA — Aquatic Ecosystem Protection",
    },
    "turbidity_ntu": {
        "limit_type": "max",
        "limit_value": 50.0,
        "warning_value": 20.0,
        "unit": "NTU",
        "standard": "Internal KPI",
    },
    "tss_mg_l": {
        "limit_type": "max",
        "limit_value": 100.0,
        "warning_value": 50.0,
        "unit": "mg/L",
        "standard": "UAE EA — Discharge Standards",
    },
    "tn_mg_l": {
        "limit_type": "max",
        "limit_value": 10.0,
        "warning_value": 5.0,
        "unit": "mg/L",
        "standard": "UAE EA — Nutrient Standards",
    },
    "tp_mg_l": {
        "limit_type": "max",
        "limit_value": 1.0,
        "warning_value": 0.5,
        "unit": "mg/L",
        "standard": "UAE EA — Nutrient Standards",
    },
    "orp_mv": {
        "limit_type": "min",
        "limit_value": -100.0,
        "critical_value": -200.0,
        "unit": "mV",
        "standard": "Internal KPI — Anoxia Prevention",
    },
    "conductivity_us_cm": {
        "limit_type": "max",
        "limit_value": 8000.0,
        "warning_value": 5000.0,
        "unit": "µS/cm",
        "standard": "Internal KPI",
    },
}


class ComplianceService(ScientificService):
    """Continuous compliance monitoring against environmental standards.

    Loop interval: configurable (default 600 s / 10 min).
    """

    service_name = "compliance"
    loop_name = "compliance_monitoring_loop"

    def __init__(
        self,
        shared_memory: Any,
        event_bus: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._shared_memory = shared_memory
        self._event_bus = event_bus
        self._config = config or {}
        self._interval_seconds: float = float(self._config.get("interval_seconds", 600))
        self._running = False
        self._task: asyncio.Task | None = None
        self._status = ServiceStatus.INITIALIZING
        # Override limits from config if provided
        self._limits: dict[str, dict[str, Any]] = {
            **_LIMITS,
            **self._config.get("custom_limits", {}),
        }

    async def start(self) -> None:
        logger.info("ComplianceService starting (interval=%.0fs)", self._interval_seconds)
        self._running = True
        self._status = ServiceStatus.RUNNING
        self._task = asyncio.create_task(self._run_loop(), name="compliance_loop")

    async def stop(self) -> None:
        logger.info("ComplianceService stopping")
        self._running = False
        self._status = ServiceStatus.STOPPED
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def health(self) -> dict[str, Any]:
        return {
            "service": self.service_name,
            "status": self._status.value,
            "interval_seconds": self._interval_seconds,
        }

    async def process_event(self, event: Any) -> None:
        pass

    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]:
        status = await self.evaluate_lagoon(lagoon_id)
        return status.to_dict()

    async def publish_state(self, lagoon_id: UUID) -> None:
        if self._shared_memory is None:
            return
        status = await self.evaluate_lagoon(lagoon_id)
        with contextlib.suppress(Exception):
            await self._shared_memory.set(
                lagoon_id, "working", "compliance", "latest_status", status.to_dict()
            )

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._evaluate_all_lagoons()
            except Exception as exc:
                logger.error("ComplianceService loop error: %s", exc)
            await asyncio.sleep(self._interval_seconds)

    async def _evaluate_all_lagoons(self) -> None:
        if self._shared_memory is None:
            return
        try:
            lagoon_ids = await self._shared_memory.get_active_lagoon_ids()
        except Exception:
            return
        for lagoon_id in lagoon_ids:
            with contextlib.suppress(Exception):
                await self.evaluate_lagoon(lagoon_id)

    async def evaluate_lagoon(self, lagoon_id: UUID) -> ComplianceStatus:
        now = datetime.now(tz=UTC)
        params: list[ParameterCompliance] = []
        violations: list[ComplianceViolation] = []

        # Fetch latest chemical state from shared memory
        state_data: dict[str, Any] = {}
        if self._shared_memory is not None:
            try:
                raw = await self._shared_memory.get(
                    lagoon_id, "working", "chemical", "latest_state"
                )
                if raw:
                    state_data = raw if isinstance(raw, dict) else {}
            except Exception:
                pass

        # Map shared-memory fields to limit parameter names
        measurements: dict[str, float | None] = {
            "do_mg_l": state_data.get("do_mg_l"),
            "ph": state_data.get("ph"),
            "turbidity_ntu": state_data.get("turbidity_ntu"),
            "tss_mg_l": state_data.get("tss_mg_l"),
            "tn_mg_l": state_data.get("tn_mg_l"),
            "tp_mg_l": state_data.get("tp_mg_l"),
            "orp_mv": state_data.get("orp_mv"),
            "conductivity_us_cm": state_data.get("conductivity_us_cm"),
        }

        available = sum(1 for v in measurements.values() if v is not None)
        data_completeness = (available / len(measurements)) * 100.0 if measurements else 0.0

        for param_key, value in measurements.items():
            if param_key not in self._limits:
                continue
            limit_cfg = self._limits[param_key]
            pc = self._evaluate_parameter(param_key, value, limit_cfg, now)
            params.append(pc)
            if pc.level in (ComplianceLevel.VIOLATION, ComplianceLevel.CRITICAL):
                violations.append(
                    ComplianceViolation(
                        parameter=param_key,
                        value=value or 0.0,
                        unit=limit_cfg["unit"],
                        limit_breached=limit_cfg.get("limit_value")
                        or limit_cfg.get("limit_max")
                        or limit_cfg.get("limit_min")
                        or 0.0,
                        level=pc.level,
                        description=self._violation_description(param_key, value, limit_cfg),
                        recommended_action=self._recommended_action(param_key, pc.level),
                        timestamp=now,
                    )
                )

        critical_count = sum(1 for p in params if p.level == ComplianceLevel.CRITICAL)
        violation_count = sum(1 for p in params if p.level == ComplianceLevel.VIOLATION)
        warning_count = sum(1 for p in params if p.level == ComplianceLevel.WARNING)

        if critical_count > 0:
            overall = ComplianceLevel.CRITICAL
        elif violation_count > 0:
            overall = ComplianceLevel.VIOLATION
        elif warning_count > 0:
            overall = ComplianceLevel.WARNING
        elif data_completeness < 30:
            overall = ComplianceLevel.UNKNOWN
        else:
            overall = ComplianceLevel.COMPLIANT

        confidence = min(1.0, data_completeness / 100.0)

        status = ComplianceStatus(
            lagoon_id=lagoon_id,
            timestamp=now,
            overall_level=overall,
            parameters=params,
            violations=violations,
            warnings_count=warning_count,
            violations_count=violation_count,
            critical_count=critical_count,
            do_compliance=next((p for p in params if p.parameter == "do_mg_l"), None),
            ph_compliance=next((p for p in params if p.parameter == "ph"), None),
            turbidity_compliance=next(
                (p for p in params if p.parameter == "turbidity_ntu"), None
            ),
            nutrient_compliance=next((p for p in params if p.parameter == "tn_mg_l"), None),
            confidence=confidence,
            data_completeness_pct=data_completeness,
        )

        # Persist to shared memory
        if self._shared_memory is not None:
            with contextlib.suppress(Exception):
                await self._shared_memory.set(
                    lagoon_id, "working", "compliance", "latest_status", status.to_dict()
                )

        # Publish violation events
        if violations and self._event_bus is not None:
            for violation in violations:
                with contextlib.suppress(Exception):
                    await self._event_bus.publish(
                        topic=f"compliance.{'critical' if violation.level == ComplianceLevel.CRITICAL else 'violation'}",
                        payload={
                            "lagoon_id": str(lagoon_id),
                            "violation": violation.to_dict(),
                        },
                        priority="high" if violation.level == ComplianceLevel.CRITICAL else "normal",
                    )

        if overall not in (ComplianceLevel.COMPLIANT, ComplianceLevel.UNKNOWN):
            logger.warning(
                "Compliance %s: lagoon=%s violations=%d critical=%d",
                overall.value, lagoon_id, violation_count, critical_count
            )

        return status

    def _evaluate_parameter(
        self,
        name: str,
        value: float | None,
        cfg: dict[str, Any],
        now: datetime,
    ) -> ParameterCompliance:
        if value is None:
            return ParameterCompliance(
                parameter=name,
                value=None,
                unit=cfg["unit"],
                limit_type=cfg["limit_type"],
                limit_value=cfg.get("limit_value"),
                limit_max=cfg.get("limit_max"),
                limit_min=cfg.get("limit_min"),
                level=ComplianceLevel.UNKNOWN,
                standard=cfg.get("standard", ""),
            )

        limit_type = cfg["limit_type"]
        level = ComplianceLevel.COMPLIANT
        margin_pct: float | None = None

        if limit_type == "min":
            limit = cfg["limit_value"]
            critical = cfg.get("critical_value")
            if critical is not None and value <= critical:
                level = ComplianceLevel.CRITICAL
            elif value < limit:
                level = ComplianceLevel.VIOLATION
            margin_pct = ((value - limit) / abs(limit)) * 100.0 if limit != 0 else None

        elif limit_type == "max":
            limit = cfg["limit_value"]
            warning = cfg.get("warning_value")
            if value > limit:
                level = ComplianceLevel.VIOLATION
            elif warning is not None and value > warning:
                level = ComplianceLevel.WARNING
            margin_pct = ((limit - value) / limit) * 100.0 if limit != 0 else None

        elif limit_type == "range":
            lo = cfg["limit_min"]
            hi = cfg["limit_max"]
            warn_lo = cfg.get("warning_min", lo)
            warn_hi = cfg.get("warning_max", hi)
            if value < lo or value > hi:
                level = ComplianceLevel.VIOLATION
            elif value < warn_lo or value > warn_hi:
                level = ComplianceLevel.WARNING
            mid = (lo + hi) / 2.0
            margin_pct = ((hi - abs(value - mid)) / (hi - mid)) * 100.0 if hi != mid else None

        return ParameterCompliance(
            parameter=name,
            value=value,
            unit=cfg["unit"],
            limit_type=limit_type,
            limit_value=cfg.get("limit_value"),
            limit_max=cfg.get("limit_max"),
            limit_min=cfg.get("limit_min"),
            level=level,
            margin_pct=margin_pct,
            standard=cfg.get("standard", ""),
        )

    @staticmethod
    def _violation_description(
        param: str, value: float | None, cfg: dict[str, Any]
    ) -> str:
        limit = cfg.get("limit_value") or cfg.get("limit_max") or cfg.get("limit_min")
        return (
            f"{param} measured {value:.2f} {cfg['unit']} "
            f"breaches limit of {limit} {cfg['unit']} "
            f"({cfg.get('standard', 'internal standard')})"
        )

    @staticmethod
    def _recommended_action(param: str, level: ComplianceLevel) -> str:
        actions = {
            "do_mg_l": "Increase aeration immediately; inspect aerators for faults.",
            "ph": "Check chemical dosing system; test for incoming influent pH shock.",
            "turbidity_ntu": "Inspect inlet baffles; check for resuspension events.",
            "tss_mg_l": "Review sediment disturbance; reduce inflow velocity.",
            "tn_mg_l": "Reduce nitrogen loading; increase hydraulic flushing.",
            "tp_mg_l": "Review phosphorus inputs; assess chemical precipitation.",
            "orp_mv": "Increase aeration; check for anaerobic sediment layer.",
            "conductivity_us_cm": "Assess salinity inputs; review TSE quality.",
        }
        prefix = "URGENT: " if level == ComplianceLevel.CRITICAL else ""
        return prefix + actions.get(param, "Investigate and report to operations team.")
