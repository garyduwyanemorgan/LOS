"""Performance tests — verify that all core operations complete within time budgets.

All time budgets are conservative for CI (running without GPU/dedicated hardware).
Scientific calculations must be fast since they run in tight event loops.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Callable

import pytest


# ─── Budget constants (milliseconds) ─────────────────────────────────────────

_BUDGET_SCIENTIFIC_CALCULATION_MS = 50.0   # individual calculation
_BUDGET_DECISION_CYCLE_MS = 500.0          # full decision engine cycle
_BUDGET_BAYESIAN_UPDATE_MS = 10.0          # single Bayesian update
_BUDGET_BATCH_BAYESIAN_MS = 200.0          # 1000 sequential updates
_BUDGET_WATER_BALANCE_BATCH_MS = 100.0     # 10,000 water balance calls
_BUDGET_TROPHIC_CLASSIFICATION_BATCH_MS = 50.0  # 1000 trophic classifications


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _elapsed_ms(fn: Callable, *args, **kwargs) -> float:
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0


async def _async_elapsed_ms(coro) -> float:
    t0 = time.perf_counter()
    await coro
    return (time.perf_counter() - t0) * 1000.0


# ─── Scientific Calculation Latency ──────────────────────────────────────────

class TestScientificCalculationLatency:
    """All scientific calculations must be fast enough for real-time loops."""

    def test_do_saturation_latency(self) -> None:
        """DO saturation calculation must complete well under budget."""
        from backend.scientific_services.chemical.calculations import do_saturation

        elapsed = _elapsed_ms(do_saturation, temperature_c=28.0, salinity_ppt=35.0)
        assert elapsed < _BUDGET_SCIENTIFIC_CALCULATION_MS, (
            f"do_saturation took {elapsed:.2f}ms — budget {_BUDGET_SCIENTIFIC_CALCULATION_MS}ms"
        )

    def test_trophic_state_index_latency(self) -> None:
        """Trophic state classification must complete under budget."""
        from backend.scientific_services.chemical.calculations import trophic_state_index

        elapsed = _elapsed_ms(
            trophic_state_index,
            chlorophyll_a_ug_l=45.0,
            total_phosphorus_mg_l=0.35,
        )
        assert elapsed < _BUDGET_SCIENTIFIC_CALCULATION_MS, (
            f"trophic_state_index took {elapsed:.2f}ms"
        )

    def test_water_balance_latency(self) -> None:
        """Water balance calculation must complete under budget."""
        from backend.scientific_services.hydrological.calculations import water_balance

        elapsed = _elapsed_ms(
            water_balance,
            inflow_m3_day=8500.0,
            outflow_m3_day=8100.0,
            precipitation_m_day=0.0,
            evapotranspiration_m_day=0.010,
            surface_area_m2=50000.0,
            groundwater_flux_m3_day=-500.0,
        )
        assert elapsed < _BUDGET_SCIENTIFIC_CALCULATION_MS, (
            f"water_balance took {elapsed:.2f}ms"
        )

    def test_penman_monteith_et0_latency(self) -> None:
        """ET0 calculation must complete under budget."""
        from backend.scientific_services.hydrological.calculations import penman_monteith_et0

        elapsed = _elapsed_ms(
            penman_monteith_et0,
            temperature_c=35.0,
            relative_humidity_pct=50.0,
            wind_speed_m_s=4.0,
            solar_radiation_mj_m2_day=25.0,
        )
        assert elapsed < _BUDGET_SCIENTIFIC_CALCULATION_MS, (
            f"penman_monteith_et0 took {elapsed:.2f}ms"
        )

    def test_residence_time_latency(self) -> None:
        """Residence time must compute instantly."""
        from backend.scientific_services.hydrological.calculations import residence_time

        elapsed = _elapsed_ms(residence_time, volume_m3=100000.0, outflow_m3_day=8000.0)
        assert elapsed < _BUDGET_SCIENTIFIC_CALCULATION_MS

    def test_classify_redox_latency(self) -> None:
        """Redox classification must be instantaneous."""
        from backend.scientific_services.chemical.calculations import classify_redox

        elapsed = _elapsed_ms(classify_redox, orp_mv=-120.0)
        assert elapsed < _BUDGET_SCIENTIFIC_CALCULATION_MS


class TestBatchThroughputLatency:
    """Batch throughput tests — simulate high-frequency sensor processing."""

    def test_10k_water_balance_calls(self) -> None:
        """10,000 sequential water balance calls must complete within budget."""
        from backend.scientific_services.hydrological.calculations import water_balance

        t0 = time.perf_counter()
        for _ in range(10_000):
            water_balance(
                inflow_m3_day=8500.0,
                outflow_m3_day=8100.0,
                precipitation_m_day=0.001,
                evapotranspiration_m_day=0.010,
                surface_area_m2=50000.0,
            )
        elapsed = (time.perf_counter() - t0) * 1000.0

        assert elapsed < _BUDGET_WATER_BALANCE_BATCH_MS, (
            f"10,000 water_balance calls took {elapsed:.1f}ms "
            f"(budget {_BUDGET_WATER_BALANCE_BATCH_MS}ms)"
        )

    def test_1k_trophic_classifications(self) -> None:
        """1,000 trophic state classifications must complete within budget."""
        from backend.scientific_services.chemical.calculations import trophic_state_index

        t0 = time.perf_counter()
        for i in range(1_000):
            trophic_state_index(
                chlorophyll_a_ug_l=float(5 + i % 50),
                total_phosphorus_mg_l=0.01 * (1 + i % 30),
            )
        elapsed = (time.perf_counter() - t0) * 1000.0

        assert elapsed < _BUDGET_TROPHIC_CLASSIFICATION_BATCH_MS, (
            f"1,000 trophic classifications took {elapsed:.1f}ms "
            f"(budget {_BUDGET_TROPHIC_CLASSIFICATION_BATCH_MS}ms)"
        )


# ─── Bayesian Updater Latency ─────────────────────────────────────────────────

class TestBayesianUpdaterLatency:
    """Bayesian confidence updates must be fast for high-throughput learning."""

    def test_single_update_latency(self) -> None:
        """Single Bayesian update must be faster than budget."""
        from backend.scientific_models.statistical.bayesian_updater import bayesian_update_confidence

        elapsed = _elapsed_ms(
            bayesian_update_confidence,
            prior=0.65,
            observed_success=True,
        )
        assert elapsed < _BUDGET_BAYESIAN_UPDATE_MS, (
            f"Single Bayesian update took {elapsed:.2f}ms (budget {_BUDGET_BAYESIAN_UPDATE_MS}ms)"
        )

    def test_1000_sequential_updates_latency(self) -> None:
        """1,000 sequential updates simulate a busy learning cycle."""
        from backend.scientific_models.statistical.bayesian_updater import bayesian_update_confidence

        t0 = time.perf_counter()
        confidence = 0.5
        for i in range(1_000):
            result = bayesian_update_confidence(
                prior=confidence,
                observed_success=(i % 3 != 0),
            )
            confidence = result.posterior
        elapsed = (time.perf_counter() - t0) * 1000.0

        assert elapsed < _BUDGET_BATCH_BAYESIAN_MS, (
            f"1,000 Bayesian updates took {elapsed:.1f}ms (budget {_BUDGET_BATCH_BAYESIAN_MS}ms)"
        )


# ─── Decision Engine Latency ──────────────────────────────────────────────────

class TestDecisionEngineLatency:
    """Full decision engine cycle must complete within time budget."""

    @pytest.mark.asyncio
    async def test_decision_cycle_latency(self) -> None:
        """A full decision cycle must complete under budget."""
        from backend.decision_engine.engine import DecisionEngine
        from backend.decision_engine.models import (
            LagoonSystemState,
            LoopStateSnapshot,
        )

        engine = DecisionEngine(shared_memory=None, srg=None)
        lagoon_id = uuid.uuid4()

        state = LagoonSystemState(lagoon_id=lagoon_id)
        state.overall_confidence = 0.75
        state.active_alerts = ["NUTRIENT_LOADING_ELEVATED"]
        state.chemical = LoopStateSnapshot(
            loop="chemical",
            confidence=0.78,
            status="warning",
            state={
                "do_mg_l": 5.5,
                "orp_mv": 80.0,
                "redox_class": "suboxic",
                "internal_loading_risk": "medium",
            },
        )
        state.ecological = LoopStateSnapshot(
            loop="ecological",
            confidence=0.65,
            status="warning",
            state={
                "bloom_probability": 0.45,
                "cyanobacteria_risk": "medium",
                "ecological_stability_score": 0.55,
                "recovery_potential": "medium",
            },
        )

        elapsed = await _async_elapsed_ms(
            engine.run_decision_cycle(
                lagoon_id=lagoon_id,
                injected_state=state,
            )
        )

        assert elapsed < _BUDGET_DECISION_CYCLE_MS, (
            f"Decision cycle took {elapsed:.1f}ms (budget {_BUDGET_DECISION_CYCLE_MS}ms)"
        )

    @pytest.mark.asyncio
    async def test_decision_cycle_repeated_10_times(self) -> None:
        """Ten consecutive cycles must all complete — no accumulating latency."""
        from backend.decision_engine.engine import DecisionEngine
        from backend.decision_engine.models import LagoonSystemState

        engine = DecisionEngine(shared_memory=None, srg=None)
        lagoon_id = uuid.uuid4()
        state = LagoonSystemState(lagoon_id=lagoon_id)
        state.overall_confidence = 0.70

        t0 = time.perf_counter()
        for _ in range(10):
            await engine.run_decision_cycle(lagoon_id=lagoon_id, injected_state=state)
        elapsed = (time.perf_counter() - t0) * 1000.0

        # 10 cycles × 500ms budget = 5000ms, but expect much faster
        assert elapsed < 5000.0, f"10 decision cycles took {elapsed:.1f}ms — budget 5000ms"


# ─── API Health Check Latency ─────────────────────────────────────────────────

class TestAPIHealthLatency:
    """Health endpoints must respond immediately."""

    @pytest.mark.asyncio
    async def test_health_endpoint_latency(self) -> None:
        """GET /health must respond in under 100ms (liveness probe)."""
        import os

        os.environ.setdefault("SECRET_KEY", "perf-test-secret-key-32-chars-long!")
        os.environ.setdefault("JWT_SECRET_KEY", "perf-test-jwt-key-32-chars-long!")
        os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
        os.environ.setdefault("NEO4J_PASSWORD", "test")
        os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
        os.environ.setdefault("SUPABASE_ANON_KEY", "test")
        os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
        os.environ.setdefault("SUPABASE_JWT_SECRET", "test")
        os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")

        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from backend.main import create_app

        with (
            patch("backend.main.init_db", new_callable=AsyncMock),
            patch("backend.main.close_db", new_callable=AsyncMock),
            patch("backend.main.event_bus") as mock_bus,
            patch("backend.main.srg") as mock_srg,
        ):
            mock_bus.connect = AsyncMock()
            mock_bus.disconnect = AsyncMock()
            mock_bus.health = AsyncMock(return_value={"status": "healthy", "connected": True})
            mock_srg.connect = AsyncMock()
            mock_srg.disconnect = AsyncMock()
            mock_srg.health = AsyncMock(return_value={"status": "healthy", "connected": True})

            app = create_app()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                t0 = time.perf_counter()
                response = await client.get("/health")
                elapsed = (time.perf_counter() - t0) * 1000.0

        assert response.status_code == 200
        assert elapsed < 100.0, f"/health took {elapsed:.1f}ms — must be under 100ms"
