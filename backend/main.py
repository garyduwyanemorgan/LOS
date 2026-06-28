"""Lagoons Operating System — FastAPI application factory.

Startup sequence:
  1. Configure structured logging
  2. Initialise Sentry (if DSN configured)
  3. Connect to PostgreSQL (verify + PostGIS check)
  4. Connect to Redis event bus
  5. Connect to Neo4j Scientific Relationship Graph
  6. Register all API routers

Shutdown sequence:
  1. Disconnect event bus (cancel consumer tasks)
  2. Disconnect Neo4j driver
  3. Close SQLAlchemy connection pool
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from backend.core.config.settings import settings
from backend.core.exceptions.exceptions import LOSException
from backend.core.logging.logger import configure_logging, get_logger
from backend.database.connection import close_db, init_db
from backend.event_bus.bus import event_bus
from backend.scientific_relationship_graph.service import ScientificRelationshipGraph

log = get_logger(__name__)

# SRG singleton — shared across the application lifetime.
srg = ScientificRelationshipGraph(
    uri=settings.NEO4J_URI,
    username=settings.NEO4J_USERNAME,
    password=settings.NEO4J_PASSWORD,
)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan — startup and shutdown hooks."""

    # ── Startup ──────────────────────────────────────────────────────────────
    log.info("los-startup", environment=settings.ENVIRONMENT, version=settings.APP_VERSION)

    # Database
    log.info("database-initialising")
    await init_db()

    # Event bus
    log.info("event-bus-connecting", redis_url=settings.REDIS_URL)
    await event_bus.connect()

    # Scientific Relationship Graph
    log.info("srg-connecting", neo4j_uri=settings.NEO4J_URI)
    await srg.connect()

    log.info("los-ready", docs_url="/api/docs")

    yield  # Application is now serving requests.

    # ── Shutdown ─────────────────────────────────────────────────────────────
    log.info("los-shutdown")

    await event_bus.disconnect()
    log.info("event-bus-disconnected")

    await srg.disconnect()
    log.info("srg-disconnected")

    await close_db()
    log.info("database-connections-closed")


# ─── Application factory ──────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    This function is the single entry point for creating the app instance.
    It is called once at module load time (app = create_app()) and during
    testing where a fresh app is needed for each test session.
    """

    # Configure logging before the app starts receiving requests.
    configure_logging(
        debug=settings.DEBUG,
        json_format=(settings.LOG_FORMAT == "json"),
    )

    # Initialise Sentry if a DSN is configured.
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                environment=settings.ENVIRONMENT,
                release=f"los@{settings.APP_VERSION}",
                integrations=[FastApiIntegration(), SqlalchemyIntegration()],
                traces_sample_rate=0.1,
                profiles_sample_rate=0.05,
                send_default_pii=False,
            )
            log.info("sentry-initialised")
        except ImportError:
            log.warning("sentry-sdk not installed; error tracking disabled")

    # Build the FastAPI application.
    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Enterprise SaaS Environmental Operating System for lagoon management. "
            "Loop of Loops scientific architecture with real-time decision support."
        ),
        version=settings.APP_VERSION,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
        terms_of_service="https://lagoons-os.com/terms",
        contact={"name": "LOS Support", "email": "support@lagoons-os.com"},
        license_info={"name": "Proprietary"},
    )

    # ── Middleware (order matters — outermost middleware runs first) ───────────

    # CORS — must be first to handle preflight OPTIONS requests.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
        expose_headers=["X-Request-ID", "X-Correlation-ID", "X-Process-Time"],
    )

    # Gzip response compression for large scientific payloads.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Rate limiting — sliding-window counter per user/IP via Redis.
    from backend.api.v1.middleware.rate_limiter import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware)

    # Security headers — applied to every response.
    from backend.api.v1.middleware.security_headers import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)

    # ── Custom middleware ─────────────────────────────────────────────────────

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next: Any) -> Any:
        """Inject request IDs and timing into every request."""
        import uuid

        from backend.core.logging.logger import set_correlation_id, set_request_id

        request_id = str(uuid.uuid4())
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        set_request_id(request_id)
        set_correlation_id(correlation_id)

        start = time.perf_counter()
        response = await call_next(request)
        process_time_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time"] = str(process_time_ms)

        log.info(
            "http-request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=process_time_ms,
            request_id=request_id,
        )
        return response

    # ── Exception handlers ────────────────────────────────────────────────────

    @app.exception_handler(LOSException)
    async def los_exception_handler(request: Request, exc: LOSException) -> JSONResponse:
        """Convert all LOS domain exceptions to consistent JSON error responses."""
        log.warning(
            "los-exception",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.http_status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler for unhandled exceptions."""
        log.error(
            "unhandled-exception",
            path=request.url.path,
            error=str(exc),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal-server-error",
                "message": "An unexpected error occurred. Please try again.",
                "detail": {},
            },
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """Register all API routers.

    Each router module is imported here so that import errors surface
    at startup rather than at the first request to a given endpoint.
    """
    from backend.api.v1 import router as api_v1_router

    app.include_router(api_v1_router, prefix=settings.api_prefix)

    # Health and readiness endpoints (no auth required).
    _add_health_routes(app)


def _add_health_routes(app: FastAPI) -> None:
    """Add /health and /ready endpoints directly to the app (no prefix)."""
    from backend.database.connection import check_db_health

    @app.get("/health", tags=["health"], include_in_schema=False)
    async def health_check() -> dict[str, Any]:
        """Liveness probe — returns 200 if the API process is alive."""
        return {
            "status": "ok",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/ready", tags=["health"], include_in_schema=False)
    async def readiness_check() -> JSONResponse:
        """Readiness probe — checks that all dependencies are available."""
        checks: dict[str, Any] = {}

        # Database
        db_health = await check_db_health()
        checks["database"] = db_health

        # Event bus
        bus_health = await event_bus.health()
        checks["event_bus"] = bus_health

        # Neo4j SRG
        srg_health = await srg.health()
        checks["srg"] = srg_health

        all_healthy = all(
            c.get("connected", False) or c.get("status") == "healthy"
            for c in checks.values()
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "ready" if all_healthy else "degraded",
                "checks": checks,
            },
        )

    @app.get("/metrics", tags=["health"], include_in_schema=False)
    async def prometheus_metrics() -> Any:
        """Expose Prometheus metrics in text format."""
        try:
            from fastapi.responses import Response
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )
        except ImportError:
            return {"error": "prometheus_client not installed"}


# ─── ASGI application ─────────────────────────────────────────────────────────

app = create_app()
