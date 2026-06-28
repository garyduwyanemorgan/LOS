"""Aeration efficiency model.

Computes Standard Aeration Efficiency (SAE) and field aeration efficiency
for surface aerators in tropical lagoons under non-standard conditions.

Reference:
  ASCE 2-06: Measurement of Oxygen Transfer in Clean Water.
  Corrections to field conditions per Metcalf & Eddy (5th ed.) Eq. 8-51.
"""
from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from ..base import ScientificModel, ModelOutput

# Temperature correction factor for oxygen transfer (Arrhenius)
_THETA = 1.024

# Surface tension correction (field vs clean water — default for lagoon)
_OMEGA = 0.9

# Oxygen deficit correction denominator for standard conditions
_DO_SAT_STANDARD_MG_L = 9.07  # Clean water, 20°C, sea level

# Minimum sensible values
_MIN_POWER_KW = 0.01
_MIN_VOLUME_M3 = 1.0


class AerationEfficiencyModel(ScientificModel):
    """Compute field Standard Aeration Efficiency (SAE) and Oxygen Transfer Rate (OTR).

    Inputs (all optional — model returns partial outputs if data incomplete):
        do_sat_mg_l: Dissolved oxygen saturation at field temperature (mg/L)
        do_field_mg_l: Measured DO in lagoon (mg/L)
        temperature_c: Water temperature (°C)
        power_kw: Aerator power input (kW)
        volume_m3: Lagoon volume (m³)
        alpha: Process water correction factor (default 0.85)
        beta: Salinity correction factor (default 0.95)
        elevation_m: Site elevation above sea level (m, default 0)

    Outputs:
        sotr_kg_o2_h: Standard Oxygen Transfer Rate (kg O₂/h)
        otr_kg_o2_h: Field Oxygen Transfer Rate (kg O₂/h)
        sae_kg_o2_kwh: Standard Aeration Efficiency (kg O₂/kWh)
        oae_kg_o2_kwh: Field Aeration Efficiency (kg O₂/kWh)
        oxygen_deficit_mg_l: DO deficit (sat − field) mg/L
        alpha_factor: Alpha correction used
        beta_factor: Beta correction used
        do_deficit_ratio: Field DO deficit / standard DO deficit (dimensionless)
    """

    model_name = "aeration_efficiency"
    model_version = "1.0.0"

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        import time
        t0 = time.perf_counter()

        warnings: list[str] = []
        errors: list[str] = []

        do_sat = inputs.get("do_sat_mg_l")
        do_field = inputs.get("do_field_mg_l")
        temperature_c = inputs.get("temperature_c", 25.0)
        power_kw = inputs.get("power_kw")
        volume_m3 = inputs.get("volume_m3")
        alpha = float(inputs.get("alpha", 0.85))
        beta = float(inputs.get("beta", 0.95))
        elevation_m = float(inputs.get("elevation_m", 0.0))

        values: dict[str, Any] = {}

        # Pressure correction for elevation
        pressure_correction = math.exp(-elevation_m / 8400.0)

        # Temperature correction factor (Arrhenius) relative to 20°C
        temp_correction = _THETA ** (temperature_c - 20.0)

        # Compute DO saturation if not provided
        if do_sat is None:
            # Benson & Krause correlation (simplified)
            do_sat = (14.62 - 0.3898 * temperature_c
                      + 0.006969 * temperature_c ** 2
                      - 0.00005896 * temperature_c ** 3) * pressure_correction
            values["do_sat_computed_mg_l"] = round(do_sat, 3)
            warnings.append("do_sat_mg_l not provided; estimated from temperature")

        if do_field is None:
            warnings.append("do_field_mg_l not provided; deficit ratio not computed")
            deficit_ratio = None
            oxygen_deficit = None
        else:
            oxygen_deficit = max(0.0, do_sat - do_field)
            standard_deficit = _DO_SAT_STANDARD_MG_L - 0.0  # assume DO=0 for SOTR
            if _DO_SAT_STANDARD_MG_L > 0:
                deficit_ratio = (
                    alpha * (beta * do_sat - do_field)
                ) / (_DO_SAT_STANDARD_MG_L) * temp_correction
            else:
                deficit_ratio = None
            values["oxygen_deficit_mg_l"] = round(oxygen_deficit, 3)
            values["do_deficit_ratio"] = round(deficit_ratio, 4) if deficit_ratio else None

        values["alpha_factor"] = alpha
        values["beta_factor"] = beta
        values["pressure_correction"] = round(pressure_correction, 4)
        values["temp_correction"] = round(temp_correction, 4)

        # Field OTR / SAE require power input and volume
        if power_kw is not None and volume_m3 is not None:
            if power_kw < _MIN_POWER_KW:
                errors.append(f"power_kw={power_kw} below minimum ({_MIN_POWER_KW})")
            elif volume_m3 < _MIN_VOLUME_M3:
                errors.append(f"volume_m3={volume_m3} below minimum ({_MIN_VOLUME_M3})")
            else:
                # SOTR based on rated specification — use deficit_ratio to convert to OTR
                sotr_kg_o2_kwh = float(inputs.get("rated_sae_kg_o2_kwh", 1.5))
                sotr_kg_o2_h = sotr_kg_o2_kwh * power_kw

                if deficit_ratio is not None:
                    otr_kg_o2_h = sotr_kg_o2_h * deficit_ratio
                    oae_kg_o2_kwh = otr_kg_o2_h / power_kw
                else:
                    otr_kg_o2_h = None
                    oae_kg_o2_kwh = None

                values["sotr_kg_o2_h"] = round(sotr_kg_o2_h, 4)
                values["sotr_kg_o2_kwh"] = round(sotr_kg_o2_kwh, 4)
                values["otr_kg_o2_h"] = round(otr_kg_o2_h, 4) if otr_kg_o2_h else None
                values["oae_kg_o2_kwh"] = round(oae_kg_o2_kwh, 4) if oae_kg_o2_kwh else None
                values["power_kw"] = power_kw
        else:
            warnings.append("power_kw or volume_m3 not provided; OTR/SAE not computed")

        confidence = 1.0
        if warnings:
            confidence -= 0.1 * len(warnings)
        if not values:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

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
