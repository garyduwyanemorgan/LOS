"""End-to-end pipeline tests.

These tests exercise the complete LOS processing chain:
  sensor observation → shared memory → scientific services →
  decision engine → recommendation

All external dependencies (Redis, PostgreSQL, Neo4j) are mocked.
The tests verify that real business logic flows correctly end-to-end.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.decision_engine.engine import DecisionEngine
from backend.decision_engine.models import (
    ActionCategory,
    LagoonSystemState,
    LoopStateSnapshot,
    RecommendationUrgency,
)
from backend.scientific_services.chemical.calculations import (
    classify_redox,
    do_saturation,
    trophic_state_index,
)
from backend.scientific_services.hydrological.calculations import (
    water_balance,
    residence_time,
    penman_monteith_et0,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def lagoon_id() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def mock_shared_memory() -> AsyncMock:
    sm = AsyncMock()
    sm.get = AsyncMock(return_value=None)
    sm.set = AsyncMock(return_value=True)
    return sm


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    bus.subscribe = AsyncMock()
    return bus


# ─── Test 1: Hydrological Service Data Flow ───────────────────────────────────

class TestHydrologicalServicePipeline:
    """Hydrological service processes sensor events and computes state."""

    @pytest.mark.asyncio
    async def test_sensor_event_updates_cache_and_state_computed(
        self, lagoon_id: uuid.UUID, mock_shared_memory: AsyncMock, mock_event_bus: AsyncMock
    ) -> None:
        """A sensor event received by the service updates the internal cache."""
        from backend.scientific_services.hydrological.service import HydrologicalService

        svc = HydrologicalService(
            shared_memory=mock_shared_memory,
            event_bus=mock_event_bus,
        )

        # Simulate receiving a water level event
        await svc.process_event({
            "topic": "sensor.water_level",
            "lagoon_id": str(lagoon_id),
            "timestamp": "2026-06-26T10:00:00Z",
            "data": {
                "value_m": 1.85,
                "volume_m3": 92500.0,
                "surface_area_m2": 50000.0,
            },
        })

        # Simulate a flow event
        await svc.process_event({
            "topic": "sensor.flow",
            "lagoon_id": str(lagoon_id),
            "timestamp": "2026-06-26T10:00:00Z",
            "data": {
                "inflow_m3_day": 8200.0,
                "outflow_m3_day": 7900.0,
            },
        })

        state = await svc.compute_state(lagoon_id)

        assert state["water_level_m"] == pytest.approx(1.85)
        assert state["volume_m3"] == pytest.approx(92500.0)
        assert state["inflow_m3_day"] == pytest.approx(8200.0)
        assert state["outflow_m3_day"] == pytest.approx(7900.0)
        assert state["confidence"] > 0.0
        assert state["data_completeness_pct"] > 0

    @pytest.mark.asyncio
    async def test_publish_state_writes_to_shared_memory(
        self, lagoon_id: uuid.UUID, mock_shared_memory: AsyncMock, mock_event_bus: AsyncMock
    ) -> None:
        """publish_state must write to shared memory and publish to event bus."""
        from backend.scientific_services.hydrological.service import HydrologicalService

        svc = HydrologicalService(
            shared_memory=mock_shared_memory,
            event_bus=mock_event_bus,
        )
        await svc.process_event({
            "topic": "sensor.water_level",
            "lagoon_id": str(lagoon_id),
            "data": {"value_m": 2.1, "volume_m3": 105000.0, "surface_area_m2": 50000.0},
        })

        await svc.publish_state(lagoon_id)

        mock_shared_memory.set.assert_called_once()
        call_args = mock_shared_memory.set.call_args
        assert f"hydro:{lagoon_id}" == call_args[0][0]

        mock_event_bus.publish.assert_called_once()
        publish_call = mock_event_bus.publish.call_args
        assert publish_call[1]["topic"] == "scientific.hydrological.state"


# ─── Test 2: Chemical Service Data Flow ───────────────────────────────────────

class TestChemicalServicePipeline:
    """Chemical service computes water chemistry state from sensor data."""

    @pytest.mark.asyncio
    async def test_sensor_event_triggers_chemical_state(
        self, lagoon_id: uuid.UUID, mock_shared_memory: AsyncMock, mock_event_bus: AsyncMock
    ) -> None:
        """Chemical service processes DO/ORP events and computes classification."""
        from backend.scientific_services.chemical.service import ChemicalService

        svc = ChemicalService(
            shared_memory=mock_shared_memory,
            event_bus=mock_event_bus,
        )

        await svc.process_event({
            "topic": "sensor.water_quality",
            "lagoon_id": str(lagoon_id),
            "data": {
                "do_mg_l": 5.8,
                "orp_mv": 120.0,
                "ph": 7.9,
                "ec_us_cm": 42000.0,
                "salinity_ppt": 25.0,
                "temperature_c": 28.0,
                "turbidity_ntu": 8.5,
                "tss_mg_l": 12.0,
            },
        })

        state = await svc.compute_state(lagoon_id)

        assert state["do_mg_l"] == pytest.approx(5.8)
        assert state["redox_class"] is not None
        assert state["trophic_state"] is not None
        assert 0.0 <= state["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_anoxic_conditions_detected_correctly(
        self, lagoon_id: uuid.UUID, mock_shared_memory: AsyncMock, mock_event_bus: AsyncMock
    ) -> None:
        """Anoxic conditions (DO < 2.0, ORP < -100) must be correctly classified."""
        from backend.scientific_services.chemical.service import ChemicalService

        svc = ChemicalService(
            shared_memory=mock_shared_memory,
            event_bus=mock_event_bus,
        )

        await svc.process_event({
            "topic": "sensor.water_quality",
            "lagoon_id": str(lagoon_id),
            "data": {
                "do_mg_l": 1.2,
                "orp_mv": -220.0,
                "ph": 7.2,
                "temperature_c": 32.0,
            },
        })

        state = await svc.compute_state(lagoon_id)

        assert state["redox_class"] in ("anoxic", "reducing"), (
            f"Expected anoxic/reducing, got {state['redox_class']}"
        )
        assert state["do_mg_l"] == pytest.approx(1.2)


# ─── Test 3: Decision Engine Full Cycle ───────────────────────────────────────

class TestDecisionEnginePipeline:
    """Decision engine synthesises state from all loops and produces recommendations."""

    @pytest.mark.asyncio
    async def test_full_decision_cycle_normal_conditions(self, lagoon_id: uuid.UUID) -> None:
        """Decision engine produces a valid recommendation under normal conditions."""
        engine = DecisionEngine(shared_memory=None, srg=None)
        state = LagoonSystemState(lagoon_id=lagoon_id)
        state.overall_confidence = 0.75
        state.active_alerts = []
        state.chemical = LoopStateSnapshot(
            loop="chemical",
            confidence=0.80,
            status="healthy",
            state={
                "do_mg_l": 7.5,
                "orp_mv": 280.0,
                "redox_class": "oxic",
                "internal_loading_risk": "low",
            },
        )
        state.ecological = LoopStateSnapshot(
            loop="ecological",
            confidence=0.70,
            status="healthy",
            state={
                "bloom_probability": 0.15,
                "cyanobacteria_risk": "low",
                "ecological_stability_score": 0.82,
            },
        )
        state.hydrological = LoopStateSnapshot(
            loop="hydrological",
            confidence=0.85,
            status="healthy",
            state={"residence_time_days": 12.0},
        )
        state.infrastructure = LoopStateSnapshot(
            loop="infrastructure",
            confidence=0.90,
            status="healthy",
            state={"aeration_status": "online", "pump_status": "online"},
        )

        recommendation = await engine.run_decision_cycle(
            lagoon_id=lagoon_id,
            injected_state=state,
        )

        assert recommendation is not None
        assert recommendation.lagoon_id == lagoon_id
        assert 0.0 < recommendation.confidence <= 1.0
        assert recommendation.recommended_action is not None
        assert recommendation.urgency is not None

    @pytest.mark.asyncio
    async def test_full_decision_cycle_emergency_aerator_failure(
        self, lagoon_id: uuid.UUID
    ) -> None:
        """Aerator failure + declining DO must produce URGENT or IMMEDIATE recommendation."""
        engine = DecisionEngine(shared_memory=None, srg=None)
        state = LagoonSystemState(lagoon_id=lagoon_id)
        state.overall_confidence = 0.85
        state.active_alerts = ["AERATOR_FAULT", "DO_DECLINING"]
        state.chemical = LoopStateSnapshot(
            loop="chemical",
            confidence=0.88,
            status="warning",
            state={
                "do_mg_l": 3.1,
                "orp_mv": -30.0,
                "redox_class": "suboxic",
                "internal_loading_risk": "medium",
            },
        )
        state.infrastructure = LoopStateSnapshot(
            loop="infrastructure",
            confidence=0.95,
            status="critical",
            state={"aeration_status": "offline", "pump_status": "online"},
        )

        recommendation = await engine.run_decision_cycle(
            lagoon_id=lagoon_id,
            injected_state=state,
        )

        assert recommendation is not None
        assert recommendation.urgency in (
            RecommendationUrgency.IMMEDIATE,
            RecommendationUrgency.URGENT,
        )

    @pytest.mark.asyncio
    async def test_decision_cycle_returns_none_for_unknown_lagoon(self) -> None:
        """Engine returns None rather than crashing for a lagoon with no state data."""
        engine = DecisionEngine(shared_memory=None, srg=None)
        unknown_lagoon = uuid.uuid4()

        # Engine should handle gracefully — either None or a low-confidence recommendation
        try:
            result = await engine.run_decision_cycle(lagoon_id=unknown_lagoon)
            # If it returns, it should be None or a valid recommendation
            if result is not None:
                assert result.lagoon_id == unknown_lagoon
        except Exception as exc:
            pytest.fail(f"Engine raised unexpected exception for unknown lagoon: {exc}")


# ─── Test 4: Shared Memory Round-Trip ─────────────────────────────────────────

class TestSharedMemoryIntegration:
    """Verify that scientific state flows through shared memory between services."""

    @pytest.mark.asyncio
    async def test_hydrological_state_stored_with_ttl(
        self, lagoon_id: uuid.UUID
    ) -> None:
        """Hydrological state must be stored with a TTL for cache expiry."""
        sm = AsyncMock()
        sm.get = AsyncMock(return_value=None)
        sm.set = AsyncMock(return_value=True)
        bus = AsyncMock()
        bus.publish = AsyncMock(return_value=True)

        from backend.scientific_services.hydrological.service import HydrologicalService

        svc = HydrologicalService(shared_memory=sm, event_bus=bus)
        await svc.process_event({
            "topic": "sensor.water_level",
            "lagoon_id": str(lagoon_id),
            "data": {"value_m": 1.9, "volume_m3": 95000.0, "surface_area_m2": 50000.0},
        })
        await svc.publish_state(lagoon_id)

        sm.set.assert_called_once()
        _, call_kwargs = sm.set.call_args
        # TTL must be set — state should expire, not persist indefinitely
        assert call_kwargs.get("ttl_seconds", 0) > 0, "State must be stored with a TTL"


# ─── Test 5: Event Bus Publication Flow ───────────────────────────────────────

class TestEventBusPipeline:
    """State changes must trigger event publication to the correct topics."""

    @pytest.mark.asyncio
    async def test_chemical_state_published_to_correct_topic(
        self, lagoon_id: uuid.UUID
    ) -> None:
        """Chemical state must be published to 'scientific.chemical.state' topic."""
        sm = AsyncMock()
        sm.get = AsyncMock(return_value=None)
        sm.set = AsyncMock(return_value=True)
        bus = AsyncMock()
        bus.publish = AsyncMock(return_value=True)

        from backend.scientific_services.chemical.service import ChemicalService

        svc = ChemicalService(shared_memory=sm, event_bus=bus)
        await svc.process_event({
            "topic": "sensor.water_quality",
            "lagoon_id": str(lagoon_id),
            "data": {"do_mg_l": 7.0, "orp_mv": 200.0, "temperature_c": 25.0},
        })
        await svc.publish_state(lagoon_id)

        bus.publish.assert_called_once()
        publish_kwargs = bus.publish.call_args[1]
        assert "chemical" in publish_kwargs["topic"], (
            f"Chemical state not published to chemical topic: {publish_kwargs['topic']}"
        )

    @pytest.mark.asyncio
    async def test_hydrological_state_published_to_correct_topic(
        self, lagoon_id: uuid.UUID
    ) -> None:
        """Hydrological state must be published to 'scientific.hydrological.state' topic."""
        sm = AsyncMock()
        sm.set = AsyncMock(return_value=True)
        bus = AsyncMock()
        bus.publish = AsyncMock(return_value=True)

        from backend.scientific_services.hydrological.service import HydrologicalService

        svc = HydrologicalService(shared_memory=sm, event_bus=bus)
        await svc.process_event({
            "topic": "sensor.flow",
            "lagoon_id": str(lagoon_id),
            "data": {"inflow_m3_day": 5000.0, "outflow_m3_day": 4800.0},
        })
        await svc.publish_state(lagoon_id)

        bus.publish.assert_called_once()
        publish_kwargs = bus.publish.call_args[1]
        assert "hydrological" in publish_kwargs["topic"]


# ─── Test 6: Scientific Calculation Correctness ───────────────────────────────

class TestScientificCalculationPipeline:
    """Full scientific calculation pipeline integration."""

    def test_gcc_lagoon_water_balance_closure(self) -> None:
        """GCC lagoon water balance must close correctly under typical summer conditions."""
        # Typical Dubai summer: high ET, tidal exchange, TSE inflow
        inflow_m3_day = 18000.0   # TSE + tidal
        outflow_m3_day = 17200.0  # evaporation-dominated
        precip_m_day = 0.0        # no rain in summer
        et_m_day = 0.012          # ~12 mm/day Penman-Monteith
        surface_area_m2 = 120000.0
        gw_flux_m3_day = -850.0   # net seawater intrusion (negative = loss)

        net_storage = water_balance(
            inflow_m3_day=inflow_m3_day,
            outflow_m3_day=outflow_m3_day,
            precipitation_m_day=precip_m_day,
            evapotranspiration_m_day=et_m_day,
            surface_area_m2=surface_area_m2,
            groundwater_flux_m3_day=gw_flux_m3_day,
        )

        # With outflow > inflow and negative GW: net storage should be negative
        # Accounts for ET removing ~1440 m³/day from 120,000 m² surface
        assert isinstance(net_storage, float)
        # Reasonable range for GCC lagoon in summer: net loss of 0–5000 m³/day
        assert -6000 < net_storage < 2000, f"Net storage {net_storage:.1f} m³/day out of range"

    def test_seawater_do_saturation_at_gcc_temperature(self) -> None:
        """DO saturation in GCC seawater at typical summer temperature (32°C, 40 ppt)."""
        sat = do_saturation(temperature_c=32.0, salinity_ppt=40.0)
        # At 32°C and 40 ppt, DO saturation should be approximately 5.5-6.5 mg/L
        assert 5.0 < sat < 7.5, f"DO sat={sat:.2f} mg/L out of expected GCC range"

    def test_gcc_lagoon_tse_trophic_state(self) -> None:
        """GCC lagoon receiving TSE must classify as eutrophic or hypereutrophic."""
        tsi = trophic_state_index(
            chlorophyll_a_ug_l=38.0,   # moderate algal bloom
            total_phosphorus_mg_l=0.28,  # TSE-elevated
        )
        assert tsi in ("eutrophic", "hypereutrophic"), (
            f"GCC TSE lagoon should be eutrophic/hypereutrophic, got {tsi}"
        )

    def test_gcc_summer_et0_range(self) -> None:
        """Penman-Monteith ET0 for Dubai summer must be in physically plausible range."""
        et0 = penman_monteith_et0(
            temperature_c=38.0,       # Dubai July mean
            relative_humidity_pct=55.0,  # typical summer RH
            wind_speed_m_s=4.5,       # moderate Gulf breeze
            solar_radiation_mj_m2_day=28.0,  # peak summer radiation
        )
        # Dubai summer ET0: 8-14 mm/day expected
        assert 7.0 < et0 < 16.0, f"ET0={et0:.2f} mm/day out of Dubai summer range"
