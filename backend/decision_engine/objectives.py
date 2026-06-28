"""Objective evaluators for all 7 LOS Operating Objectives.

Each evaluator takes the current LagoonSystemState and a candidate
DecisionOption and returns a score in [0, 1] with rationale.

Score = 0   →   action actively harms this objective
Score = 0.5 →   neutral or unknown impact
Score = 1.0 →   action strongly advances this objective
"""
from __future__ import annotations

import logging
from typing import Any

from backend.decision_engine.models import (
    ActionCategory,
    DecisionOption,
    LagoonSystemState,
    ObjectiveScore,
    ObjectiveType,
)

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _chem(state: LagoonSystemState) -> dict[str, Any]:
    if state.chemical:
        return state.chemical.state
    return {}


def _eco(state: LagoonSystemState) -> dict[str, Any]:
    if state.ecological:
        return state.ecological.state
    return {}


def _hydro(state: LagoonSystemState) -> dict[str, Any]:
    if state.hydrological:
        return state.hydrological.state
    return {}


def _infra(state: LagoonSystemState) -> dict[str, Any]:
    if state.infrastructure:
        return state.infrastructure.state
    return {}


# ─── Objective 1: Protect the Lagoon ──────────────────────────────────────────

def score_protect_lagoon(option: DecisionOption, state: LagoonSystemState) -> ObjectiveScore:
    """
    O1: Protect the Lagoon — structural integrity, water balance, infrastructure.

    High score for: maintenance actions, early intervention on failing infra,
    reducing stress on the ecosystem, monitoring escalation.
    Low score for: no-action when alerts are critical, actions with high environmental risk.
    """
    score = 0.5  # neutral baseline

    # Infrastructure maintenance and repair directly protect the lagoon
    if option.category in (ActionCategory.MAINTENANCE, ActionCategory.AERATION):
        score += 0.25

    # Monitoring is always protective (reduces blind spots)
    if option.category == ActionCategory.MONITORING:
        score += 0.15

    # Reduce score for high environmental risk
    score -= option.environmental_risk * 0.3

    # If infrastructure is in critical state, urgency is protective
    infra = _infra(state)
    if infra.get("aeration_status") == "offline" or infra.get("pump_status") == "offline":
        if option.category in (ActionCategory.MAINTENANCE, ActionCategory.AERATION):
            score += 0.25

    # No-action when lagoon is under stress is anti-protective
    if option.category == ActionCategory.NO_ACTION and state.worst_alert_level == "critical":
        score -= 0.3

    return ObjectiveScore(
        objective=ObjectiveType.PROTECT_LAGOON,
        score=_clamp(score),
        weighted_score=0.0,  # set by caller
        rationale=(
            f"Category={option.category.value}, "
            f"environmental_risk={option.environmental_risk:.2f}, "
            f"infra_status={infra.get('aeration_status', 'unknown')}"
        ),
    )


# ─── Objective 2: Improve Water Quality ───────────────────────────────────────

