"""Admin endpoints — system health, loop management, worker status."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.v1.dependencies import require_role
from backend.api.v1.schemas import LoopStatusResponse, WorkerStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/loops",
    response_model=list[LoopStatusResponse],
    summary="List scientific loop statuses",
)
async def list_loop_statuses(
    _: dict = Depends(require_role("admin")),
) -> list[LoopStatusResponse]:
    """Return health status of all registered scientific service loops."""
    import json

    import redis.asyncio as aioredis

    from backend.core.config.settings import settings

    results: list[LoopStatusResponse] = []
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=3.0)
        keys = await r.keys("los:loop:health:*")
        for key in keys:
            raw = await r.get(key)
            if raw:
                data = json.loads(raw)
                results.append(
                    LoopStatusResponse(
                        loop_name=data.get("loop", "unknown"),
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
        logger.error("Failed to read loop statuses from Redis: %s", exc)

    return results


@router.get(
    "/workers",
    response_model=list[WorkerStatusResponse],
    summary="List Celery worker statuses",
)
async def list_workers(
    _: dict = Depends(require_role("admin")),
) -> list[WorkerStatusResponse]:
    """Return status of all active Celery workers."""
    try:
        from backend.workers.celery_app import app as celery_app

        inspect = celery_app.control.inspect(timeout=5.0)
        active = inspect.active() or {}
        stats = inspect.stats() or {}

        workers = []
        for worker_id, tasks in active.items():
            worker_stats = stats.get(worker_id, {})
            workers.append(
                WorkerStatusResponse(
                    worker_id=worker_id,
                    hostname=worker_stats.get("hostname", worker_id),
                    status="online",
                    active_tasks=tasks or [],
                    queue=worker_stats.get("total", {}).get("queue", "default"),
                    heartbeat_at=datetime.now(UTC),
                )
            )
        return workers
    except Exception as exc:
        logger.error("Failed to inspect Celery workers: %s", exc)
        return []


@router.post(
    "/loops/{loop_name}/restart",
    summary="Restart a specific scientific loop",
)
async def restart_loop(
    loop_name: str,
    _: dict = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Publish a loop restart command to the event bus.

    The loop service will pick this up and reinitialise.
    """
    import json

    import redis.asyncio as aioredis

    from backend.core.config.settings import settings

    valid_loops = {"hydrological", "chemical", "ecological", "infrastructure", "decision_engine"}
    if loop_name not in valid_loops:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown loop '{loop_name}'. Valid: {sorted(valid_loops)}",
        )

    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.publish(
            "los:commands",
            json.dumps(
                {
                    "command": "restart_loop",
                    "loop": loop_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ),
        )
        await r.aclose()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to publish restart command: {exc}",
        ) from exc

    return {
        "status": "restart_commanded",
        "loop": loop_name,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/queue/depth", summary="Get Celery queue depths")
async def queue_depths(
    _: dict = Depends(require_role("admin")),
) -> dict[str, int]:
    """Return the number of messages in each Celery task queue."""
    import redis.asyncio as aioredis

    from backend.core.config.settings import settings

    queues = ["default", "scientific", "simulations", "notifications", "reporting"]
    depths: dict[str, int] = {}
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=3.0)
        for q in queues:
            depths[q] = await r.llen(q)
        await r.aclose()
    except Exception as exc:
        logger.error("Failed to read queue depths: %s", exc)
        depths = dict.fromkeys(queues, -1)

    return depths
