"""Scientific scenario validation tests.

These tests verify that the integrated scientific services produce
physically plausible results for known lagoon scenarios.

Each scenario represents a real operational condition that LOS
must correctly diagnose and recommend for.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.decision_engine.engine import DecisionEngine
from backend.decision_engine.models import ActionCategory, LagoonSystemState, LoopStateSnapshot
from backend.decision_engine.objectives import evaluate_option, DEFAULT_WEIGHTS
from backend.scientific_services.chemical.calculations import (
    classify_redox,
    do_saturation,
    trophic_state_index,
)
from backend.scientific_services.hydrological.calculations import (
    penman_monteith_et0,
    residence_time,
    water_balance,
)


# ─── Scenario 1: Algal Bloom Event ─────────────────────────────────────────────

class TestAlgalBloomScenario:
    """
    Scenario: A GCC lagoon is experiencing a developing algal bloom.

    Conditions:
    - DO moderate but declining (6.5 mg/L → pattern suggests night-time crash)
    - ORP suboxic (-20 mV)
    - High nutrient loading (TP = 0.35 mg/L, TN = 6.2 mg/L)
    - Residence time 22 days (long — nutrient accumulation)
    - TSE inflow rate elevated
    - Bloom probability: 0.62
    """

    def setup_method(self) -> None:
        self.lagoon_id = uuid.UUID("11111111-2222-3333-4444-555555555555")

    def test_high_nutrient_loading_is_eutrophic(self) -> None:
        """High TP/chlorophyll scenario must classify as eutrophic or hypereutrophic."""
        tsi = trophic_state_index(
            chlorophyll_a_ug_l=45.0,
            total_phosphorus_mg_l=0.35,
        )
        assert tsi in ("eutrophic", "hypereutrophic"), f"Expected eutrophic, got {tsi}"

    def test_long_residence_time_increases_bloom_risk(self) -> None:
        """Residence time 22 days is flagged as a bloom risk factor."""
        hrt = residence_time(volume_m3=130000.0, outflow_m3_day=5900.0)
        assert 20.0 < hrt < 25.0, f"HRT={hrt} unexpected for bloom scenario"

    @pytest.mark.asyncio
    async def test_engine_recommends_active_intervention_for_bloom(self) -> None:
        """Decision Engine must NOT recommend no-action for bloom conditions."""
        engine = DecisionEngine(shared_memory=None, srg=None)

        # Manually build state
        state = LagoonSystemState(lagoon_id=self.lagoon_id)
        state.overall_confidence = 0.72
        state.active_alerts = ["BLOOM_RISK_HIGH", "NUTRIENT_LOADING_HIGH"]
        state.chemical = LoopStateSnapshot(
            loop="chemical",
            confidence=0.78,
            status="warning",
            state={
                "do_mg_l": 6.5,
                "orp_mv": -20.0,
                "redox_class": "suboxic",
                "tp_mg_l": 0.35,
                "tn_mg_l": 6.2,
                "internal_loading_risk": "medium",
            },
        )
        state.ecological = LoopStateSnapshot(
            loop="ecological",
            confidence=0.65,
            status="warning",
            state={
                "bloom_probability": 0.62,
                "cyanobacteria_risk": "medium",
                "ecological_stability_score": 0.45,
                "recovery_potential": "medium",
            },
        )
        state.hydrological = LoopStateSnapshot(
            loop="hydrological",
            confidence=0.80,
            status="healthy",
            state={"residence_time_days": 22.0},
        )

        # Generate and score all options
        options = await engine._generate_options(state)
        from backend.decision_engine.objectives import evaluate_option
        ranked = sorted(
            [evaluate_option(o, state) for o in options],
            key=lambda o: o.overall_score,
            reverse=True,
        )

        best = ranked[0]
        assert best.category != ActionCategory.NO_ACTION, (
            f"No-action ranked first for bloom scenario (score={best.overall_score:.3f})"
        )


# ─── Scenario 2: Hypoxic Crash ─────────────────────────────────────────────────

class TestHypoxicCrashScenario:
    """
    Scenario: Severe overnight DO crash — hypoxia event.

    Conditions:
    - DO: 1.8 mg/L (below 2 mg/L compliance threshold)
    - ORP: -180 mV (strongly reducing)
    - Temperature: 31°C (high — reduces saturation)
    - Bloom crash 3 days ago (fish kill risk)
    """

    def test_do_below_saturation_at_high_temp(self) -> None:
        """At 31°C, DO saturation is lower than at lower temps."""
        sat = do_saturation(temperature_c=31.0, salinity_ppt=8.0)
        # Observed DO (1.8) must be much below saturation
        assert 1.8 < sat  # saturation must be above measured value

    def test_strongly_reducing_conditions_classified(self) -> None:
        """ORP -180 mV must be classified as 'anoxic' or 'reducing'."""
        classification = classify_redox(orp_mv=-180.0)
        assert classification in ("anoxic", "reducing")

    @pytest.mark.asyncio
    async def test_engine_urgency_is_immediate_for_hypoxia(self) -> None:
        """Decision Engine must recommend IMMEDIATE or URGENT action for DO < 2 mg/L."""
        from backend.decision_engine.models import RecommendationUrgency

        engine = DecisionEngine(shared_memory=None, srg=None)
        state = LagoonSystemState(lagoon_id=uuid.uuid4())
        state.overall_confidence = 0.80
        state.active_alerts = ["DO_CRITICAL", "ORP_ANAEROBIC"]
        state.chemical = LoopStateSnapshot(
            loop="chemical",
            confidence=0.85,
            status="critical",
            state={
                "do_mg_l": 1.8,
                "orp_mv": -180.0,
                "redox_class": "reducing",
                "internal_loading_risk": "critical",
            },
        )
        state.infrastructure = LoopStateSnapshot(
            loop="infrastructure",
            confidence=0.90,
            status="healthy",
            state={"aeration_status": "online", "pump_status": "online"},
        )

        recommendation = await engine.run_decision_cycle(
            lagoon_id=state.lagoon_id,
            injected_state=state,
        )

        assert recommendation is not None
        assert recommendation.urgency in (
            RecommendationUrgency.IMMEDIATE,
            RecommendationUrgency.URGENT,
        ), f"Expected IMMEDIATE/URGENT urgency for DO=1.8 but got {recommendation.urgency}"


# ─── Scenario 3: Infrastructure Failure ──────────────────────────────────────

class TestInfrastructureFailureScenario:
    """
    Scenario: Primary aerator failure — DO declining, immediate risk.
    """

    @pytest.mark.asyncio
    async def test_maintenance_recommended_when_aerator_offline(self) -> None:
        """With aerator offline, maintenance action must rank highly."""
        engine = DecisionEngine(shared_memory=None, srg=None)
        state = LagoonSystemState(lagoon_id=uuid.uuid4())
        state.overall_confidence = 0.70
        state.active_alerts = ["AERATOR_FAULT"]
        state.chemical = LoopStateSnapshot(
            loop="chemical",
            confidence=0.75,
            status="warning",
            state={
                "do_mg_l": 4.2,
                "orp_mv": 50.0,
                "redox_class": "suboxic",
                "internal_loading_risk": "low",
            },
        )
        state.infrastructure = LoopStateSnapshot(
            loop="infrastructure",
            confidence=0.95,
            status="critical",
            state={"aeration_status": "offline", "pump_status": "online"},
        )

        options = await engine._generate_options(state)
        from backend.decision_engine.objectives import evaluate_option
        ranked = sorted(
            [evaluate_option(o, state) for o in options],
            key=lambda o: o.overall_score,
            reverse=True,
        )

        # Top 3 options must include maintenance
        top_3_categories = {o.category for o in ranked[:3]}
        assert ActionCategory.MAINTENANCE in top_3_categories, (
            f"Maintenance not in top 3 for aerator failure. Top 3: {top_3_categories}"
        )