def score_water_quality(option: DecisionOption, state: LagoonSystemState) -> ObjectiveScore:
    """
    O2: Improve Water Quality — DO, nutrients, pH, ORP, salinity, turbidity.

    Score reflects how much the action is expected to improve key water quality
    parameters based on the current chemical loop state.
    """
    score = 0.5
    chem = _chem(state)

    do_mg_l: float | None = chem.get("do_mg_l")
    chem.get("orp_mv")
    internal_loading: str | None = chem.get("internal_loading_risk")

    # Aeration directly improves DO
    if option.category == ActionCategory.AERATION:
        if do_mg_l is not None and do_mg_l < 4.0:
            score += 0.40  # critical DO — aeration is highly beneficial
        elif do_mg_l is not None and do_mg_l < 6.0:
            score += 0.25
        else:
            score += 0.10

    # Circulation improves DO and reduces stratification
    if option.category == ActionCategory.CIRCULATION:
        score += 0.20

    # Reducing TSE directly reduces nutrient loading
    if option.category == ActionCategory.TSE_MANAGEMENT:
        score += 0.25

    # Chemical dosing can improve specific parameters
    if option.category == ActionCategory.CHEMICAL_DOSING:
        score += 0.15

    # Internal P release is a water quality threat — dredging reduces it
    if option.category == ActionCategory.DREDGING:
        if internal_loading in ("high", "critical"):
            score += 0.30
        else:
            score += 0.10

    # No-action during poor water quality
    if option.category == ActionCategory.NO_ACTION:
        if internal_loading in ("high", "critical") or (do_mg_l is not None and do_mg_l < 3.0):
            score -= 0.30

    return ObjectiveScore(
        objective=ObjectiveType.WATER_QUALITY,
        score=_clamp(score),
        weighted_score=0.0,
        rationale=(
            f"do_mg_l={do_mg_l}, internal_loading={internal_loading}, "
            f"category={option.category.value}"
        ),
    )


# ─── Objective 3: Ecological Stability ────────────────────────────────────────

def score_ecological_stability(option: DecisionOption, state: LagoonSystemState) -> ObjectiveScore:
    """
    O3: Maintain Ecological Stability — algal balance, bloom risk, recovery potential.
    """
    score = 0.5
    eco = _eco(state)

    bloom_prob: float | None = eco.get("bloom_probability")
    cyano_risk: str | None = eco.get("cyanobacteria_risk")
    stability: float | None = eco.get("ecological_stability_score")
    recovery: str | None = eco.get("recovery_potential")

    # Aeration breaks stratification, reduces bloom risk
    if option.category == ActionCategory.AERATION:
        if bloom_prob is not None and bloom_prob > 0.5:
            score += 0.35
        else:
            score += 0.15

    # Circulation reduces stagnation zones that favour blooms
    if option.category == ActionCategory.CIRCULATION:
        score += 0.20

    # TSE reduction reduces nutrient loading driving bloom
    if option.category == ActionCategory.TSE_MANAGEMENT:
        if bloom_prob is not None and bloom_prob > 0.6:
            score += 0.30
        else:
            score += 0.15

    # Dredging removes accumulated sludge — long-term ecological benefit
    if option.category == ActionCategory.DREDGING:
        score += 0.20

    # No-action during active or imminent bloom
    if option.category == ActionCategory.NO_ACTION:
        if bloom_prob is not None and bloom_prob > 0.7:
            score -= 0.35
        if cyano_risk in ("high", "critical"):
            score -= 0.25

    # Reward for recognising poor recovery potential
    if recovery == "low" and option.category != ActionCategory.NO_ACTION:
        score += 0.10

    return ObjectiveScore(
        objective=ObjectiveType.ECOLOGICAL_STABILITY,
        score=_clamp(score),
        weighted_score=0.0,
        rationale=(
            f"bloom_prob={bloom_prob}, cyano_risk={cyano_risk}, "
            f"stability={stability}, category={option.category.value}"
        ),
    )


# ─── Objective 4: Reduce Operational Cost ─────────────────────────────────────

def score_operational_cost(option: DecisionOption, state: LagoonSystemState) -> ObjectiveScore:
    """
    O4: Reduce Operational Cost — energy, maintenance, labs, chemicals.

    Inverted from the cost index: low-cost actions score high.
    No-action always scores maximum here but must be outweighed by other objectives.
    """
    # Direct inversion: low cost = high score
    cost_score = 1.0 - option.operational_cost_index

    # Monitoring is low-cost and enables cost-effective future decisions
    if option.category == ActionCategory.MONITORING:
        cost_score = max(cost_score, 0.80)

    # No-action is cheapest but may lead to expensive emergencies later
    if option.category == ActionCategory.NO_ACTION:
        cost_score = 0.85  # not 1.0 — opportunity cost of delayed intervention

    # Dredging is expensive — reflect that
    if option.category == ActionCategory.DREDGING:
        cost_score = min(cost_score, 0.25)

    # Emergency response is expensive — proactive maintenance is cheaper
    if option.urgency.value == "immediate" and option.category == ActionCategory.MAINTENANCE:
        cost_score *= 0.85  # emergency maintenance costs more

    return ObjectiveScore(
        objective=ObjectiveType.OPERATIONAL_COST,
        score=_clamp(cost_score),
        weighted_score=0.0,
        rationale=(
            f"cost_index={option.operational_cost_index:.2f}, "
            f"category={option.category.value}"
        ),
    )


