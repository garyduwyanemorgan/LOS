"""
Residence time model.

Supports three methods:
  1. Simple: τ = V / Q_out (default)
  2. Age-tracer: plug-flow age distribution given inlet/outlet geometry
  3. CSTR-cascade: n well-mixed cells in series (Q_total / n*V_cell)
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..base import ModelOutput, ScientificModel

if TYPE_CHECKING:
    from uuid import UUID


class ResidenceTimeModel(ScientificModel):
    """
    Hydraulic residence time model with multiple computation methods.

    Methods:
      - "simple": τ = V / Q_out
      - "cstr_cascade": n-CSTR series model
      - "age_tracer": area-weighted age distribution
    """

    model_name = "residence_time"
    model_version = "1.0.0"

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        t0 = time.perf_counter()
        method: str = str(inputs.get("method", "simple"))

        required = ["volume_m3", "outflow_m3_day"]
        missing = self.validate_inputs(inputs, required)
        if missing:
            return self._make_output(
                lagoon_id, values={}, errors=[f"Missing inputs: {missing}"], confidence=0.0
            )

        volume = float(inputs["volume_m3"])
        outflow = float(inputs["outflow_m3_day"])
        warnings: list[str] = []

        if outflow < 0.001:
            warnings.append("Outflow negligible — using maximum residence time of 999 days")
            return self._make_output(
                lagoon_id,
                values={
                    "residence_time_days": 999.0,
                    "method": method,
                    "flushing_rate_per_day": 0.0,
                },
                diagnostics={"volume_m3": volume, "outflow_m3_day": outflow},
                confidence=0.5,
                uncertainty={"residence_time_days": 0.0},
                warnings=warnings,
                runtime_seconds=time.perf_counter() - t0,
            )

        if method == "simple":
            tau = volume / outflow
            flushing_rate = 1.0 / tau
            confidence = 0.85
            diagnostics: dict[str, Any] = {
                "method": "simple",
                "volume_m3": volume,
                "outflow_m3_day": outflow,
            }

        elif method == "cstr_cascade":
            n_cells: int = int(inputs.get("n_cells", 3))
            if n_cells < 1:
                n_cells = 1
            tau_single = volume / outflow  # total τ same as simple
            # Mean age for n-CSTR cascade = τ (same as simple)
            # Variance is τ²/n — narrower RTD for higher n
            tau = tau_single
            tau_variance = tau**2 / n_cells
            flushing_rate = 1.0 / tau
            confidence = 0.80
            diagnostics = {
                "method": "cstr_cascade",
                "n_cells": n_cells,
                "tau_variance_days2": round(tau_variance, 3),
                "peclet_number": n_cells,
            }

        elif method == "age_tracer":
            # Age distribution: exponential for CSTR → mean age = τ
            # Modify by inlet/outlet separation factor (0-1, 1=maximum separation)
            separation: float = float(inputs.get("inlet_outlet_separation_factor", 0.5))
            tau_simple = volume / outflow
            # Short-circuiting correction: τ_eff = τ * (0.3 + 0.7 * separation)
            tau = tau_simple * (0.3 + 0.7 * separation)
            flushing_rate = 1.0 / tau
            confidence = 0.70
            diagnostics = {
                "method": "age_tracer",
                "inlet_outlet_separation_factor": separation,
                "tau_simple_days": round(tau_simple, 2),
                "short_circuit_correction": round(0.3 + 0.7 * separation, 3),
            }

        else:
            return self._make_output(
                lagoon_id,
                values={},
                errors=[f"Unknown method: {method}. Use 'simple', 'cstr_cascade', or 'age_tracer'"],
                confidence=0.0,
            )

        # Tidal dilution factor (optional)
        tidal_exchange_m3: float = float(inputs.get("tidal_exchange_m3_per_day", 0.0))
        if tidal_exchange_m3 > 0:
            effective_outflow = outflow + tidal_exchange_m3
            tau_tidal = volume / effective_outflow
            diagnostics["tidal_diluted_tau_days"] = round(tau_tidal, 2)
            diagnostics["tidal_exchange_m3_day"] = tidal_exchange_m3
        else:
            tau_tidal = None

        runtime = time.perf_counter() - t0
        return self._make_output(
            lagoon_id=lagoon_id,
            values={
                "residence_time_days": round(tau, 2),
                "tidal_corrected_residence_time_days": (
                    round(tau_tidal, 2) if tau_tidal is not None else None
                ),
                "flushing_rate_per_day": round(flushing_rate, 5),
                "flushing_rate_per_year": round(flushing_rate * 365, 2),
                "method": method,
            },
            diagnostics=diagnostics,
            confidence=confidence,
            uncertainty={"residence_time_days": round(tau * 0.15, 3)},
            warnings=warnings,
            runtime_seconds=round(runtime, 4),
        )
