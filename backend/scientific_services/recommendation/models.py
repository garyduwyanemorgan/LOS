"""Recommendation models for lagoon management actions."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class RecommendationPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionCategory(StrEnum):
    AERATION = "aeration"
    CIRCULATION = "circulation"
    MONITORING = "monitoring"
    MAINTENANCE = "maintenance"
    TSE_MANAGEMENT = "tse_management"
    CHEMICAL_DOSING = "chemical_dosing"
    DREDGING = "dredging"
    REPORTING = "reporting"
    DO_NOTHING = "do_nothing"


@dataclass
class Recommendation:
    recommendation_id: str
    lagoon_id: UUID
    generated_at: datetime
    priority: RecommendationPriority
    category: ActionCategory
    title: str
    description: str
    rationale: str
    expected_outcome: str
    estimated_cost_aed: float | None
    estimated_duration_hours: float | None
    confidence: float  # 0–1
    evidence: list[str] = field(default_factory=list)
    contraindications: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    kpis: list[str] = field(default_factory=list)  # metrics to track after action

    def to_dict(self) -> dict:
        return {
            "recommendation_id": self.recommendation_id,
            "lagoon_id": str(self.lagoon_id),
            "generated_at": self.generated_at.isoformat(),
            "priority": self.priority.value,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "expected_outcome": self.expected_outcome,
            "estimated_cost_aed": self.estimated_cost_aed,
            "estimated_duration_hours": self.estimated_duration_hours,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "contraindications": self.contraindications,
            "dependencies": self.dependencies,
            "kpis": self.kpis,
        }


@dataclass
class RecommendationSet:
    lagoon_id: UUID
    generated_at: datetime
    primary_recommendation: Recommendation
    alternatives: list[Recommendation] = field(default_factory=list)
    system_summary: str = ""
    urgency_level: str = "normal"  # "normal", "elevated", "urgent", "emergency"

    def to_dict(self) -> dict:
        return {
            "lagoon_id": str(self.lagoon_id),
            "generated_at": self.generated_at.isoformat(),
            "primary_recommendation": self.primary_recommendation.to_dict(),
            "alternatives": [r.to_dict() for r in self.alternatives],
            "system_summary": self.system_summary,
            "urgency_level": self.urgency_level,
        }
