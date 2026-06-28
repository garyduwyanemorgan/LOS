"""API tests for health and readiness endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import create_app


@pytest.fixture
def app():
    """Create test FastAPI app with mocked dependencies."""
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

        yield create_app()


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(app) -> None:
    """GET /health must return 200 with service info."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_returns_503_when_db_unhealthy(app) -> None:
    """GET /ready must return 503 when database is unhealthy."""
    with patch(
        "backend.database.connection.check_db_health",
        new_callable=AsyncMock,
        return_value={"connected": False, "status": "unhealthy"},
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
