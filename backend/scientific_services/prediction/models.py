"""Prediction and forecast models."""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Forecast:
    parameter: str
    horizon_days: int
    predicted_value: float
    lower_bound: float
    upper_bound: float
    confidence: float
    trend: str  # "increasing", "stable", "decreasing"
    timestamp: datetime
    method: str = "trend_extrapolation"

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "horizon_days": self.horizon_days,
            "predicted_value": self.predicted_value,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence": self.confidence,
            "trend": self.trend,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
        }


@dataclass
class LagoonForecast:
    lagoon_id: UUID
    generated_at: datetime
    bloom_probability_7d: float
    bloom_probability_14d: float
    bloom_probability_30d: float
    do_trend: str         # "improving", "stable", "deteriorating"
    residence_time_trend: str  # "decreasing", "stable", "increasing"
    overall_trajectory: str   # "improving", "stable", "deteriorating", "critical"
    confidence: float
    forecasts: list[Forecast] = field(default_factory=list)
    narrative: str = ""

    def to_dict(self) -> dict:
        return {
            "lagoon_id": str(self.lagoon_id),
            "generated_at": self.generated_at.isoformat(),
            "bloom_probability_7d": self.bloom_probability_7d,
            "bloom_probability_14d": self.bloom_probability_14d,
            "bloom_probability_30d": self.bloom_probability_30d,
            "do_trend": self.do_trend,
            "residence_time_trend": self.residence_time_trend,
            "overall_trajectory": self.overall_trajectory,
            "confidence": self.confidence,
            "forecasts": [f.to_dict() for f in self.forecasts],
            "narrative": self.narrative,
        }
