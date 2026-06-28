"""Health check endpoints — liveness, readiness, detailed system status."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.v1.dependencies import (
    DatabaseDep,
    require_role,
)
from backend.api.v1.schemas import LoopStatusResponse, SystemHealthResponse
from backend.core.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

_start_time = time.monotonic()


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Simple liveness check — returns 200 if the process is running."""
    return {
        "status": "ok",
        "service": "LOS",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get(
    "/health/ready",
    summary="Readiness probe",
    responses={503: {"description": "One or more critical services unavailable"}},
)
async def readiness(db: DatabaseDep) -> dict:
    """Readiness probe — checks DB, Redis, and Neo4j connectivity.

    Returns 503 if any critical service is unavailable.
    """
    checks: dict[str, str] = {}
    failures: list[str] = []

    # Database
    try:
        await db.execute(__import__("sqlalchemy", fromlist=["text"]).text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        failures.append("database")

    # Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=3.0)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        failures.append("redis")

    # Neo4j
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
        )
        await driver.verify_connectivity()
        await driver.close()
        checks["neo4j"] = "ok"
    except Exception as exc:
        checks["neo4j"] = f"error: {exc}"
        failures.append("neo4j")

    if failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Service degraded", "failures": failures, "checks": checks},
        )

    return {
        "status": "ready",
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get(
    "/health/detailed",
    response_model=SystemHealthResponse,
    summary="Full system health status (admin only)",
)
async def detailed_health(
    db: DatabaseDep,
    _: dict = Depends(require_role("admin")),
) -> SystemHealthResponse:
    """Detailed system status including loop health, queue depth, and worker info.

    Requires admin role.
    """
    db_status = "ok"
    redis_status = "ok"
    neo4j_status = "ok"
    queue_depth: int | None = None
    loop_statuses: list[LoopStatusResponse] = []

    # DB ping
    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    # Redis ping + queue depth
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=3.0)
        await r.ping()
        queue_depth = await r.llen("celery")
        await r.aclose()
    except Exception as exc:
        redis_status = f"error: {exc}"

    # Neo4j ping
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
        )
        await driver.verify_connectivity()
        await driver.close()
    except Exception as exc:
        neo4j_status = f"error: {exc}"

    # Loop statuses — read from shared memory if available
    try:
        import json

        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=3.0)
        loop_keys = await r.keys("los:loop:health:*")
        for key in loop_keys[:20]:
            raw = await r.get(key)
            if raw:
                data = json.loads(raw)
                loop_statuses.append(
                    LoopStatusResponse(
                        loop_name=data.get("loop", key.decode().split(":")[-1]),
                        service_name=data.get("service", "unknown"),
                        status=data.get("status", "unknown"),
                        last_run=data.get("last_run"),
                        run_count=data.get("run_count", 0),
                        error_count=data.get("error_count", 0),
                        confidence=data.get("confidence"),
                    )
                )
        await r.aclose()
    except Exception as exc:
        logger.debug("Could not fetch loop statuses: %s", exc)

    uptime = time.monotonic() - _start_time

    overall = "ok"
    if "error" in db_status:
        overall = "degraded"

    return SystemHealthResponse(
        status=overall,
        version=settings.APP_VERSION,
        timestamp=datetime.now(UTC),
        database=db_status,
        redis=redis_status,
        neo4j=neo4j_status,
        worker_queue_depth=queue_depth,
        active_loops=len(loop_statuses),
        loop_statuses=loop_statuses,
        uptime_seconds=round(uptime, 1),
    )
