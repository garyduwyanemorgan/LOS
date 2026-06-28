"""
Algal dynamics model using Monod growth kinetics.

Models phytoplankton biomass dynamics including:
  - Monod growth limited by light, nutrients (N and P), and temperature
  - Respiration
  - Settling/sedimentation
  - Grazing (simplified zooplankton term)
  - Photoinhibition at high irradiance

Reference: Chapra (1997), Reynolds (2006) "The Ecology of Phytoplankton"
"""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from ..base import ModelOutput, ScientificModel

if TYPE_CHECKING:
    from uuid import UUID


class AlgalDynamicsModel(ScientificModel):
    """
    Single-component phytoplankton growth model.

    Computes:
      dB/dt = (mu_net - r_resp - v_s/H - G) * B

    where B = biomass (mg chl-a/L or mg C/L), mu_net = net growth rate,
    r_resp = respiration rate, v_s = settling velocity, H = depth, G = grazing.
    """

    model_name = "algal_dynamics"
    model_version = "1.0.0"

    # Default parameters (all at 20°C)
    MU_MAX_DAY = 2.0          # maximum growth rate (day⁻¹)
    R_RESP_DAY = 0.1          # respiration rate (day⁻¹)
    V_SETTLING_M_DAY = 0.05   # settling velocity (m/day)
    K_P = 0.005               # phosphorus half-saturation (mg P/L)
    K_N = 0.10                # nitrogen half-saturation (mg N/L)
    K_I = 120.0               # light half-saturation (µmol/m²/s PAR)
    I_INHIBIT = 800.0         # photoinhibition threshold (µmol/m²/s PAR)
    THETA = 1.066             # Arrhenius temperature coefficient

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        t0 = time.perf_counter()

        required = ["initial_biomass_ug_l", "tp_mg_l"]
        missing = self.validate_inputs(inputs, required)
        if missing:
            return self._make_output(
                lagoon_id, values={}, errors=[f"Missing inputs: {missing}"], confidence=0.0
            )

        B0 = max(0.001, float(inputs["initial_biomass_ug_l"]) / 1000.0)  # convert µg/L → mg/L
        tp = float(inputs["tp_mg_l"])
        tn = float(inputs.get("tn_mg_l", tp * 10))  # default Redfield-ish
        # Assume reactive P = 60% of TP, reactive N = 80% of TN
        po4 = float(inputs.get("po4_mg_l", tp * 0.6))
        no3 = float(inputs.get("no3_mg_l", tn * 0.8))
        temp_c = float(inputs.get("temperature_c", 25.0))
        irradiance = float(inputs.get("irradiance_umol_m2_s", 300.0))
        depth_m = float(inputs.get("mean_depth_m", 1.5))
        dt_days = float(inputs.get("dt_days", 1.0))
        n_steps = int(inputs.get("n_steps", 1))
        grazing_rate_day = float(inputs.get("grazing_rate_day", 0.05))
        kext = float(inputs.get("light_extinction_m", 0.5))  # m⁻¹

        # Optional group: treat as cyanobacteria (buoyancy) or diatom (fast settling)
        algal_group = str(inputs.get("algal_group", "mixed"))  # "cyano", "diatom", "mixed"

        # Adjust settling for cyanobacteria (buoyant, low settling)
        if algal_group == "cyano":
            settling = self.V_SETTLING_M_DAY * 0.1
            mu_max = self.MU_MAX_DAY * 0.8  # cyanos slower but temperature tolerant
        elif algal_group == "diatom":
            settling = self.V_SETTLING_M_DAY * 2.0
            mu_max = self.MU_MAX_DAY * 1.2
        else:
            settling = self.V_SETTLING_M_DAY
            mu_max = self.MU_MAX_DAY

        warnings: list[str] = []
        B = B0
        biomass_series: list[float] = [B * 1000]  # store in µg/L

        for _step in range(n_steps):
            # Temperature factor (Arrhenius)
            theta_T = self.THETA ** (temp_c - 20.0)

            # Light limitation — depth-integrated (Beer's law attenuation)
            # Average irradiance through water column
            I_avg = (irradiance / (kext * depth_m)) * (1.0 - math.exp(-kext * depth_m))
            # Steele's equation for light + photoinhibition
            I_opt = self.K_I
            if I_avg <= I_opt:
                f_light = I_avg / (self.K_I + I_avg)
            else:
                # Photoinhibition: decline above I_opt
                f_light = math.exp(-1.0 * (I_avg - I_opt) / self.I_INHIBIT) * (I_opt / (self.K_I + I_opt))

            # Nutrient limitation (Liebig's Law of the Minimum)
            f_P = po4 / (self.K_P + po4) if po4 > 0 else 0.0
            f_N = no3 / (self.K_N + no3) if no3 > 0 else 0.0
            f_nut = min(f_P, f_N)  # Liebig's minimum

            # Gross growth rate
            mu = mu_max * theta_T * f_light * f_nut

            # Settling loss
            settling_loss = settling / depth_m if depth_m > 0 else 0.0

            # Net rate of change
            net_rate = mu - self.R_RESP_DAY * theta_T - settling_loss - grazing_rate_day

            # Euler integration
            dB = net_rate * B * dt_days
            B = max(0.0, B + dB)

            # Update nutrients consumed by algae
            # Redfield: C:N:P = 106:16:1 by mol → mass ratio C:N:P ≈ 41:7.2:1
            # Biomass growth in mg C/L ≈ B (chl-a to C ratio ~50)
            delta_B_mgC = dB * 50  # approximate
            po4 = max(0.0, po4 - delta_B_mgC / 41.0 / 41.0)  # very rough
            no3 = max(0.0, no3 - delta_B_mgC * (7.2 / 41.0))

            biomass_series.append(round(B * 1000, 3))

        final_B_ug_l = B * 1000  # µg chl-a/L

        if final_B_ug_l > 50:
            warnings.append(f"Biomass {final_B_ug_l:.0f} µg/L — bloom threshold exceeded (>50 µg/L)")
        if final_B_ug_l > 200:
            warnings.append("Severe bloom — surface scum likely. Toxin production risk elevated.")

        # Trophic classification from chlorophyll
        if final_B_ug_l > 50:
            trophic = "hypereutrophic"
        elif final_B_ug_l > 25:
            trophic = "eutrophic"
        elif final_B_ug_l > 10:
            trophic = "mesotrophic"
        else:
            trophic = "oligotrophic"

        confidence = 0.70 if inputs.get("irradiance_umol_m2_s") else 0.55

        runtime = time.perf_counter() - t0
        return self._make_output(
            lagoon_id=lagoon_id,
            values={
                "initial_biomass_ug_chl_l": round(B0 * 1000, 3),
                "final_biomass_ug_chl_l": round(final_B_ug_l, 3),
                "biomass_change_ug_chl_l": round(final_B_ug_l - B0 * 1000, 3),
                "net_growth_rate_day": round(net_rate, 4),
                "light_limitation_factor": round(f_light, 4),
                "nutrient_limitation_factor": round(f_nut, 4),
                "p_limitation_factor": round(f_P, 4),
                "n_limitation_factor": round(f_N, 4),
                "trophic_class": trophic,
                "algal_group": algal_group,
                "biomass_time_series_ug_l": biomass_series if n_steps > 1 else None,
                "bloom_threshold_exceeded": final_B_ug_l > 50,
            },
            diagnostics={
                "temperature_c": temp_c,
                "irradiance_umol_m2_s": irradiance,
                "I_avg_column_umol_m2_s": round(I_avg, 2),
                "mu_max_day": mu_max,
                "settling_m_day": settling,
                "n_steps": n_steps,
                "dt_days": dt_days,
            },
            confidence=confidence,
            uncertainty={
                "final_biomass_ug_chl_l": final_B_ug_l * 0.30,
                "net_growth_rate_day": abs(net_rate) * 0.25,
            },
            warnings=warnings,
            runtime_seconds=round(runtime, 4),
        )
