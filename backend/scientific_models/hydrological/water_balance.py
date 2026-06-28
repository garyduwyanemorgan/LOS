"""
Water balance model with daily time-stepping.

Implements a simple but complete lumped parameter water balance:
  dS/dt = Qin + P*A - ET*A + Qgw - Qout

Handles volume-level relationship via bathymetry coefficients.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..base import ModelOutput, ScientificModel

if TYPE_CHECKING:
    from uuid import UUID


@dataclass
class WaterBalanceInputs:
    """Inputs for the WaterBalanceModel time-stepping run."""
    initial_volume_m3: float
    surface_area_m2: float
    n_days: int                          # simulation duration
    daily_inflow_m3: list[float]        # one value per day
    daily_outflow_m3: list[float]
    daily_precipitation_mm: list[float]
    daily_evaporation_mm: list[float]
    daily_groundwater_m3: list[float]   # positive = in, negative = out
    bathymetry_a0: float = 0.0          # V = a0 + a1*h + a2*h²
    bathymetry_a1: float = 1000.0
    bathymetry_a2: float = 100.0
    min_volume_m3: float = 0.0          # lagoon floor


class WaterBalanceModel(ScientificModel):
    """
    Lumped daily water balance model.

    Simulates lagoon storage, volume, and derived residence time
    over N days given daily forcing time series.
    """

    model_name = "water_balance"
    model_version = "1.0.0"

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        t0 = time.perf_counter()

        # Validate
        required = [
            "initial_volume_m3", "surface_area_m2", "n_days",
            "daily_inflow_m3", "daily_outflow_m3",
        ]
        missing = self.validate_inputs(inputs, required)
        if missing:
            return self._make_output(
                lagoon_id, values={}, errors=[f"Missing inputs: {missing}"],
                confidence=0.0,
            )

        wb = WaterBalanceInputs(
            initial_volume_m3=float(inputs["initial_volume_m3"]),
            surface_area_m2=float(inputs["surface_area_m2"]),
            n_days=int(inputs["n_days"]),
            daily_inflow_m3=_to_list(inputs["daily_inflow_m3"], inputs["n_days"]),
            daily_outflow_m3=_to_list(inputs["daily_outflow_m3"], inputs["n_days"]),
            daily_precipitation_mm=_to_list(inputs.get("daily_precipitation_mm", 0.0), inputs["n_days"]),
            daily_evaporation_mm=_to_list(inputs.get("daily_evaporation_mm", 0.0), inputs["n_days"]),
            daily_groundwater_m3=_to_list(inputs.get("daily_groundwater_m3", 0.0), inputs["n_days"]),
            bathymetry_a0=float(inputs.get("bathymetry_a0", 0.0)),
            bathymetry_a1=float(inputs.get("bathymetry_a1", 1000.0)),
            bathymetry_a2=float(inputs.get("bathymetry_a2", 100.0)),
            min_volume_m3=float(inputs.get("min_volume_m3", 0.0)),
        )

        # ---- Time stepping ----
        volume = wb.initial_volume_m3
        volumes: list[float] = [volume]
        delta_storage: list[float] = []
        water_levels: list[float] = [_volume_to_level(volume, wb)]
        residence_times: list[float] = []
        balance_errors: list[float] = []
        warnings: list[str] = []

        for day in range(wb.n_days):
            P_m3 = (wb.daily_precipitation_mm[day] / 1000.0) * wb.surface_area_m2
            ET_m3 = (wb.daily_evaporation_mm[day] / 1000.0) * wb.surface_area_m2
            Qin = wb.daily_inflow_m3[day]
            Qout = wb.daily_outflow_m3[day]
            Qgw = wb.daily_groundwater_m3[day]

            dS = Qin + P_m3 + Qgw - Qout - ET_m3
            volume = max(wb.min_volume_m3, volume + dS)

            # Water balance check
            total_in = Qin + P_m3 + max(0.0, Qgw)
            err_pct = abs(dS / total_in * 100) if total_in > 0 else 0.0

            volumes.append(volume)
            delta_storage.append(dS)
            water_levels.append(_volume_to_level(volume, wb))
            balance_errors.append(err_pct)

            # Residence time
            rt = volume / Qout if Qout > 0.001 else 999.0
            residence_times.append(rt)

            if volume <= wb.min_volume_m3 * 1.01:
                warnings.append(f"Day {day+1}: volume reached minimum ({volume:.1f} m³)")
            if err_pct > 10:
                warnings.append(f"Day {day+1}: water balance error {err_pct:.1f}%")

        # ---- Summary statistics ----
        mean_volume = sum(volumes) / len(volumes)
        mean_rt = sum(residence_times) / len(residence_times) if residence_times else 0.0
        max_level = max(water_levels)
        min_level = min(water_levels)
        mean_balance_err = sum(balance_errors) / len(balance_errors) if balance_errors else 0.0

        # Confidence: inversely proportional to mean balance error
        confidence = max(0.1, min(1.0, 1.0 - mean_balance_err / 100.0))

        runtime = time.perf_counter() - t0
        return self._make_output(
            lagoon_id=lagoon_id,
            values={
                "final_volume_m3": round(volume, 2),
                "mean_volume_m3": round(mean_volume, 2),
                "mean_residence_time_days": round(mean_rt, 2),
                "max_water_level_m": round(max_level, 3),
                "min_water_level_m": round(min_level, 3),
                "volume_time_series": [round(v, 1) for v in volumes],
                "water_level_time_series": [round(h, 3) for h in water_levels],
                "residence_time_series": [round(rt, 2) for rt in residence_times],
                "delta_storage_series": [round(d, 2) for d in delta_storage],
            },
            diagnostics={
                "n_days": wb.n_days,
                "mean_balance_error_pct": round(mean_balance_err, 3),
                "n_dry_days": sum(1 for v in volumes if v <= wb.min_volume_m3 * 1.01),
            },
            confidence=round(confidence, 3),
            uncertainty={
                "volume_m3": mean_volume * 0.1,
                "residence_time_days": mean_rt * 0.15,
            },
            warnings=warnings,
            runtime_seconds=round(runtime, 4),
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _to_list(value: Any, n: int) -> list[float]:
    """Convert scalar or list to length-n list of floats."""
    if isinstance(value, (int, float)):
        return [float(value)] * n
    lst = list(value)
    if len(lst) < n:
        # Repeat last value
        lst = lst + [lst[-1]] * (n - len(lst))
    return [float(v) for v in lst[:n]]


def _volume_to_level(volume_m3: float, wb: WaterBalanceInputs) -> float:
    """Invert V = a0 + a1*h + a2*h² to solve for h given V."""
    a0, a1, a2 = wb.bathymetry_a0, wb.bathymetry_a1, wb.bathymetry_a2
    if a2 == 0:
        if a1 == 0:
            return 0.0
        return max(0.0, (volume_m3 - a0) / a1)
    # Quadratic: a2*h² + a1*h + (a0 - V) = 0
    discriminant = a1**2 - 4 * a2 * (a0 - volume_m3)
    if discriminant < 0:
        return 0.0
    return max(0.0, (-a1 + discriminant**0.5) / (2 * a2))
