"""Decision Engine — the operational brain of the Lagoons Operating System.

Implements the full decision cycle:
  Observe → Validate → Interpret → Generate Options → Evaluate →
  Rank → Recommend → Measure → Learn → Repeat

Architectural rules (from spec):
- Never bypasses scientific models
- Never invents scientific relationships
- Always references Shared Memory and SRG
- Every recommendation must be explainable
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from backend.decision_engine.models import (
    ActionCategory,
    DecisionMatrix,
    DecisionOption,
    LagoonSystemState,
    LoopStateSnapshot,
    ObjectiveType,
    RankedRecommendation,
    RecommendationUrgency,
)
from backend.decision_engine.objectives import DEFAULT_WEIGHTS, evaluate_option

logger = logging.getLogger(__name__)


# ─── Action library ───────────────────────────────────────────────────────────
# Pre-defined action templates. The engine selects and parameterises these
# based on the current system state. New templates can be added without
# modifying the scoring or ranking logic.

_ACTION_TEMPLATES: list[dict[str, Any]] = [
    {
        "action_title": "Increase Surface Aeration",
        "category": ActionCategory.AERATION,
        "urgency": RecommendationUrgency.URGENT,
        "scientific_reasoning": (
            "Mechanical aeration transfers oxygen from atmosphere to water, "
            "directly increasing DO and disrupting thermal stratification. "
            "SOTR ≈ 1.2-2.0 kg O₂/kWh at standard conditions."
        ),
        "expected_outcome": "DO increase by 1-3 mg/L within 4-8 hours.",
        "expected_timeframe_hours": 6.0,
        "operational_cost_index": 0.50,
        "environmental_risk": 0.05,
        "implementation_complexity": 0.20,
        "contributing_loops": ["infrastructure", "chemical"],
    },
    {
        "action_title": "Increase Lagoon Circulation",
        "category": ActionCategory.CIRCULATION,
        "urgency": RecommendationUrgency.URGENT,
        "scientific_reasoning": (
            "Increased circulation reduces residence time in stagnation zones, "
            "breaks thermal stratification, improves oxygen distribution, "
            "and reduces conditions favouring bloom formation."
        ),
        "expected_outcome": "Improved mixing and reduced stratification within 12-24 hours.",
        "expected_timeframe_hours": 18.0,
        "operational_cost_index": 0.40,
        "environmental_risk": 0.05,
        "implementation_complexity": 0.20,
        "contributing_loops": ["hydrological", "ecological"],
    },
    {
        "action_title": "Reduce TSE Inflow Volume",
        "category": ActionCategory.TSE_MANAGEMENT,
        "urgency": RecommendationUrgency.ROUTINE,
        "scientific_reasoning": (
            "Reducing treated sewage effluent inflow decreases nutrient loading (N, P), "
            "increases hydraulic residence time flushing, and reduces algal substrate availability."
        ),
        "expected_outcome": "Reduced nutrient concentration by 15-30% within 7-14 days.",
        "expected_timeframe_hours": 168.0,
        "operational_cost_index": 0.20,
        "environmental_risk": 0.10,
        "implementation_complexity": 0.30,
        "contributing_loops": ["hydrological", "chemical", "ecological"],
    },
    {
        "action_title": "Schedule Infrastructure Maintenance",
        "category": ActionCategory.MAINTENANCE,
        "urgency": RecommendationUrgency.ROUTINE,
        "scientific_reasoning": (
            "Proactive maintenance of aerators, pumps, and sensors maintains "
            "operational capability and prevents unplanned failures that cause "
            "DO crashes and compliance failures."
        ),
        "expected_outcome": "Restored full infrastructure capability within 24-48 hours.",
        "expected_timeframe_hours": 36.0,
        "operational_cost_index": 0.50,
        "environmental_risk": 0.02,
        "implementation_complexity": 0.40,
        "contributing_loops": ["infrastructure"],
    },
    {
        "action_title": "Escalate Monitoring Frequency",
        "category": ActionCategory.MONITORING,
        "urgency": RecommendationUrgency.ROUTINE,
        "scientific_reasoning": (
            "Increased sampling frequency improves confidence in trend detection, "
            "enables earlier intervention, and generates data to improve "
            "predictive model accuracy."
        ),
        "expected_outcome": "Improved system confidence and early warning capability within 24-48 hours.",
        "expected_timeframe_hours": 24.0,
        "operational_cost_index": 0.25,
        "environmental_risk": 0.00,
        "implementation_complexity": 0.10,
        "contributing_loops": ["chemical", "ecological"],
    },
    {
        "action_title": "Apply Algaecide Treatment",
        "category": ActionCategory.CHEMICAL_DOSING,
        "urgency": RecommendationUrgency.URGENT,
        "scientific_reasoning": (
            "Chemical algaecide (copper sulphate or hydrogen peroxide) directly "
            "targets algal cell structures, suppressing bloom. Requires careful "
            "dosing to avoid secondary DO crash from algal die-off."
        ),
        "expected_outcome": "Bloom suppression within 24-72 hours. Monitor DO closely.",
        "expected_timeframe_hours": 48.0,
        "operational_cost_index": 0.65,
        "environmental_risk": 0.40,
        "implementation_complexity": 0.60,
        "contributing_loops": ["chemical", "ecological"],
    },
    {
        "action_title": "Targeted Dredging Programme",
        "category": ActionCategory.DREDGING,
        "urgency": RecommendationUrgency.PLANNED,
        "scientific_reasoning": (
            "Mechanical removal of accumulated organic sediment (sludge) permanently "
            "reduces sediment oxygen demand (SOD), internal phosphorus loading, "
            "and harmful gas (H₂S, NH₃) production from anaerobic decomposition."
        ),
        "expected_outcome": "Sustained DO improvement and reduced internal P loading over 3-6 months.",
        "expected_timeframe_hours": 720.0,
        "operational_cost_index": 0.90,
        "environmental_risk": 0.35,
        "implementation_complexity": 0.90,
        "contributing_loops": ["ecological", "chemical", "hydrological"],
    },
    {
        "action_title": "Continue Observation — No Intervention",
        "category": ActionCategory.NO_ACTION,
        "urgency": RecommendationUrgency.MONITORING,
        "scientific_reasoning": (
            "Current system state does not require immediate intervention. "
            "Continued observation will confirm trends before action is taken. "
            "Premature intervention may disturb system equilibrium."
        ),
        "expected_outcome": "System remains stable under continued monitoring.",
        "expected_timeframe_hours": None,
        "operational_cost_index": 0.05,
        "environmental_risk": 0.00,
        "implementation_complexity": 0.00,
        "contributing_loops": [],
    },
]


class DecisionEngine:
    """
    Multi-objective Decision Engine for lagoon operational management.

    Generates and ranks candidate actions against the 7 LOS Operating Objectives.
    Every recommendation is fully explainable.
    """

    def __init__(
        self,
        shared_memory: Any | None = None,
        srg: Any | None = None,
    ) -> None:
        self._memory = shared_memory
        self._srg = srg
        logger.info("DecisionEngine initialised")

    # ──────────────────────────────────────────────────────────────────────────
    # Primary public interface
    # ──────────────────────────────────────────────────────────────────────────

    async def run_decision_cycle(
        self,
        lagoon_id: UUID,
        trigger_event: str = "scheduled",
        objective_weights: dict[ObjectiveType, float] | None = None,
        injected_state: LagoonSystemState | None = None,
    ) -> RankedRecommendation | None:
        """
        Execute a complete decision cycle for a lagoon.

        Returns the top-ranked recommendation or None if no action is warranted.
        ``injected_state`` bypasses shared-memory assembly (used in tests).
        """
        logger.info(
            "decision-cycle-start",
            extra={"lagoon_id": str(lagoon_id), "trigger": trigger_event},
        )

        # 1. Assemble current system state from all loops
        state = injected_state if injected_state is not None else await self._assemble_system_state(lagoon_id)

        # 2. Enrich with SRG hypotheses
        state = await self._enrich_with_srg(state)

        # 3. Generate candidate options (filtered to relevant actions)
        options = await self._generate_options(state)

        # 4. Evaluate each option against all 7 objectives
        weights = objective_weights or DEFAULT_WEIGHTS
        evaluated = [evaluate_option(opt, state, weights) for opt in options]

        # 5. Rank by overall score
        ranked = sorted(evaluated, key=lambda o: o.overall_score, reverse=True)

        if not ranked:
            logger.warning("No options generated for lagoon %s", lagoon_id)
            return None

        # 6. Build decision matrix (audit record)
        matrix = self._build_matrix(state, ranked, weights, trigger_event)

        # 7. Produce final recommendation
        recommendation = self._produce_recommendation(state, matrix, ranked)

        logger.info(
            "decision-cycle-complete",
            extra={
                "lagoon_id": str(lagoon_id),
                "recommended_action": recommendation.recommended_action,
                "confidence": recommendation.confidence,
                "score": recommendation.overall_score,
            },
        )
        return recommendation

    # ──────────────────────────────────────────────────────────────────────────
    # State assembly
    # ──────────────────────────────────────────────────────────────────────────

    async def _assemble_system_state(self, lagoon_id: UUID) -> LagoonSystemState:
        """Collect state from all scientific loops via Shared Memory."""
        state = LagoonSystemState(lagoon_id=lagoon_id)

        if self._memory is None:
            logger.warning("No shared memory — assembling minimal state")
            return state

        try:
            # Pull the latest scientific memory for each loop
            for loop_name in ("hydrological", "chemical", "ecological", "infrastructure"):
                loop_data = await self._memory.get_scientific_memory(lagoon_id, loop_name)
                if loop_data:
                    snapshot = LoopStateSnapshot(
                        loop=loop_name,
                        confidence=loop_data.get("confidence", 0.5),
                        status=loop_data.get("status", "unknown"),
                        state=loop_data,
                        alerts=loop_data.get("alerts", []),
                    )
                    setattr(state, loop_name, snapshot)

            # Load recent interventions (for learning context)
            learning = await self._memory.get_learning_history(lagoon_id, days=30)
            state.recent_interventions = learning[:10]  # last 10 interventions

            # Compute overall confidence as mean of available loops
            confidences = [
                snap.confidence
                for snap in [state.hydrological, state.chemical,
                             state.ecological, state.infrastructure]
                if snap is not None
            ]
            state.overall_confidence = (
                sum(confidences) / len(confidences) if confidences else 0.3
            )

            # Aggregate alerts
            for loop in [state.hydrological, state.chemical,
                        state.ecological, state.infrastructure]:
                if loop:
                    state.active_alerts.extend(loop.alerts)

        except Exception as exc:
            logger.error("Failed to assemble system state: %s", exc)

        return state

    async def _enrich_with_srg(self, state: LagoonSystemState) -> LagoonSystemState:
        """Query SRG for causal hypotheses based on current alerts."""
        if self._srg is None:
            return state

        try:
            for alert in state.active_alerts[:5]:  # limit to top 5 alerts
                hypotheses = await self._srg.generate_hypotheses(
                    condition=alert,
                    lagoon_id=state.lagoon_id,
                    top_n=3,
                )
                for h in hypotheses:
                    state.causal_hypotheses.append({
                        "condition": h.condition_observed,
                        "candidate_cause": h.candidate_cause,
                        "confidence": h.confidence,
                        "narrative": h.narrative,
                        "rank": h.rank,
                    })
        except Exception as exc:
            logger.warning("SRG enrichment failed: %s", exc)

        return state

    # ──────────────────────────────────────────────────────────────────────────
    # Option generation
    # ──────────────────────────────────────────────────────────────────────────

    async def _generate_options(self, state: LagoonSystemState) -> list[DecisionOption]:
        """
        Generate relevant candidate actions based on current system state.

        All 8 templates are always included (scored to 0 if irrelevant),
        plus any action-specific options derived from SRG hypotheses.
        """
        options: list[DecisionOption] = []

        # Build supporting evidence from current state
        evidence = self._build_evidence(state)

        # Causal pathways from SRG hypotheses
        pathways = [h.get("narrative", "") for h in state.causal_hypotheses]

        for template in _ACTION_TEMPLATES:
            opt = DecisionOption(
                id=uuid4(),
                action_title=template["action_title"],
                category=template["category"],
                urgency=self._adjust_urgency(template["urgency"], state),
                scientific_reasoning=template["scientific_reasoning"],
                expected_outcome=template["expected_outcome"],
                expected_timeframe_hours=template["expected_timeframe_hours"],
                operational_cost_index=template["operational_cost_index"],
                environmental_risk=template["environmental_risk"],
                implementation_complexity=template["implementation_complexity"],
                contributing_loops=list(
                    set(template["contributing_loops"]) & set(state.available_loops)
                ),
                supporting_evidence=evidence,
                causal_pathways=pathways[:3],
                confidence=state.overall_confidence,
            )
            options.append(opt)

        return options

    def _adjust_urgency(
        self,
        base_urgency: RecommendationUrgency,
        state: LagoonSystemState,
    ) -> RecommendationUrgency:
        """Escalate urgency if system state is critical."""
        if state.worst_alert_level == "critical":
            if base_urgency == RecommendationUrgency.ROUTINE:
                return RecommendationUrgency.URGENT
            if base_urgency == RecommendationUrgency.PLANNED:
                return RecommendationUrgency.ROUTINE
        return base_urgency

    def _build_evidence(self, state: LagoonSystemState) -> list[str]:
        """Extract key scientific evidence strings from current state."""
        evidence: list[str] = []

        if state.chemical:
            chem = state.chemical.state
            if (do := chem.get("do_mg_l")) is not None:
                evidence.append(f"DO = {do:.1f} mg/L")
            if (orp := chem.get("orp_mv")) is not None:
                evidence.append(f"ORP = {orp:.0f} mV ({chem.get('redox_class', '')})")
            if ph := chem.get("ph"):
                evidence.append(f"pH = {ph:.1f}")
            if load := chem.get("internal_loading_risk"):
                evidence.append(f"Internal P loading risk: {load}")

        if state.ecological:
            eco = state.ecological.state
            if (bp := eco.get("bloom_probability")) is not None:
                evidence.append(f"Bloom probability = {bp:.0%}")
            if risk := eco.get("cyanobacteria_risk"):
                evidence.append(f"Cyanobacteria risk: {risk}")

        if state.hydrological:
            hydro = state.hydrological.state
            if rt := hydro.get("residence_time_days"):
                evidence.append(f"Residence time = {rt:.1f} days")

        for h in state.causal_hypotheses[:3]:
            evidence.append(f"SRG: {h.get('narrative', '')}")

        return evidence

    # ──────────────────────────────────────────────────────────────────────────
    # Matrix and ranking
    # ──────────────────────────────────────────────────────────────────────────

    def _build_matrix(
        self,
        state: LagoonSystemState,
        ranked_options: list[DecisionOption],
        weights: dict[ObjectiveType, float],
        trigger_event: str,
    ) -> DecisionMatrix:
        """Build the decision matrix audit record."""
        matrix = DecisionMatrix(
            lagoon_id=state.lagoon_id,
            system_state=state,
            options=ranked_options,
            ranked_indices=list(range(len(ranked_options))),
            objective_weights={k.value: v for k, v in weights.items()},
            trigger_event=trigger_event,
        )
        return matrix

    def _produce_recommendation(
        self,
        state: LagoonSystemState,
        matrix: DecisionMatrix,
        ranked: list[DecisionOption],
    ) -> RankedRecommendation:
        """Convert the top-ranked option into a RankedRecommendation."""
        best = ranked[0]
        alternatives = ranked[1:4]  # next 3 options

        # Build alternative descriptions with rejection rationale
        alt_dicts: list[dict[str, Any]] = []
        for i, alt in enumerate(alternatives):
            alt_dicts.append({
                "rank": i + 2,
                "action": alt.action_title,
                "score": round(alt.overall_score, 3),
                "why_not_recommended": self._why_not(best, alt),
                "category": alt.category.value,
                "confidence": round(alt.confidence, 3),
            })

        # Generate narrative explanation
        why = self._generate_why_narrative(best, state)
        risk = self._generate_risk_narrative(best)

        return RankedRecommendation(
            lagoon_id=state.lagoon_id,
            recommended_action=best.action_title,
            category=best.category,
            urgency=best.urgency,
            confidence=round(best.confidence, 3),
            overall_score=round(best.overall_score, 3),
            why_recommended=why,
            what_will_happen=best.expected_outcome,
            expected_timeframe=(
                f"{best.expected_timeframe_hours:.0f} hours"
                if best.expected_timeframe_hours
                else "Ongoing"
            ),
            contributing_loops=best.contributing_loops,
            supporting_evidence=best.supporting_evidence,
            scientific_hypotheses=[h.get("narrative", "") for h in state.causal_hypotheses[:3]],
            alternative_options=alt_dicts,
            risk_assessment=risk,
            environmental_risk=best.environmental_risk,
            parameters=best.parameters,
            decision_matrix_id=matrix.id,
        )

    def _why_not(self, winner: DecisionOption, loser: DecisionOption) -> str:
        """Generate a brief explanation of why the loser was ranked below winner."""
        winner.overall_score - loser.overall_score
        if loser.environmental_risk > winner.environmental_risk + 0.1:
            return f"Higher environmental risk ({loser.environmental_risk:.0%} vs {winner.environmental_risk:.0%})"
        if loser.operational_cost_index > winner.operational_cost_index + 0.2:
            return f"Higher operational cost (index {loser.operational_cost_index:.1f} vs {winner.operational_cost_index:.1f})"
        return f"Lower overall objective score ({loser.overall_score:.3f} vs {winner.overall_score:.3f})"

    def _generate_why_narrative(
        self, option: DecisionOption, state: LagoonSystemState
    ) -> str:
        """Generate human-readable explanation of recommendation rationale."""
        parts: list[str] = []

        if option.category == ActionCategory.AERATION:
            chem = state.chemical.state if state.chemical else {}
            do = chem.get("do_mg_l")
            if do is not None:
                parts.append(
                    f"Dissolved oxygen ({do:.1f} mg/L) is "
                    + ("critically low" if do < 2.0 else "below optimal")
                    + ", requiring immediate oxygenation."
                )
        elif option.category == ActionCategory.CIRCULATION:
            parts.append(
                "Thermal stratification or stagnation zones are reducing "
                "oxygen distribution across the lagoon."
            )
        elif option.category == ActionCategory.TSE_MANAGEMENT:
            parts.append(
                "Nutrient loading from TSE inflow is elevated, driving "
                "algal growth and depleting oxygen through decomposition."
            )
        elif option.category == ActionCategory.MONITORING:
            parts.append(
                "System confidence is insufficient to recommend active intervention. "
                "Increased monitoring will improve decision quality."
            )
        elif option.category == ActionCategory.NO_ACTION:
            parts.append(
                "Current conditions do not warrant active intervention. "
                "The lagoon appears to be within acceptable operating bounds."
            )

        # Add contributing loops
        if option.contributing_loops:
            parts.append(
                f"Evidence from: {', '.join(option.contributing_loops)} loop(s)."
            )

        # Add top causal hypothesis
        if state.causal_hypotheses:
            top = state.causal_hypotheses[0]
            parts.append(
                f"Scientific analysis identifies {top.get('candidate_cause', 'unknown')} "
                f"as probable root cause (confidence: {top.get('confidence', 0.0):.0%})."
            )

        return " ".join(parts) if parts else option.scientific_reasoning

    def _generate_risk_narrative(self, option: DecisionOption) -> str:
        """Generate risk assessment narrative."""
        if option.environmental_risk < 0.1:
            return "Low environmental risk. Standard operational monitoring recommended."
        elif option.environmental_risk < 0.3:
            return (
                "Moderate environmental risk. Monitor DO and ecological indicators "
                "closely during implementation."
            )
        else:
            return (
                f"Elevated environmental risk ({option.environmental_risk:.0%}). "
                "Requires engineer oversight, detailed implementation plan, "
                "and continuous monitoring during and after treatment."
            )
