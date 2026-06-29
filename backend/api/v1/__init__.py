"""API v1 — aggregates all versioned routers into a single APIRouter."""

from fastapi import APIRouter

from backend.api.v1.routers.admin import router as admin_router
from backend.api.v1.routers.auth import router as auth_router
from backend.api.v1.routers.events import router as events_router
from backend.api.v1.routers.health import router as health_router
from backend.api.v1.routers.interventions import router as interventions_router
from backend.api.v1.routers.lagoons import router as lagoons_router
from backend.api.v1.routers.observations import router as observations_router
from backend.api.v1.routers.recommendations import router as recommendations_router
from backend.api.v1.routers.reports import router as reports_router
from backend.api.v1.routers.sensors import router as sensors_router
from backend.api.v1.routers.simulations import router as simulations_router
from backend.api.v1.routers.users import router as users_router
from backend.api.v1.websocket import router as websocket_router

router = APIRouter()

# Each sub-router defines its own prefix via APIRouter(prefix=...).
# Do NOT pass prefix= here — it would double the prefix and cause 404s.
router.include_router(auth_router)
router.include_router(lagoons_router)
router.include_router(observations_router)
router.include_router(sensors_router)
router.include_router(events_router)
router.include_router(recommendations_router)
router.include_router(interventions_router)
router.include_router(simulations_router)
router.include_router(reports_router)
router.include_router(users_router)
router.include_router(admin_router)
router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(websocket_router, prefix="/ws", tags=["WebSocket"])
