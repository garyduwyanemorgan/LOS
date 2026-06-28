"""
Nutrient cycling model using Michaelis-Menten kinetics.

Models:
  - Nitrification: NH4+ → NO2- → NO3- (aerobic)
  - Denitrification: NO3- → N2 (anoxic)
  - Phosphorus sorption/release (pH and redox dependent)
  - Algal uptake (Monod kinetics)
  - Sediment internal loading

Reference: Chapra, S.C. (1997) "Surface Water-Quality Modeling", McGraw-Hill.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..base import ModelOutput, ScientificModel

if TYPE_CHECKING:
    from uuid import UUID


class NutrientCyclingModel(ScientificModel):
    """
    Lumped-parameter nutrient cycling model.

    Runs one time step (dt=1 day by default) of coupled N and P
    transformations using Michaelis-Menten / Monod kinetics.

    All concentrations in mg/L unless noted.
    All rates in mg/L/day.
    """

    model_name = "nutrient_cycling"
    model_version = "1.0.0"

    # Michaelis-Menten half-saturation constants
    KN_NITRIFICATION = 0.5    # mg/L NH4+
    KO_NITRIFICATION = 2.0    # mg/L DO (nitrification inhibited below this)
    KN_DENITRIFICATION = 0.1  # mg/L NO3-
    KO_DENITRIFICATION = 0.2  # mg/L DO (denitrification active below this)
    KP_UPTAKE = 0.02          # mg/L PO4 (algal P half-saturation)
    KN_UPTAKE = 0.2           # mg/L NO3 (algal N half-saturation)

    # Maximum reaction rates (mg/L/day at 20°C)
    R_NITRIFICATION_MAX = 1.5
    R_DENITRIFICATION_MAX = 2.0
    R_P_UPTAKE_MAX = 0.3

    # Temperature correction coefficient (θ in Arrhenius-type)
    THETA = 1.07

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        t0 = time.perf_counter()

        required = ["nh4_mg_l", "no3_mg_l", "tp_mg_l", "do_mg_l"]
        missing = self.validate_inputs(inputs, required)
        if missing:
            return self._make_output(
                lagoon_id, values={}, errors=[f"Missing inputs: {missing}"], confidence=0.0
            )

        nh4 = max(0.0, float(inputs["nh4_mg_l"]))
        no3 = max(0.0, float(inputs["no3_mg_l"]))
        tp = max(0.0, float(inputs["tp_mg_l"]))
        do = max(0.0, float(inputs["do_mg_l"]))
        po4 = float(inputs.get("po4_mg_l", tp * 0.5))  # assume 50% is reactive if not given
        temp_c: float = float(inputs.get("temperature_c", 20.0))
        orp_mv: float = float(inputs.get("orp_mv", 100.0))
        volume_m3: float = float(inputs.get("volume_m3", 1e6))
        surface_area_m2: float = float(inputs.get("surface_area_m2", 1e5))
        dt_days: float = float(inputs.get("dt_days", 1.0))
        sediment_p_stock_mg_m2: float = float(inputs.get("sediment_p_stock_mg_m2", 500.0))
        warnings: list[str] = []

        # ---- Temperature correction (Arrhenius) ----
        theta = _temp_factor(temp_c, self.THETA)

        # ---- Nitrification: NH4+ → NO3- (two-step, modelled as one) ----
        # Rate ∝ NH4 / (KN + NH4) × DO / (KO + DO) × theta
        nitrification_rate = (
            self.R_NITRIFICATION_MAX
            * theta
            * _mm(nh4, self.KN_NITRIFICATION)
            * _mm(do, self.KO_NITRIFICATION)
        )
        d_nh4_nitrif = -nitrification_rate * dt_days
        d_no3_nitrif = nitrification_rate * dt_days

        # ---- Denitrification: NO3- → N2 (anoxic) ----
        # Active when DO < KO_denitrif (anoxic inhibition of oxygen)
        do_inhibition = max(0.0, 1.0 - do / self.KO_DENITRIFICATION)
        denitrification_rate = (
            self.R_DENITRIFICATION_MAX
            * theta
            * _mm(no3, self.KN_DENITRIFICATION)
            * do_inhibition
        )
        d_no3_denitrif = -denitrification_rate * dt_days

        # ---- Algal P uptake (Monod on P and N) ----
        p_uptake_rate = (
            self.R_P_UPTAKE_MAX
            * theta
            * _mm(po4, self.KP_UPTAKE)
            * _mm(no3 + nh4, self.KN_UPTAKE)
        )
        d_po4_uptake = -p_uptake_rate * dt_days

        # ---- Internal P loading from sediment ----
        # Release rate = 0 when ORP > 0, increases under reducing conditions
        release_rate_mg_m2_day = min(5.0, 2.0 * (-orp_mv / 200.0)) * theta if orp_mv < 0 else 0.0
        # Convert from areal to volumetric rate
        d_po4_release = (release_rate_mg_m2_day * surface_area_m2 / volume_m3) * dt_days

        # ---- Net changes ----
        nh4_new = max(0.0, nh4 + d_nh4_nitrif)
        no3_new = max(0.0, no3 + d_no3_nitrif + d_no3_denitrif)
        po4_new = max(0.0, po4 + d_po4_uptake + d_po4_release)
        tp_new = max(po4_new, tp + d_po4_release * 0.5)  # particulate fraction not fully recycled

        # Oxygen demand from nitrification: 4.57 g O2 per g NH4-N oxidised
        o2_demand_nitrif = nitrification_rate * 4.57
        # Oxygen recovery from denitrification: 2.86 g O2 per g NO3-N denitrified
        o2_recovery_denitrif = denitrification_rate * 2.86

        # ---- N:P ratio ----
        tn_est = nh4_new + no3_new
        np_ratio = tn_est / po4_new if po4_new > 0.001 else None

        if np_ratio is not None and np_ratio < 10:
            warnings.append(f"N:P ratio {np_ratio:.1f} < 10 — N limitation favours cyanobacteria")

        confidence = 0.75 if inputs.get("orp_mv") is not None else 0.60

        runtime = time.perf_counter() - t0
        return self._make_output(
            lagoon_id=lagoon_id,
            values={
                "nh4_new_mg_l": round(nh4_new, 4),
                "no3_new_mg_l": round(no3_new, 4),
                "po4_new_mg_l": round(po4_new, 4),
                "tp_new_mg_l": round(tp_new, 4),
                "nitrification_rate_mg_l_day": round(nitrification_rate, 4),
                "denitrification_rate_mg_l_day": round(denitrification_rate, 4),
                "p_uptake_rate_mg_l_day": round(p_uptake_rate, 4),
                "p_internal_loading_mg_l_day": round(d_po4_release / dt_days, 4),
                "p_release_rate_mg_m2_day": round(release_rate_mg_m2_day, 3),
                "o2_demand_nitrification_mg_l_day": round(o2_demand_nitrif, 3),
                "o2_recovery_denitrification_mg_l_day": round(o2_recovery_denitrif, 3),
                "net_o2_demand_mg_l_day": round(o2_demand_nitrif - o2_recovery_denitrif, 3),
                "n_p_ratio": round(np_ratio, 2) if np_ratio is not None else None,
                "dt_days": dt_days,
            },
            diagnostics={
                "temperature_c": temp_c,
                "temp_factor": round(theta, 4),
                "do_inhibition_denitrif": round(do_inhibition, 4),
                "sediment_p_stock_mg_m2": sediment_p_stock_mg_m2,
            },
            confidence=confidence,
            uncertainty={
                "nh4_new_mg_l": nh4_new * 0.15,
                "po4_new_mg_l": po4_new * 0.20,
                "p_release_rate_mg_m2_day": release_rate_mg_m2_day * 0.40,
            },
            warnings=warnings,
            runtime_seconds=round(runtime, 4),
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _mm(substrate: float, K_half: float) -> float:
    """Michaelis-Menten limiting factor: S / (K + S) ∈ [0, 1]."""
    if substrate + K_half == 0:
        return 0.0
    return substrate / (K_half + substrate)


def _temp_factor(temp_c: float, theta: float = 1.07) -> float:
    """Arrhenius-type temperature correction factor relative to 20°C."""
    return theta ** (temp_c - 20.0)
