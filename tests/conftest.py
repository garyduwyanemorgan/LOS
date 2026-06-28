"""Pytest configuration and shared fixtures for LOS test suite."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# ─── Test database ─────────────────────────────────────────────────────────────

TEST_DATABASE_URL = "postgresql+asyncpg://los_test:los_test_password@localhost:5432/los_test"

# Use in-memory SQLite for unit tests that don't need PostGIS
# Use PostgreSQL for integration tests
UNIT_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_lagoon_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def sample_organisation_id() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


# ─── Mocked external services ─────────────────────────────────────────────────

@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Mock EventBus for unit tests."""
    bus = MagicMock()
    bus.publish = AsyncMock(return_value="mock-stream-id")
    bus.connect = AsyncMock()
    bus.disconnect = AsyncMock()
    bus.health = AsyncMock(return_value={"status": "healthy", "connected": True})
    return bus


@pytest.fixture
def mock_shared_memory() -> MagicMock:
    """Mock SharedMemoryService for unit tests."""
    mem = MagicMock()
    mem.store_short_term = AsyncMock()
    mem.get_short_term = AsyncMock(return_value=None)
    mem.store_scientific_memory = AsyncMock()
    mem.get_scientific_memory = AsyncMock(return_value={})
    mem.get_learning_history = AsyncMock(return_value=[])
    mem.store_long_term = AsyncMock()
    mem.get_long_term = AsyncMock(return_value={})
    return mem


@pytest.fixture
def mock_srg() -> MagicMock:
    """Mock ScientificRelationshipGraph for unit tests."""
    srg = MagicMock()
    srg.connect = AsyncMock()
    srg.disconnect = AsyncMock()
    srg.create_relationship = AsyncMock(return_value="mock-relationship-id")
    srg.find_causal_pathways = AsyncMock(return_value=[])
    srg.generate_hypotheses = AsyncMock(return_value=[])
    srg.update_confidence = AsyncMock()
    srg.update_from_intervention_outcome = AsyncMock()
    srg.health = AsyncMock(return_value={"status": "healthy", "connected": True})
    return srg


# ─── Sample domain objects ─────────────────────────────────────────────────────

@pytest.fixture
def sample_lagoon_state(sample_lagoon_id: uuid.UUID) -> dict[str, Any]:
    """A realistic LagoonSystemState snapshot for testing."""
    return {
        "lagoon_id": sample_lagoon_id,
        "overall_confidence": 0.75,
        "active_alerts": ["DO_LOW"],
        "chemical": {
            "do_mg_l": 3.2,
            "do_saturation_pct": 42.0,
            "orp_mv": -45.0,
            "ph": 8.1,
            "temperature_c": 28.5,
            "ec_us_cm": 15200.0,
            "salinity_ppt": 9.8,
            "tn_mg_l": 4.2,
            "tp_mg_l": 0.28,
            "nh4_mg_l": 0.85,
            "no3_mg_l": 0.42,
            "redox_class": "suboxic",
            "internal_loading_risk": "medium",
            "trophic_state": "eutrophic",
            "confidence": 0.82,
            "status": "warning",
        },
        "ecological": {
            "bloom_probability": 0.55,
            "bloom_detected": False,
            "dominant_community": "green_algae",
            "cyanobacteria_risk": "medium",
            "ecological_stability_score": 0.48,
            "recovery_potential": "medium",
            "confidence": 0.70,
            "status": "warning",
        },
        "hydrological": {
            "water_level_m": 1.82,
            "volume_m3": 145000.0,
            "residence_time_days": 18.5,
            "inflow_m3_day": 7800.0,
            "outflow_m3_day": 7600.0,
            "groundwater_flux_m3_day": -120.0,
            "confidence": 0.78,
            "status": "healthy",
        },
        "infrastructure": {
            "aeration_status": "online",
            "pump_status": "online",
            "sensor_coverage_pct": 85.0,
            "maintenance_due": False,
            "active_alerts": 0,
            "confidence": 0.90,
            "status": "healthy",
        },
    }


@pytest.fixture
def sample_observation() -> dict[str, Any]:
    """A sample sensor observation record."""
    return {
        "id": str(uuid.uuid4()),
        "lagoon_id": "12345678-1234-5678-1234-567812345678",
        "sensor_id": str(uuid.uuid4()),
        "parameter": "dissolved_oxygen",
        "value": 3.2,
        "unit": "mg/L",
        "timestamp": "2026-06-26T10:00:00Z",
        "quality_flag": "good",
        "confidence": 0.95,
        "depth_m": 0.5,
        "source": "sensor",
    }
