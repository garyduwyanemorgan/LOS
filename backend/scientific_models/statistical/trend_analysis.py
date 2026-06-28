"""Trend analysis for lagoon time-series data.

Provides:
- Mann-Kendall trend test (non-parametric, robust for environmental data)
- Sen's slope estimator
- Change point detection
- Seasonal decomposition helpers
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class TrendResult:
    """Result of a Mann-Kendall trend test."""
    parameter: str
    n_observations: int
    trend: str                  # "increasing" | "decreasing" | "no_trend"
    p_value: float
    significant: bool           # p < 0.05
    slope_per_day: float | None = None  # Sen's slope
    intercept: float | None = None
    confidence_level: float = 0.95


@dataclass
class ChangePoint:
    """A detected change point in a time series."""
    index: int
    timestamp: Any | None
    value_before: float
    value_after: float
    magnitude: float


def mann_kendall_test(
    values: list[float],
    alpha: float = 0.05,
    parameter_name: str = "unknown",
) -> TrendResult:
    """
    Non-parametric Mann-Kendall trend test.

    Suitable for monotonic trend detection in environmental data.
    More robust than linear regression for non-normally distributed series.

    Args:
        values: Time-ordered list of measurements
        alpha: Significance threshold (default 0.05)
        parameter_name: Human-readable parameter name for reporting

    Returns:
        TrendResult with trend direction, p-value, and significance
    """
    n = len(values)
    if n < 4:
        return TrendResult(
            parameter=parameter_name,
            n_observations=n,
            trend="no_trend",
            p_value=1.0,
            significant=False,
        )

    # Mann-Kendall S statistic
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = values[j] - values[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    # Variance of S accounting for ties
    var_s = _mann_kendall_var(values, n)

    if var_s == 0:
        return TrendResult(
            parameter=parameter_name,
            n_observations=n,
            trend="no_trend",
            p_value=1.0,
            significant=False,
        )

    # Z-score
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0

    # Two-tailed p-value using standard normal approximation
    p_value = 2 * (1 - _normal_cdf(abs(z)))

    # Trend direction
    trend = ("increasing" if s > 0 else "decreasing") if p_value < alpha else "no_trend"

    # Sen's slope estimate
    slope = _sens_slope(values)

    return TrendResult(
        parameter=parameter_name,
        n_observations=n,
        trend=trend,
        p_value=round(p_value, 4),
        significant=p_value < alpha,
        slope_per_day=round(slope, 6),
        confidence_level=1.0 - alpha,
    )


def _mann_kendall_var(values: list[float], n: int) -> float:
    """Compute variance of Mann-Kendall S statistic with tie correction."""
    # Count ties
    from collections import Counter
    counts = Counter(values)
    tie_correction = sum(t * (t - 1) * (2 * t + 5) for t in counts.values() if t > 1)

    var_s = (n * (n - 1) * (2 * n + 5) - tie_correction) / 18.0
    return max(var_s, 0.0)


def _sens_slope(values: list[float]) -> float:
    """Compute Sen's non-parametric slope estimator."""
    n = len(values)
    slopes: list[float] = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            if j != i:
                slopes.append((values[j] - values[i]) / (j - i))
    if not slopes:
        return 0.0
    slopes.sort()
    mid = len(slopes) // 2
    if len(slopes) % 2 == 0:
        return (slopes[mid - 1] + slopes[mid]) / 2.0
    return slopes[mid]


def _normal_cdf(z: float) -> float:
    """Approximate standard normal CDF using error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def detect_change_points(
    values: list[float],
    threshold_sigma: float = 2.0,
) -> list[ChangePoint]:
    """
    Simple change point detection using cumulative sum (CUSUM) method.

    Identifies points where the series mean shifts by more than threshold_sigma
    standard deviations from the rolling baseline.

    Args:
        values: Time-ordered measurements
        threshold_sigma: Detection threshold in standard deviations

    Returns:
        List of ChangePoint objects, ordered chronologically
    """
    if len(values) < 8:
        return []

    arr = np.array(values, dtype=float)
    float(np.mean(arr))
    std = float(np.std(arr))
    if std == 0:
        return []

    change_points: list[ChangePoint] = []
    window = min(10, len(arr) // 4)
    in_change = False

    for i in range(window, len(arr) - window):
        before_mean = float(np.mean(arr[i - window:i]))
        after_mean = float(np.mean(arr[i:i + window]))
        magnitude = abs(after_mean - before_mean)
        if magnitude > threshold_sigma * std and not in_change:
            change_points.append(
                ChangePoint(
                    index=i,
                    timestamp=None,
                    value_before=round(before_mean, 4),
                    value_after=round(after_mean, 4),
                    magnitude=round(magnitude, 4),
                )
            )
            in_change = True
        elif magnitude <= threshold_sigma * std:
            in_change = False

    return change_points
