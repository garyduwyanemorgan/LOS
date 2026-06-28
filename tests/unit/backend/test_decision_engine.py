"""Unit tests for the Decision Engine."""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.decision_engine.engine import DecisionEngine
from backend.decision_engine.models import (
    ActionCategory,
    DecisionOption,
    LagoonSystemState,
    LoopStateSnapshot,
    ObjectiveType,
    RecommendationUrgency,
)
from backend.decision_engine.objectives import evaluate_option, DEFAULT_WEIGHTS


class TestObjectiveEvaluators:
    """Test individual objective scorer functions."""

    def _make_state(
        self,
        do_mg_l: float = 5.0,
        orp_mv: float = 100.0,
        bloom_prob: float = 0.2,
        cyano_risk: str = "low",
        aeration_status: str = "online",
    ) -> LagoonSystemState:
        state = LagoonSystemState(lagoon_id=uuid.uuid4())
        state.overall_confidence = 0.75
        state.chemical = LoopStateSnapshot(
            loop="chemical",
            confidence=0.80,
            status="healthy",
            state={
                "do_mg_l": do_mg_l,
                "orp_mv": orp_mv,
                "redox_class": "suboxic" if orp_mv < 200 else "oxic",
                "internal_loading_risk": "medium",
            },
        )
        state.ecological = LoopStateSnapshot(
            loop="ecological",
            confidence=0.70,
            status="healthy",
            state={
                "bloom_probability": bloom_prob,
                "cyanobacteria_risk": cyano_risk,
                "ecological_stability_score": 0.6,
                "recovery_potential": "medium",
            },
        )
        state.infrastructure = LoopStateSnapshot(
            loop="infrastructure",
            confidence=0.90,
            status="healthy",
            state={"aeration_status": aeration_status, "pump_status": "online"},
        )
        return state

    def _make_option(self, category: ActionCategory) -> DecisionOption:
        return DecisionOption(
            action_title=f"Test {category.value}",
            category=category,
            urgency=RecommendationUrgency.ROUTINE,
            confidence=0.75,
            operational_cost_index=0.4,
            environmental_risk=0.05,
            implementation_complexity=0.3,
            supporting_evidence=["Test evidence A", "Test evidence B"],
            causal_pathways=["Pathway 1"],
        )

    def test_aeration_scores_high_when_do_critical(self) -> None:
        """Aeration should score highest for water quality when DO is critical."""
        state = self._make_state(do_mg_l=1.5)  # critical DO
        aeration = self._make_option(ActionCategory.AERATION)
        monitoring = self._make_option(ActionCategory.MONITORING)

        evaluate_option(aeration, state)
        evaluate_option(monitoring, state)

        # Aeration should beat monitoring on water quality when DO is critical
        aeration_wq = next(
            s for s in aeration.objective_scores if s.objective == ObjectiveType.WATER_QUALITY
        )
        monitoring_wq = next(
            s for s in monitoring.objective_scores if s.objective == ObjectiveType.WATER_QUALITY
        )
        assert aeration_wq.score > monitoring_wq.score

    def test_no_action_penalised_during_critical_do(self) -> None:
        """No-action should score low on compliance and water quality when DO is critical."""
        state = self._make_state(do_mg_l=1.0)  # critically low
        no_action = self._make_option(ActionCategory.NO_ACTION)
        aeration = self._make_option(ActionCategory.AERATION)

        evaluate_option(no_action, state)
        evaluate_option(aeration, state)

        assert aeration.overall_score > no_action.overall_score

    def test_overall_score_in_valid_range(self) -> None:
        """Overall score must be in [0, 1]."""
        state = self._make_state()
        for category in ActionCategory:
            opt = self._make_option(category)
            evaluate_option(opt, state)
            assert 0.0 <= opt.overall_score <= 1.0, (
                f"{category}: score={opt.overall_score} out of range"
            )

    def test_objective_scores_populated(self) -> None:
        """All 7 objectives must be scored after evaluation."""
        state = self._make_state()
        opt = self._make_option(ActionCategory.AERATION)
        evaluate_option(opt, state)
        assert len(opt.objective_scores) == 7

    def test_high_env_risk_reduces_score(self) -> None:
        """High environmental risk must reduce the overall score."""
        state = self._make_state()
        low_risk = DecisionOption(
            action_title="Low risk", category=ActionCategory.AERATION,
            urgency=RecommendationUrgency.ROUTINE, confidence=0.7,
            operational_cost_index=0.4, environmental_risk=0.05,
            implementation_complexity=0.3,
        )
        high_risk = DecisionOption(
            action_title="High risk", category=ActionCategory.AERATION,
            urgency=RecommendationUrgency.ROUTINE, confidence=0.7,
            operational_cost_index=0.4, environmental_risk=0.80,
            implementation_complexity=0.3,
        )
        evaluate_option(low_risk, state)
        evaluate_option(high_risk, state)
        assert low_risk.overall_score > high_risk.overall_score


