"""AI Orchestrator — LangGraph workflow coordinating the scientific loops.

The orchestrator is the cognitive layer that:
1. Reads the multi-loop system state from Shared Memory
2. Uses the Scientific Relationship Graph to generate hypotheses
3. Invokes the Decision Engine for multi-objective scoring
4. Uses Claude claude-sonnet-4-6 to generate explainable narrative
5. Persists the recommendation to the database via event bus

Architectural rules:
- Claude generates narrative, not scientific conclusions
- Scientific models are authoritative
- Every recommendation must be explainable from first principles
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from backend.core.config.settings import settings
from backend.decision_engine.models import (
    LagoonSystemState,
    ObjectiveType,
    RankedRecommendation,
)

if TYPE_CHECKING:
    from backend.decision_engine.engine import DecisionEngine

logger = logging.getLogger(__name__)

# ─── LangGraph state type ─────────────────────────────────────────────────────

try:
    from langgraph.graph import END, StateGraph
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning(
        "langgraph not installed — AI orchestrator will operate in direct mode. "
        "Install with: pip install langgraph"
    )

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning(
        "anthropic not installed — narrative generation disabled. "
        "Install with: pip install anthropic"
    )


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class AIOrchestrator:
    """
    LangGraph-powered AI orchestrator for lagoon operational intelligence.

    Uses a StateGraph to coordinate:
    - System state assembly
    - Hypothesis generation
    - Decision Engine evaluation
    - AI narrative generation
    - Recommendation publishing

    Falls back to direct mode (no LangGraph) if the library is unavailable.
    """

    def __init__(
        self,
        decision_engine: DecisionEngine,
        shared_memory: Any | None = None,
        srg: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self._engine = decision_engine
        self._memory = shared_memory
        self._srg = srg
        self._event_bus = event_bus
        self._anthropic: Any | None = None
        self._graph: Any | None = None

        self._initialise_anthropic()
        if LANGGRAPH_AVAILABLE:
            self._build_graph()

    def _initialise_anthropic(self) -> None:
        """Initialise Anthropic client if API key is available."""
        if not ANTHROPIC_AVAILABLE:
            return
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — AI narrative generation disabled")
            return
        self._anthropic = anthropic.AsyncAnthropic(api_key=api_key)
        logger.info("AI orchestrator: Anthropic client initialised (model: %s)", settings.AI_MODEL)

    def _build_graph(self) -> None:
        """Construct the LangGraph StateGraph."""
        try:
            from typing import TypedDict


            class OrchestratorState(TypedDict):
                lagoon_id: str
                trigger_event: str
                system_state: dict[str, Any]
                hypotheses: list[dict[str, Any]]
                recommendation: dict[str, Any] | None
                ai_narrative: str
                published: bool

            graph = StateGraph(OrchestratorState)

            graph.add_node("assemble_state", self._node_assemble_state)
            graph.add_node("generate_hypotheses", self._node_generate_hypotheses)
            graph.add_node("run_decision_engine", self._node_run_decision_engine)
            graph.add_node("generate_narrative", self._node_generate_narrative)
            graph.add_node("publish_recommendation", self._node_publish_recommendation)

            graph.set_entry_point("assemble_state")
            graph.add_edge("assemble_state", "generate_hypotheses")
            graph.add_edge("generate_hypotheses", "run_decision_engine")
            graph.add_edge("run_decision_engine", "generate_narrative")
            graph.add_edge("generate_narrative", "publish_recommendation")
            graph.add_edge("publish_recommendation", END)

            self._graph = graph.compile()
            logger.info("AI orchestrator: LangGraph workflow compiled successfully")
        except Exception as exc:
            logger.error("Failed to build LangGraph: %s — using direct mode", exc)
            self._graph = None

    # ──────────────────────────────────────────────────────────────────────────
    # Primary interface
    # ──────────────────────────────────────────────────────────────────────────

    async def orchestrate(
        self,
        lagoon_id: UUID,
        trigger_event: str = "scheduled",
        objective_weights: dict[ObjectiveType, float] | None = None,
    ) -> RankedRecommendation | None:
        """
        Run the full orchestration cycle for a lagoon.

        Uses LangGraph if available, otherwise direct mode.
        """
        if self._graph is not None:
            return await self._run_graph(lagoon_id, trigger_event, objective_weights)
        else:
            return await self._run_direct(lagoon_id, trigger_event, objective_weights)

    async def _run_graph(
        self,
        lagoon_id: UUID,
        trigger_event: str,
        objective_weights: dict[ObjectiveType, float] | None,
    ) -> RankedRecommendation | None:
        """Execute orchestration via LangGraph StateGraph."""
        try:
            initial_state = {
                "lagoon_id": str(lagoon_id),
                "trigger_event": trigger_event,
                "system_state": {},
                "hypotheses": [],
                "recommendation": None,
                "ai_narrative": "",
                "published": False,
            }
            final_state = await self._graph.ainvoke(initial_state)
            rec_dict = final_state.get("recommendation")
            if rec_dict is None:
                return None
            # Reconstruct RankedRecommendation from dict
            return self._dict_to_recommendation(rec_dict, lagoon_id)
        except Exception as exc:
            logger.error("LangGraph orchestration failed: %s — falling back to direct", exc)
            return await self._run_direct(lagoon_id, trigger_event, objective_weights)

    async def _run_direct(
        self,
        lagoon_id: UUID,
        trigger_event: str,
        objective_weights: dict[ObjectiveType, float] | None,
    ) -> RankedRecommendation | None:
        """Direct orchestration without LangGraph (fallback mode)."""
        recommendation = await self._engine.run_decision_cycle(
            lagoon_id=lagoon_id,
            trigger_event=trigger_event,
            objective_weights=objective_weights,
        )
        if recommendation and self._anthropic:
            recommendation.ai_reasoning = await self._generate_ai_narrative(recommendation)
        return recommendation

    # ──────────────────────────────────────────────────────────────────────────
    # LangGraph nodes
    # ──────────────────────────────────────────────────────────────────────────

    async def _node_assemble_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Node: Assemble current system state from all scientific loops."""
        lagoon_id = UUID(state["lagoon_id"])
        system_state = await self._engine._assemble_system_state(lagoon_id)
        return {"system_state": self._state_to_dict(system_state)}

    async def _node_generate_hypotheses(self, state: dict[str, Any]) -> dict[str, Any]:
        """Node: Query SRG for causal hypotheses based on active alerts."""
        if self._srg is None:
            return {"hypotheses": []}

        try:
            lagoon_id = UUID(state["lagoon_id"])
            sys_state = self._dict_to_system_state(state["system_state"], lagoon_id)
            enriched = await self._engine._enrich_with_srg(sys_state)
            return {"hypotheses": enriched.causal_hypotheses}
        except Exception as exc:
            logger.warning("Hypothesis node failed: %s", exc)
            return {"hypotheses": []}

    async def _node_run_decision_engine(self, state: dict[str, Any]) -> dict[str, Any]:
        """Node: Run the Decision Engine to produce a ranked recommendation."""
        try:
            lagoon_id = UUID(state["lagoon_id"])
            recommendation = await self._engine.run_decision_cycle(
                lagoon_id=lagoon_id,
                trigger_event=state.get("trigger_event", "scheduled"),
            )
            if recommendation:
                return {"recommendation": recommendation.to_dict()}
        except Exception as exc:
            logger.error("Decision engine node failed: %s", exc)
        return {"recommendation": None}

    async def _node_generate_narrative(self, state: dict[str, Any]) -> dict[str, Any]:
        """Node: Use Claude to generate explainable recommendation narrative."""
        rec = state.get("recommendation")
        if rec is None or self._anthropic is None:
            return {"ai_narrative": ""}

        try:
            narrative = await self._generate_ai_narrative_from_dict(rec, state)
            return {"ai_narrative": narrative}
        except Exception as exc:
            logger.warning("AI narrative generation failed: %s", exc)
            return {"ai_narrative": ""}

    async def _node_publish_recommendation(self, state: dict[str, Any]) -> dict[str, Any]:
        """Node: Publish the recommendation to the event bus."""
        rec = state.get("recommendation")
        if rec is None or self._event_bus is None:
            return {"published": False}

        try:

            from backend.event_bus.models import DecisionEvent, EventType

            event = DecisionEvent(
                lagoon_id=UUID(state["lagoon_id"]),
                source="ai-orchestrator",
                event_type=EventType.RECOMMENDATION_GENERATED.value,
                payload={
                    "recommendation": rec,
                    "ai_narrative": state.get("ai_narrative", ""),
                },
                confidence=rec.get("confidence", 0.5),
            )
            await self._event_bus.publish(event)
            return {"published": True}
        except Exception as exc:
            logger.warning("Recommendation publish failed: %s", exc)
            return {"published": False}

    # ──────────────────────────────────────────────────────────────────────────
    # AI narrative generation
    # ──────────────────────────────────────────────────────────────────────────

    async def _generate_ai_narrative(self, recommendation: RankedRecommendation) -> str:
        """Generate explainable narrative using Claude claude-sonnet-4-6."""
        return await self._generate_ai_narrative_from_dict(recommendation.to_dict(), {})

    async def _generate_ai_narrative_from_dict(
        self, rec: dict[str, Any], state: dict[str, Any]
    ) -> str:
        """Generate narrative from a recommendation dict."""
        if self._anthropic is None:
            return ""

        prompt = self._build_narrative_prompt(rec, state)

        try:
            response = await self._anthropic.messages.create(
                model=settings.AI_MODEL,
                max_tokens=1024,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
                system=(
                    "You are the AI component of the Lagoons Operating System, "
                    "a scientific environmental management platform. "
                    "Your role is to translate scientific analysis into clear, "
                    "actionable operational communication for environmental engineers and operators. "
                    "You never invent scientific conclusions — you explain the conclusions "
                    "produced by the scientific models. "
                    "Be concise, precise, and professionally confident. "
                    "Write in plain English suitable for an operational briefing."
                ),
            )
            return response.content[0].text if response.content else ""
        except Exception as exc:
            logger.warning("Anthropic API call failed: %s", exc)
            return ""

    def _build_narrative_prompt(self, rec: dict[str, Any], state: dict[str, Any]) -> str:
        """Build the prompt for AI narrative generation."""
        evidence = "\n".join(f"- {e}" for e in rec.get("supporting_evidence", []))
        hypotheses = "\n".join(f"- {h}" for h in rec.get("scientific_hypotheses", []))
        alternatives = "\n".join(
            f"- {a.get('action', '')} (score: {a.get('score', 0):.3f}): {a.get('why_not_recommended', '')}"
            for a in rec.get("alternative_options", [])
        )

        return f"""You have been provided with a scientific decision from the LOS Decision Engine.
Generate a clear operational briefing for the lagoon operations team.

RECOMMENDED ACTION: {rec.get('recommended_action', '')}
URGENCY: {rec.get('urgency', '')}
CONFIDENCE: {rec.get('confidence', 0):.0%}
OVERALL SCORE: {rec.get('overall_score', 0):.3f}

SCIENTIFIC REASONING:
{rec.get('why_recommended', '')}

EXPECTED OUTCOME:
{rec.get('what_will_happen', '')}

TIMEFRAME: {rec.get('expected_timeframe', '')}

SUPPORTING EVIDENCE:
{evidence}

CAUSAL HYPOTHESES:
{hypotheses}

ALTERNATIVES CONSIDERED:
{alternatives}

RISK ASSESSMENT:
{rec.get('risk_assessment', '')}

Write a 2-3 paragraph operational briefing that:
1. Explains what is happening in the lagoon and why (based on the scientific evidence above)
2. Explains why this specific action is recommended over the alternatives
3. Describes what operators should expect to observe after implementation

Do not invent facts. Base your explanation only on the evidence provided above."""

    # ──────────────────────────────────────────────────────────────────────────
    # Conversion helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _state_to_dict(self, state: LagoonSystemState) -> dict[str, Any]:
        return {
            "lagoon_id": str(state.lagoon_id),
            "overall_confidence": state.overall_confidence,
            "active_alerts": state.active_alerts,
            "available_loops": state.available_loops,
            "worst_alert_level": state.worst_alert_level,
            "chemical": state.chemical.state if state.chemical else {},
            "ecological": state.ecological.state if state.ecological else {},
            "hydrological": state.hydrological.state if state.hydrological else {},
            "infrastructure": state.infrastructure.state if state.infrastructure else {},
        }

    def _dict_to_system_state(
        self, data: dict[str, Any], lagoon_id: UUID
    ) -> LagoonSystemState:
        """Minimal reconstruction of LagoonSystemState from dict for SRG enrichment."""
        from backend.decision_engine.models import LoopStateSnapshot
        state = LagoonSystemState(lagoon_id=lagoon_id)
        state.overall_confidence = data.get("overall_confidence", 0.5)
        state.active_alerts = data.get("active_alerts", [])
        for loop_name in ("chemical", "ecological", "hydrological", "infrastructure"):
            if data.get(loop_name):
                setattr(
                    state,
                    loop_name,
                    LoopStateSnapshot(
                        loop=loop_name,
                        confidence=data.get("overall_confidence", 0.5),
                        status="unknown",
                        state=data[loop_name],
                    ),
                )
        return state

    def _dict_to_recommendation(
        self, rec_dict: dict[str, Any], lagoon_id: UUID
    ) -> RankedRecommendation:
        """Reconstruct RankedRecommendation from its serialised dict form."""
        from backend.decision_engine.models import ActionCategory, RecommendationUrgency
        return RankedRecommendation(
            lagoon_id=lagoon_id,
            recommended_action=rec_dict.get("recommended_action", ""),
            category=ActionCategory(rec_dict.get("category", "observation")),
            urgency=RecommendationUrgency(rec_dict.get("urgency", "monitoring")),
            confidence=rec_dict.get("confidence", 0.0),
            overall_score=rec_dict.get("overall_score", 0.0),
            why_recommended=rec_dict.get("why_recommended", ""),
            what_will_happen=rec_dict.get("what_will_happen", ""),
            expected_timeframe=rec_dict.get("expected_timeframe", ""),
            contributing_loops=rec_dict.get("contributing_loops", []),
            supporting_evidence=rec_dict.get("supporting_evidence", []),
            scientific_hypotheses=rec_dict.get("scientific_hypotheses", []),
            alternative_options=rec_dict.get("alternative_options", []),
            risk_assessment=rec_dict.get("risk_assessment", ""),
            environmental_risk=rec_dict.get("environmental_risk", 0.0),
            parameters=rec_dict.get("parameters", {}),
        )
