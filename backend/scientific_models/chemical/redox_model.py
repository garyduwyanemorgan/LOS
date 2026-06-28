"""
Redox model — thermodynamic sequential reduction model.

Models the progression through redox couples as oxygen equivalents
are consumed. Follows the standard thermodynamic sequence:
  O2 → NO3- → MnO2 → Fe(OH)3 → SO4²⁻ → CO2

Used to predict prevailing redox couple from ORP and consumed oxygen demand.
"""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from ..base import ModelOutput, ScientificModel

if TYPE_CHECKING:
    from uuid import UUID

# Standard redox half-reaction potentials (pe° at pH 7) in mV
# pe° × 59.2 mV gives Eh at pH 7
_REDOX_COUPLES = [
    {"name": "oxygen_reduction",    "Eh_upper_mV": 800,  "Eh_lower_mV": 200,  "pe": 13.8},
    {"name": "nitrate_reduction",   "Eh_upper_mV": 200,  "Eh_lower_mV": 100,  "pe": 12.7},
    {"name": "manganese_reduction", "Eh_upper_mV": 100,  "Eh_lower_mV": -50,  "pe": 9.8},
    {"name": "iron_reduction",      "Eh_upper_mV": -50,  "Eh_lower_mV": -150, "pe": -1.67},
    {"name": "sulfate_reduction",   "Eh_upper_mV": -150, "Eh_lower_mV": -300, "pe": -3.75},
    {"name": "methanogenesis",      "Eh_upper_mV": -300, "Eh_lower_mV": -500, "pe": -4.13},
]


class RedoxModel(ScientificModel):
    """
    Thermodynamic sequential reduction model.

    Given ORP (Eh), temperature, and dissolved oxygen, identifies:
    - Active redox couple
    - Terminal electron acceptor
    - Predicted SO4²⁻ and Fe²⁺ concentrations at equilibrium
    - Internal P release potential from iron reduction
    """

    model_name = "redox_model"
    model_version = "1.0.0"

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        t0 = time.perf_counter()

        required = ["orp_mv"]
        missing = self.validate_inputs(inputs, required)
        if missing:
            return self._make_output(
                lagoon_id, values={}, errors=[f"Missing inputs: {missing}"], confidence=0.0
            )

        orp_mv = float(inputs["orp_mv"])
        temp_c: float = float(inputs.get("temperature_c", 25.0))
        do_mg_l: float | None = inputs.get("do_mg_l")
        so4_mg_l: float | None = inputs.get("so4_mg_l")
        fe_total_mg_l: float | None = inputs.get("fe_total_mg_l")
        ph: float = float(inputs.get("ph", 7.0))
        warnings: list[str] = []

        # ---- Identify active redox couple from ORP ----
        active_couple = None
        for couple in _REDOX_COUPLES:
            if orp_mv <= couple["Eh_upper_mV"]:
                active_couple = couple
            if orp_mv >= couple["Eh_lower_mV"]:
                break
        if active_couple is None:
            active_couple = _REDOX_COUPLES[-1]

        # ---- Temperature correction: ΔEh/ΔT ≈ -1.5 mV/°C for biological systems ----
        temp_c + 273.15
        temp_correction_mv = -1.5 * (temp_c - 25.0)
        orp_corrected = orp_mv + temp_correction_mv

        # ---- Free energy of active couple ----
        # ΔG = -nFΔEh, where n=number electrons transferred
        F = 96485  # C/mol
        n = 4  # typical electrons in O2 reduction
        delta_Eh = orp_corrected / 1000.0  # convert to V
        delta_G_kJ = -n * F * delta_Eh / 1000.0

        # ---- Predict ferrous iron release ----
        # Fe(III) → Fe(II) at Eh < -50 mV (pH 7)
        fe2_predicted: float | None = None
        if orp_mv < -50 and fe_total_mg_l is not None:
            # Fraction of Fe(III) reduced ~ sigmoid function of ORP
            reduction_fraction = 1.0 / (1.0 + math.exp((orp_mv + 50) / 30))
            fe2_predicted = fe_total_mg_l * reduction_fraction

        # ---- Predict H2S production ----
        h2s_predicted: float | None = None
        if orp_mv < -150 and so4_mg_l is not None:
            # Sulfate reduction rate proportional to distance from SO4/H2S boundary
            reduction_fraction = min(1.0, max(0.0, (-orp_mv - 150) / 150))
            # Max H2S (as S) from SO4 reduction: SO4 → H2S, MW ratio 32/96
            h2s_predicted = so4_mg_l * (32 / 96) * reduction_fraction * 0.1
            if h2s_predicted > 0.05:
                warnings.append(f"H2S generation estimated at {h2s_predicted:.2f} mg/L — toxicity risk")

        # ---- Internal phosphorus loading estimate ----
        # P release rate ≈ 2-5 mg/m²/d under reducing conditions
        p_release_mg_m2_day: float
        if orp_mv < -100:
            p_release_mg_m2_day = 5.0 * min(1.0, (-orp_mv - 100) / 200)
        elif orp_mv < 0:
            p_release_mg_m2_day = 2.0 * (-orp_mv / 100)
        else:
            p_release_mg_m2_day = 0.0

        # ---- Methanogenesis ----
        ch4_production = orp_mv < -250

        # ---- Confidence ----
        confidence = 0.90 if do_mg_l is not None else 0.70

        runtime = time.perf_counter() - t0
        return self._make_output(
            lagoon_id=lagoon_id,
            values={
                "active_redox_couple": active_couple["name"],
                "terminal_electron_acceptor": _get_tea(active_couple["name"]),
                "orp_mv": round(orp_mv, 1),
                "orp_corrected_25c_mv": round(orp_corrected, 1),
                "delta_G_kJ_mol": round(delta_G_kJ, 2),
                "fe2_predicted_mg_l": round(fe2_predicted, 3) if fe2_predicted is not None else None,
                "h2s_predicted_mg_l": round(h2s_predicted, 3) if h2s_predicted is not None else None,
                "p_internal_release_mg_m2_day": round(p_release_mg_m2_day, 2),
                "methanogenesis_active": ch4_production,
                "redox_zone": _redox_zone_name(orp_mv),
                "iron_reduction_active": orp_mv < -50,
                "sulfate_reduction_active": orp_mv < -150,
            },
            diagnostics={
                "temperature_c": temp_c,
                "ph": ph,
                "temp_correction_mv": round(temp_correction_mv, 2),
                "n_couples": len(_REDOX_COUPLES),
            },
            confidence=confidence,
            uncertainty={
                "orp_mv": 20.0,
                "fe2_predicted_mg_l": 0.5 if fe2_predicted is not None else 0.0,
                "p_internal_release_mg_m2_day": p_release_mg_m2_day * 0.5,
            },
            warnings=warnings,
            runtime_seconds=round(runtime, 4),
        )


def _get_tea(couple_name: str) -> str:
    """Return the terminal electron acceptor for a redox couple."""
    tea_map = {
        "oxygen_reduction": "O2",
        "nitrate_reduction": "NO3-",
        "manganese_reduction": "MnO2",
        "iron_reduction": "Fe(OH)3",
        "sulfate_reduction": "SO4²⁻",
        "methanogenesis": "CO2",
    }
    return tea_map.get(couple_name, "unknown")


def _redox_zone_name(orp_mv: float) -> str:
    if orp_mv > 200:
        return "oxic"
    elif orp_mv > 0:
        return "suboxic"
    elif orp_mv > -150:
        return "anoxic"
    elif orp_mv > -300:
        return "sulfidic"
    return "methanogenic"