class TestDecisionEngine:
    """Integration tests for the DecisionEngine."""

    @pytest.mark.asyncio
    async def test_run_decision_cycle_returns_recommendation(
        self, mock_shared_memory, sample_lagoon_id
    ) -> None:
        """Decision cycle must return a recommendation."""
        # Configure mock to return a state with low DO
        mock_shared_memory.get_scientific_memory.return_value = {
            "do_mg_l": 2.5,
            "orp_mv": -50.0,
            "redox_class": "anoxic",
            "internal_loading_risk": "high",
            "confidence": 0.75,
            "status": "critical",
            "alerts": ["DO_CRITICAL"],
        }
        mock_shared_memory.get_learning_history.return_value = []

        engine = DecisionEngine(
            shared_memory=mock_shared_memory,
            srg=None,
        )
        recommendation = await engine.run_decision_cycle(
            lagoon_id=sample_lagoon_id,
            trigger_event="test",
        )

        assert recommendation is not None
        assert recommendation.recommended_action
        assert 0.0 <= recommendation.confidence <= 1.0
        assert 0.0 <= recommendation.overall_score <= 1.0
        assert recommendation.why_recommended
        assert len(recommendation.alternative_options) > 0

    @pytest.mark.asyncio
    async def test_aeration_recommended_for_critical_do(
        self, mock_shared_memory, sample_lagoon_id
    ) -> None:
        """Aeration should be top recommendation when DO is critically low."""
        mock_shared_memory.get_scientific_memory.return_value = {
            "do_mg_l": 1.2,  # below 2 mg/L — critical
            "orp_mv": -150.0,
            "redox_class": "reducing",
            "internal_loading_risk": "critical",
            "confidence": 0.85,
            "status": "critical",
            "alerts": ["DO_CRITICAL", "ORP_ANAEROBIC"],
        }
        mock_shared_memory.get_learning_history.return_value = []

        engine = DecisionEngine(shared_memory=mock_shared_memory, srg=None)
        recommendation = await engine.run_decision_cycle(lagoon_id=sample_lagoon_id)

        assert recommendation is not None
        # With critically low DO, aeration or circulation should be recommended
        assert recommendation.category in (
            ActionCategory.AERATION, ActionCategory.CIRCULATION
        ), f"Expected aeration/circulation but got {recommendation.category}"

    @pytest.mark.asyncio
    async def test_recommendation_has_all_required_fields(
        self, mock_shared_memory, sample_lagoon_id
    ) -> None:
        """RankedRecommendation must include all required explanation fields."""
        mock_shared_memory.get_scientific_memory.return_value = {
            "do_mg_l": 4.5,
            "confidence": 0.72,
            "status": "healthy",
            "alerts": [],
        }
        mock_shared_memory.get_learning_history.return_value = []

        engine = DecisionEngine(shared_memory=mock_shared_memory, srg=None)
        rec = await engine.run_decision_cycle(lagoon_id=sample_lagoon_id)

        assert rec is not None
        # Mandatory explanation fields
        assert rec.recommended_action != ""
        assert rec.why_recommended != ""
        assert rec.what_will_happen != ""
        assert rec.risk_assessment != ""
        assert isinstance(rec.contributing_loops, list)
        assert isinstance(rec.alternative_options, list)
        assert rec.decision_matrix_id is not None

    @pytest.mark.asyncio
    async def test_no_memory_produces_fallback_recommendation(
        self, sample_lagoon_id
    ) -> None:
        """Engine must still produce a recommendation when shared memory is unavailable."""
        engine = DecisionEngine(shared_memory=None, srg=None)
        rec = await engine.run_decision_cycle(lagoon_id=sample_lagoon_id)
        # Should return monitoring or no-action as safe default
        assert rec is not None