# ─── Objective 5: Regulatory Compliance ──────────────────────────────────────

def score_regulatory_compliance(option: DecisionOption, state: LagoonSystemState) -> ObjectiveScore:
    """
    O5: Regulatory Compliance — water quality standards, permit conditions, reporting.

    Any action that directly addresses a compliance threshold scores high.
    No-action during a compliance breach scores very low.
    """
    score = 0.5
    chem = _chem(state)

    do_mg_l: float | None = chem.get("do_mg_l")
    chem.get("orp_mv")
    redox_class: str | None = chem.get("redox_class")

    # Compliance thresholds (common minimum standards)
    do_breach = do_mg_l is not None and do_mg_l < 2.0
    anoxic_breach = redox_class in ("anoxic", "reducing")

    # Aeration directly addresses DO compliance
    if option.category == ActionCategory.AERATION:
        if do_breach or anoxic_breach:
            score += 0.45
        else:
            score += 0.10

    # Monitoring is required for compliance reporting
    if option.category == ActionCategory.MONITORING:
        score += 0.20

    # Chemical dosing can address specific compliance parameters
    if option.category == ActionCategory.CHEMICAL_DOSING:
        score += 0.20

    # TSE management addresses nutrient compliance
    if option.category == ActionCategory.TSE_MANAGEMENT:
        score += 0.15

    # Infrastructure failure creates regulatory obligation to restore equipment
    if option.category == ActionCategory.MAINTENANCE:
        infra = _infra(state)
        if (
            state.infrastructure and state.infrastructure.status == "critical"
        ) or infra.get("aeration_status") == "offline" or infra.get("pump_status") == "offline":
            score += 0.40  # operator regulatory duty to restore critical equipment

    # No-action during compliance breach
    if option.category == ActionCategory.NO_ACTION and (do_breach or anoxic_breach):
        score -= 0.40

    return ObjectiveScore(
        objective=ObjectiveType.REGULATORY_COMPLIANCE,
        score=_clamp(score),
        weighted_score=0.0,
        rationale=(
            f"do_mg_l={do_mg_l}, do_breach={do_breach}, "
            f"redox={redox_class}, category={option.category.value}"
        ),
    )


# ─── Objective 6: Scientific Confidence ───────────────────────────────────────

def score_scientific_confidence(option: DecisionOption, state: LagoonSystemState) -> ObjectiveScore:
    """
    O6: Improve Scientific Confidence — prediction accuracy, model performance.

    Actions that generate measurable outcomes and monitoring data
    increase confidence. Options with high supporting evidence score higher.
    """
    score = 0.5

    # The option's own confidence correlates with scientific confidence
    score += (option.confidence - 0.5) * 0.4

    # Monitoring directly generates data → improves confidence
    if option.category == ActionCategory.MONITORING:
        score += 0.25

    # Number of supporting evidence items indicates confidence
    evidence_bonus = min(0.20, len(option.supporting_evidence) * 0.04)
    score += evidence_bonus

    # Options with higher overall system confidence are more reliable
    score += (state.overall_confidence - 0.5) * 0.15

    # Causal hypotheses from SRG indicate scientific understanding
    hypothesis_bonus = min(0.15, len(option.causal_pathways) * 0.03)
    score += hypothesis_bonus

    return ObjectiveScore(
        objective=ObjectiveType.SCIENTIFIC_CONFIDENCE,
        score=_clamp(score),
        weighted_score=0.0,
        rationale=(
            f"option_confidence={option.confidence:.2f}, "
            f"evidence_count={len(option.supporting_evidence)}, "
            f"system_confidence={state.overall_confidence:.2f}"
        ),
    )


