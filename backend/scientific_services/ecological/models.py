"""Ecological state models."""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class EcologicalState:
    lagoon_id: UUID
    timestamp: datetime

    # Bloom dynamics
    bloom_probability: float | None
    bloom_probability_trend: str | None  # "increasing", "stable", "decreasing"
    cyanobacteria_advantage: float | None
    succession_stage: str | None

    # Ecosystem health
    ecological_stability_score: float | None
    recovery_potential: str | None  # "high", "medium", "low"
    trophic_state: str | None

    # Observed biological indicators
    chlorophyll_a_ug_l: float | None
    phycocyanin_rfu: float | None   # cyanobacteria pigment proxy
    secchi_depth_m: float | None
    macrophyte_cover_pct: float | None

    # Risk indicators
    fish_kill_risk: str | None   # "low", "medium", "high", "critical"
    toxin_risk: str | None       # "low", "medium", "high" (microcystin proxy)
    historical_bloom_count: int = 0

    # Quality metadata
    data_completeness_pct: float = 0.0
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lagoon_id": str(self.lagoon_id),
            "timestamp": self.timestamp.isoformat(),
            "bloom_probability": self.bloom_probability,
            "bloom_probability_trend": self.bloom_probability_trend,
            "cyanobacteria_advantage": self.cyanobacteria_advantage,
            "succession_stage": self.succession_stage,
            "ecological_stability_score": self.ecological_stability_score,
            "recovery_potential": self.recovery_potential,
            "trophic_state": self.trophic_state,
            "chlorophyll_a_ug_l": self.chlorophyll_a_ug_l,
            "phycocyanin_rfu": self.phycocyanin_rfu,
            "secchi_depth_m": self.secchi_depth_m,
            "macrophyte_cover_pct": self.macrophyte_cover_pct,
            "fish_kill_risk": self.fish_kill_risk,
            "toxin_risk": self.toxin_risk,
            "historical_bloom_count": self.historical_bloom_count,
            "data_completeness_pct": self.data_completeness_pct,
            "confidence": self.confidence,
            "notes": self.notes,
        }
