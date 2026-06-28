"""Statistical anomaly detection model.

Detects anomalous observations in water quality time series using:
  - Modified Z-score (Iglewicz & Hoaglin 1993) — robust to outliers
  - Inter-quartile range (IQR) fence method
  - Rate-of-change threshold (delta detection)

All methods operate on pure Python/NumPy — no external ML dependencies.
This ensures the model runs in environments without scikit-learn or PyTorch.

Reference:
  Iglewicz, B. & Hoaglin, D. (1993). How to Detect and Handle Outliers.
  ASQC Quality Press, Milwaukee, Wisconsin.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..base import ScientificModel, ModelOutput


@dataclass
class AnomalyResult:
    """Anomaly assessment for a single data point."""
    value: float
    timestamp: str
    is_anomaly: bool
    method: str             # "z_score", "iqr", "rate_of_change"
    score: float            # method-specific score (higher = more anomalous)
    threshold: float        # threshold used
    severity: str           # "low", "medium", "high"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "timestamp": self.timestamp,
            "is_anomaly": self.is_anomaly,
            "method": self.method,
            "score": round(self.score, 4),
            "threshold": self.threshold,
            "severity": self.severity,
            "notes": self.notes,
        }


class AnomalyDetectionModel(ScientificModel):
    """Detect anomalous observations in a water quality parameter time series.

    Inputs:
        series: list[dict] — each entry has "value" (float) and "timestamp" (str ISO)
        parameter: str — name of the parameter being analysed
        z_threshold: float — modified Z-score threshold (default 3.5)
        iqr_multiplier: float — IQR fence multiplier (default 1.5)
        max_rate_per_hour: float | None — maximum expected Δvalue/hour (None = skip)
        window_hours: float — rolling window size for rate detection (default 1.0)

    Outputs:
        anomaly_count: int
        anomaly_rate_pct: float
        anomalies: list[dict] — each is AnomalyResult.to_dict()
        median: float
        mad: float — Median Absolute Deviation
        q1: float
        q3: float
        iqr: float
        method_used: list[str]
    """

    model_name = "anomaly_detection"
    model_version = "1.0.0"

    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        import time
        t0 = time.perf_counter()

        warnings: list[str] = []
        errors: list[str] = []

        series: list[dict] = inputs.get("series", [])
        if not series:
            return self._make_output(
                lagoon_id=lagoon_id,
                values={"anomaly_count": 0, "anomaly_rate_pct": 0.0},
                confidence=0.0,
                errors=["series is empty"],
            )

        z_threshold = float(inputs.get("z_threshold", 3.5))
        iqr_multiplier = float(inputs.get("iqr_multiplier", 1.5))
        max_rate = inputs.get("max_rate_per_hour")

        values_list = [float(p["value"]) for p in series if p.get("value") is not None]
        timestamps = [p.get("timestamp", "") for p in series if p.get("value") is not None]

        if len(values_list) < 4:
            warnings.append(
                f"Only {len(values_list)} data points; Z-score and IQR require ≥4"
            )
            return self._make_output(
                lagoon_id=lagoon_id,
                values={"anomaly_count": 0, "anomaly_rate_pct": 0.0},
                confidence=0.3,
                warnings=warnings,
            )

        # ── Modified Z-score ─────────────────────────────────────────────────
        med = statistics.median(values_list)
        mad = statistics.median([abs(x - med) for x in values_list]) or 1e-9
        z_scores = [0.6745 * (x - med) / mad for x in values_list]

        # ── IQR fence ────────────────────────────────────────────────────────
        sorted_vals = sorted(values_list)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[(3 * n) // 4]
        iqr = q3 - q1
        iqr_lo = q1 - iqr_multiplier * iqr
        iqr_hi = q3 + iqr_multiplier * iqr

        # ── Rate-of-change detection ─────────────────────────────────────────
        rate_anomalies: set[int] = set()
        if max_rate is not None and len(values_list) >= 2:
            for i in range(1, len(values_list)):
                delta = abs(values_list[i] - values_list[i - 1])
                if delta > max_rate:
                    rate_anomalies.add(i)

        # ── Assemble results ─────────────────────────────────────────────────
        anomalies: list[AnomalyResult] = []
        method_flags: set[str] = set()

        for i, (val, ts) in enumerate(zip(values_list, timestamps)):
            z = abs(z_scores[i])
            iqr_flag = val < iqr_lo or val > iqr_hi
            rate_flag = i in rate_anomalies

            is_anomaly = z > z_threshold or iqr_flag or rate_flag

            if not is_anomaly:
                continue

            if z > z_threshold * 2:
                severity = "high"
            elif z > z_threshold or (iqr_flag and abs(val - med) > 3 * mad):
                severity = "medium"
            else:
                severity = "low"

            methods: list[str] = []
            if z > z_threshold:
                methods.append("z_score")
                method_flags.add("z_score")
            if iqr_flag:
                methods.append("iqr")
                method_flags.add("iqr")
            if rate_flag:
                methods.append("rate_of_change")
                method_flags.add("rate_of_change")

            anomalies.append(
                AnomalyResult(
                    value=val,
                    timestamp=ts,
                    is_anomaly=True,
                    method=", ".join(methods),
                    score=round(z, 4),
                    threshold=z_threshold,
                    severity=severity,
                    notes=f"IQR fence [{iqr_lo:.2f}, {iqr_hi:.2f}]" if iqr_flag else "",
                )
            )

        anomaly_rate = (len(anomalies) / len(values_list)) * 100.0

        out_values: dict[str, Any] = {
            "anomaly_count": len(anomalies),
            "anomaly_rate_pct": round(anomaly_rate, 2),
            "anomalies": [a.to_dict() for a in anomalies],
            "series_length": len(values_list),
            "median": round(med, 4),
            "mad": round(mad, 4),
            "q1": round(q1, 4),
            "q3": round(q3, 4),
            "iqr": round(iqr, 4),
            "iqr_fence_lo": round(iqr_lo, 4),
            "iqr_fence_hi": round(iqr_hi, 4),
            "z_threshold": z_threshold,
            "method_used": sorted(method_flags),
        }

        if anomaly_rate > 20:
            warnings.append(
                f"High anomaly rate ({anomaly_rate:.1f}%); verify sensor calibration."
            )

        confidence = min(1.0, math.log10(max(len(values_list), 1)) / 2.0)

        runtime = time.perf_counter() - t0

        return self._make_output(
            lagoon_id=lagoon_id,
            values=out_values,
            diagnostics={"n_points": len(values_list)},
            confidence=round(confidence, 3),
            warnings=warnings,
            errors=errors,
            runtime_seconds=runtime,
        )