# ─── Objective 7: Continuous Improvement ──────────────────────────────────────

def score_continuous_improvement(option: DecisionOption, state: LagoonSystemState) -> ObjectiveScore:
    """
    O7: Continuous Improvement — measurability, learning, trend improvement.

    Actions that create measurable outcomes (experiments) score high.
    Actions that address root causes score higher than symptom treatment.
    """
    score = 0.5

    # Actions that are addressng root causes score higher
    if len(option.causal_pathways) > 0:
        score += 0.20  # has SRG-grounded causal basis

    # Specific measurable parameters indicate trackable outcomes
    if option.expected_outcome:
        score += 0.10

    if option.expected_timeframe_hours is not None:
        score += 0.10  # specific timeframe enables comparison

    # Monitoring enables continuous improvement loop
    if option.category == ActionCategory.MONITORING:
        score += 0.15

    # Actions that were successful historically score higher
    # (reflected in option.confidence from learning engine)
    score += (option.confidence - 0.5) * 0.2

    # Dredging removes sludge permanently — long-term improvement
    if option.category == ActionCategory.DREDGING:
        score += 0.15

    # No-action misses improvement opportunity
    if option.category == ActionCategory.NO_ACTION:
        score -= 0.15

    return ObjectiveScore(
        objective=ObjectiveType.CONTINUOUS_IMPROVEMENT,
        score=_clamp(score),
        weighted_score=0.0,
        rationale=(
            f"has_causal_basis={len(option.causal_pathways) > 0}, "
            f"has_timeframe={option.expected_timeframe_hours is not None}, "
            f"category={option.category.value}"
        ),
    )


# ─── Master evaluator ─────────────────────────────────────────────────────────

DEFAULT_WEIGHTS: dict[ObjectiveType, float] = {
    ObjectiveType.PROTECT_LAGOON: 0.20,
    ObjectiveType.WATER_QUALITY: 0.20,
    ObjectiveType.ECOLOGICAL_STABILITY: 0.20,
    ObjectiveType.OPERATIONAL_COST: 0.10,
    ObjectiveType.REGULATORY_COMPLIANCE: 0.15,
    ObjectiveType.SCIENTIFIC_CONFIDENCE: 0.05,
    ObjectiveType.CONTINUOUS_IMPROVEMENT: 0.10,
}


def evaluate_option(
    option: DecisionOption,
    state: LagoonSystemState,
    weights: dict[ObjectiveType, float] | None = None,
) -> DecisionOption:
    """
    Evaluate a DecisionOption against all 7 objectives.

    Mutates the option in-place by populating objective_scores and overall_score.
    Returns the option for chaining.
    """
    w = weights or DEFAULT_WEIGHTS
    total_weight = sum(w.values())
    normalised = {obj: wt / total_weight for obj, wt in w.items()}

    evaluators = [
        score_protect_lagoon,
        score_water_quality,
        score_ecological_stability,
        score_operational_cost,
        score_regulatory_compliance,
        score_scientific_confidence,
        score_continuous_improvement,
    ]

    scores: list[ObjectiveScore] = []
    for evaluator in evaluators:
        try:
            os_ = evaluator(option, state)
            obj_weight = normalised.get(os_.objective, 1.0 / 7.0)
            os_.weighted_score = os_.score * obj_weight
            scores.append(os_)
        except Exception as exc:
            logger.warning("Objective evaluator %s failed: %s", evaluator.__name__, exc)

    option.objective_scores = scores
    option.overall_score = sum(s.weighted_score for s in scores)
    option.confidence = state.overall_confidence  # sync with system confidence
    return option
