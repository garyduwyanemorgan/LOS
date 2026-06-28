"""Decision Engine domain models.

Every recommendation passes through these models.
The DecisionMatrix is the authoritative scoring record — it explains
exactly why one option was ranked above another.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

# ─── Enumerations ─────────────────────────────────────────────────────────────

class ObjectiveType(StrEnum):
    PROTECT_LAGOON = "protect_lagoon"
    WATER_QUALITY = "water_quality"
    ECOLOGICAL_STABILITY = "ecological_stability"
    OPERATIONAL_COST = "operational_cost"
    REGULATORY_COMPLIANCE = "regulatory_compliance"
    SCIENTIFIC_CONFIDENCE = "scientific_confidence"
    CONTINUOUS_IMPROVEMENT = "continuous_improvement"


class ActionCategory(StrEnum):
    AERATION = "aeration"
    CIRCULATION = "circulation"
    TSE_MANAGEMENT = "tse_management"
    MAINTENANCE = "maintenance"
    MONITORING = "monitoring"
    CHEMICAL_DOSING = "chemical_dosing"
    DREDGING = "dredging"
    OBSERVATION = "observation"
    NO_ACTION = "no_action"


class RecommendationUrgency(StrEnum):
    IMMEDIATE = "immediate"       # Act within hours
    URGENT = "urgent"             # Act within 24 hours
    ROUTINE = "routine"           # Act within 7 days
    PLANNED = "planned"           # Schedule for next maintenance window
    MONITORING = "monitoring"     # Continue observing


# ─── Operating objectives ──────────────────────────────────────────────────────

@dataclass
class ObjectiveWeight:
    """Per-lagoon, per-objective weight configuration."""
    objective: ObjectiveType
    weight: float                  # 0.0 – 1.0; weights are normalised
    target_value: float | None = None
    threshold_critical: float | None = None
    threshold_warning: float | None = None
    notes: str = ""


@dataclass
class OperatingObjective:
    """Full objective definition with current performance score."""
    objective_type: ObjectiveType
    weight: float                  # normalised
    current_score: float           # 0.0 – 1.0 (1.0 = fully achieving objective)
    target_score: float = 1.0
    indicators: dict[str, float] = field(default_factory=dict)
    compliance_status: bool = True


# ─── System state snapshot ────────────────────────────────────────────────────

@dataclass
class LoopStateSnapshot:
    """Current state of one scientific loop."""
    loop: str                      # ScientificLoop enum value
    confidence: float              # 0.0 – 1.0
    status: str                    # healthy | warning | critical | unknown
    state: dict[str, Any] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class LagoonSystemState:
    """
    Complete state of a lagoon at the time of a decision cycle.

    This is the primary input to the Decision Engine.
    Assembled by collecting state from all scientific loops.
    """
    lagoon_id: UUID
    snapshot_time: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    # Loop states
    hydrological: LoopStateSnapshot | None = None
    chemical: LoopStateSnapshot | None = None
    ecological: LoopStateSnapshot | None = None
    infrastructure: LoopStateSnapshot | None = None

    # Aggregated signals
    active_alerts: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    operating_objectives: list[OperatingObjective] = field(default_factory=list)

    # Memory context
    recent_interventions: list[dict[str, Any]] = field(default_factory=list)
    learning_insights: list[str] = field(default_factory=list)

    # SRG hypotheses
    causal_hypotheses: list[dict[str, Any]] = field(default_factory=list)

    @property
    def worst_alert_level(self) -> str:
        """Return the highest alert level across all loops."""
        statuses = []
        for loop in [self.hydrological, self.chemical, self.ecological, self.infrastructure]:
            if loop:
                statuses.append(loop.status)
        if "critical" in statuses:
            return "critical"
        if "warning" in statuses:
            return "warning"
        return "healthy"

    @property
    def available_loops(self) -> list[str]:
        names = []
        for name, loop in [
            ("hydrological", self.hydrological),
            ("chemical", self.chemical),
            ("ecological", self.ecological),
            ("infrastructure", self.infrastructure),
        ]:
            if loop is not None:
                names.append(name)
        return names


# ─── Decision option ──────────────────────────────────────────────────────────

@dataclass
class ObjectiveScore:
    """How one decision option scores against one objective."""
    objective: ObjectiveType
    score: float                   # 0.0 – 1.0
    weighted_score: float          # score × objective_weight
    rationale: str = ""


@dataclass
class DecisionOption:
    """
    A candidate operational action that the Decision Engine can recommend.

    Generated for every significant system event.
    Evaluated and ranked before a recommendation is produced.
    """
    id: UUID = field(default_factory=uuid4)
    action_title: str = ""
    category: ActionCategory = ActionCategory.OBSERVATION
    urgency: RecommendationUrgency = RecommendationUrgency.ROUTINE

    # Scientific basis
    scientific_reasoning: str = ""
    contributing_loops: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    causal_pathways: list[str] = field(default_factory=list)

    # Objective scoring
    objective_scores: list[ObjectiveScore] = field(default_factory=list)
    overall_score: float = 0.0    # Weighted sum of objective scores

    # Operational parameters
    expected_outcome: str = ""
    expected_timeframe_hours: float | None = None
    confidence: float = 0.0
    implementation_complexity: float = 0.5  # 0=trivial, 1=complex
    operational_cost_index: float = 0.5     # 0=free, 1=expensive
    environmental_risk: float = 0.0         # 0=no risk, 1=high risk

    # Parameters that define the action (settings, quantities, etc.)
    parameters: dict[str, Any] = field(default_factory=dict)

    def weighted_total(self, weights: dict[ObjectiveType, float]) -> float:
        """Compute weighted score given objective weights."""
        total = 0.0
        total_weight = 0.0
        for os in self.objective_scores:
            w = weights.get(os.objective, 1.0 / len(ObjectiveType))
            total += os.score * w
            total_weight += w
        # Penalise for high environmental risk and complexity
        base = total / total_weight if total_weight > 0 else 0.0
        base *= (1.0 - self.environmental_risk * 0.3)
        base *= (1.0 - self.implementation_complexity * 0.1)
        return min(1.0, max(0.0, base))


# ─── Decision matrix ──────────────────────────────────────────────────────────

@dataclass
class DecisionMatrix:
    """
    The full decision matrix for one lagoon at one point in time.

    Contains all generated options, their scores, and the final ranking.
    This is the primary audit record for a decision cycle.
    """
    id: UUID = field(default_factory=uuid4)
    lagoon_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    # System state that triggered this decision
    system_state: LagoonSystemState | None = None

    # All options generated and evaluated
    options: list[DecisionOption] = field(default_factory=list)

    # Ranked order (index into options list)
    ranked_indices: list[int] = field(default_factory=list)

    # Objective weights used for scoring
    objective_weights: dict[str, float] = field(default_factory=dict)

    # Decision context
    trigger_event: str = ""
    decision_narrative: str = ""
    ai_reasoning: str = ""

    @property
    def best_option(self) -> DecisionOption | None:
        if self.ranked_indices and self.options:
            return self.options[self.ranked_indices[0]]
        return None

    @property
    def ranked_options(self) -> list[DecisionOption]:
        return [self.options[i] for i in self.ranked_indices if i < len(self.options)]


# ─── Final recommendation ─────────────────────────────────────────────────────

@dataclass
class RankedRecommendation:
    """
    A recommendation ready for presentation to operators.

    This is the output of the Decision Engine — a ranked, explained,
    and explainable recommendation with full audit trail.
    """
    id: UUID = field(default_factory=uuid4)
    lagoon_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    # Primary recommendation
    recommended_action: str = ""
    category: ActionCategory = ActionCategory.OBSERVATION
    urgency: RecommendationUrgency = RecommendationUrgency.ROUTINE
    confidence: float = 0.0
    overall_score: float = 0.0

    # Explanation (mandatory)
    why_recommended: str = ""
    what_will_happen: str = ""
    expected_timeframe: str = ""
    contributing_loops: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    scientific_hypotheses: list[str] = field(default_factory=list)

    # Alternatives (mandatory — must explain why NOT chosen)
    alternative_options: list[dict[str, Any]] = field(default_factory=list)

    # Risk assessment
    risk_assessment: str = ""
    environmental_risk: float = 0.0

    # Parameters for execution
    parameters: dict[str, Any] = field(default_factory=dict)

    # Audit trail
    decision_matrix_id: UUID | None = None
    ai_reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API response and database persistence."""
        return {
            "id": str(self.id),
            "lagoon_id": str(self.lagoon_id),
            "created_at": self.created_at.isoformat(),
            "recommended_action": self.recommended_action,
            "category": self.category.value,
            "urgency": self.urgency.value,
            "confidence": self.confidence,
            "overall_score": self.overall_score,
            "why_recommended": self.why_recommended,
            "what_will_happen": self.what_will_happen,
            "expected_timeframe": self.expected_timeframe,
            "contributing_loops": self.contributing_loops,
            "supporting_evidence": self.supporting_evidence,
            "scientific_hypotheses": self.scientific_hypotheses,
            "alternative_options": self.alternative_options,
            "risk_assessment": self.risk_assessment,
            "environmental_risk": self.environmental_risk,
            "parameters": self.parameters,
            "decision_matrix_id": str(self.decision_matrix_id) if self.decision_matrix_id else None,
        }
