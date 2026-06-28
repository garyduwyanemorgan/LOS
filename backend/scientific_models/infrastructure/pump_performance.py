"""Pump performance model.

Evaluates pump operation against rated characteristic curves.
Detects efficiency degradation, cavitation risk, and impending failure.

Reference:
  Hydraulic Institute Standards, 14th Edition — Pump Performance Testing.
  Europump & Hydraulic Institute — Variable Speed Pumping Guide.
"""
from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from ..base import ScientificModel, ModelOutput


class PumpPerformanceModel(ScientificModel):
    """Evaluate pump performance relative to rated duty point.

    Inputs:
        flow_rate_m3_h: Measured flow rate (m³/h)
        head_m: Measured total dynamic head (m)
        power_input_kw: Electrical power input (kW)
        speed_rpm: Shaft speed (RPM), if variable speed
        rated_flow_m3_h: Rated flow at best efficiency point (m³/h)
        rated_head_m: Rated head at best efficiency point (m)
        rated_power_kw: Rated shaft power at BEP (kW)
        rated_speed_rpm: Rated speed at BEP (RPM)
        impeller_diameter_mm: Impeller diameter (mm), for affinity law correction
        fluid_density_kg_m3: Fluid density (default 1000 kg/m³ for fresh water)

    Outputs:
        hydraulic_efficiency_pct: η_hydraulic as % of rated BEP efficiency
        wire_to_water_efficiency_pct: Overall wire-to-water efficiency (%)
        flow_deviation_pct: % deviation of flow from rated duty
        head_deviation_pct: % deviation of head from rated duty
        performance_index: 0–1 score (1 = perfect BEP operation)
        cavitation_risk: "low", "moderate", "high"
        degradation_flag: True if performance has degraded >15% from rated
        affinity_corrected_flow_m3_h: Flow corrected for speed deviation
    """

    model_name = "pump_performance"
    model_version = "1.0.0"

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        import time
        t0 = time.perf_counter()

        warnings: list[str] = []
        errors: list[str] = []
        values: dict[str, Any] = {}

        flow = inputs.get("flow_rate_m3_h")
        head = inputs.get("head_m")
        power_in = inputs.get("power_input_kw")
        speed = inputs.get("speed_rpm")

        rated_flow = inputs.get("rated_flow_m3_h")
        rated_head = inputs.get("rated_head_m")
        rated_power = inputs.get("rated_power_kw")
        rated_speed = inputs.get("rated_speed_rpm")

        density = float(inputs.get("fluid_density_kg_m3", 1000.0))
        g = 9.81  # m/s²

        # ── Affinity law correction for speed deviation ──────────────────────
        affinity_flow: float | None = None
        if flow is not None and speed is not None and rated_speed is not None and rated_speed > 0:
            speed_ratio = speed / rated_speed
            affinity_flow = flow / speed_ratio if speed_ratio > 0 else None
            if affinity_flow is not None:
                values["affinity_corrected_flow_m3_h"] = round(affinity_flow, 3)
                values["speed_ratio"] = round(speed_ratio, 4)

        effective_flow = affinity_flow if affinity_flow is not None else flow

        # ── Flow and head deviation from rated duty ──────────────────────────
        if effective_flow is not None and rated_flow is not None and rated_flow > 0:
            flow_dev = ((effective_flow - rated_flow) / rated_flow) * 100.0
            values["flow_deviation_pct"] = round(flow_dev, 2)

        if head is not None and rated_head is not None and rated_head > 0:
            head_dev = ((head - rated_head) / rated_head) * 100.0
            values["head_deviation_pct"] = round(head_dev, 2)

        # ── Hydraulic power and efficiency ───────────────────────────────────
        if flow is not None and head is not None:
            # P_hydraulic = ρ·g·Q·H  (convert m³/h → m³/s)
            q_m3_s = flow / 3600.0
            p_hydraulic_kw = (density * g * q_m3_s * head) / 1000.0
            values["hydraulic_power_kw"] = round(p_hydraulic_kw, 3)

            if power_in is not None and power_in > 0:
                wire_to_water = (p_hydraulic_kw / power_in) * 100.0
                values["wire_to_water_efficiency_pct"] = round(wire_to_water, 2)

                # Rated wire-to-water at BEP (estimated from rated inputs)
                if (rated_flow is not None and rated_head is not None
                        and rated_power is not None and rated_power > 0):
                    q_rated = rated_flow / 3600.0
                    p_hydraulic_rated = (density * g * q_rated * rated_head) / 1000.0
                    rated_ww = (p_hydraulic_rated / rated_power) * 100.0
                    hydraulic_efficiency_pct = (wire_to_water / rated_ww) * 100.0
                    values["hydraulic_efficiency_pct"] = round(hydraulic_efficiency_pct, 2)
                    values["rated_wire_to_water_pct"] = round(rated_ww, 2)
                    degradation_flag = hydraulic_efficiency_pct < 85.0
                    values["degradation_flag"] = degradation_flag
                    if degradation_flag:
                        warnings.append(
                            f"Pump efficiency {hydraulic_efficiency_pct:.1f}% "
                            f"is >15% below rated; maintenance recommended."
                        )

        # ── Performance index (0–1) ──────────────────────────────────────────
        deviations: list[float] = []
        if "flow_deviation_pct" in values:
            deviations.append(abs(values["flow_deviation_pct"]) / 100.0)
        if "head_deviation_pct" in values:
            deviations.append(abs(values["head_deviation_pct"]) / 100.0)
        if deviations:
            mean_dev = sum(deviations) / len(deviations)
            performance_index = max(0.0, 1.0 - mean_dev)
            values["performance_index"] = round(performance_index, 3)

        # ── Cavitation risk assessment (simplified Thoma number proxy) ────────
        if flow is not None and rated_flow is not None and rated_flow > 0:
            flow_ratio = flow / rated_flow
            if flow_ratio > 1.2 or flow_ratio < 0.6:
                cavitation_risk = "high"
            elif flow_ratio > 1.1 or flow_ratio < 0.75:
                cavitation_risk = "moderate"
            else:
                cavitation_risk = "low"
            values["cavitation_risk"] = cavitation_risk
            if cavitation_risk == "high":
                warnings.append(
                    f"Pump operating at {flow_ratio:.2f}× rated flow — "
                    f"high cavitation risk; adjust operating point."
                )

        confidence = 1.0
        if not any(k in inputs for k in ("flow_rate_m3_h", "head_m", "power_input_kw")):
            errors.append("No performance measurements provided")
            confidence = 0.0
        else:
            missing_rated = [k for k in ("rated_flow_m3_h", "rated_head_m") if k not in inputs]
            if missing_rated:
                warnings.append(f"Rated duty data missing: {missing_rated}")
                confidence -= 0.3

        confidence = max(0.0, min(1.0, confidence - 0.1 * len(warnings)))
        runtime = time.perf_counter() - t0

        return self._make_output(
            lagoon_id=lagoon_id,
            values=values,
            diagnostics={"inputs_received": list(inputs.keys())},
            confidence=confidence,
            warnings=warnings,
            errors=errors,
            runtime_seconds=runtime,
        )
