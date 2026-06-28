"""Simulation trigger and monitoring endpoints."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, status

from backend.api.v1.dependencies import (
    CurrentUserDep,
    DatabaseDep,
    EventBusDep,
    PaginationDep,
    require_role,
)
from backend.api.v1.schemas import (
    PaginatedSimulations,
    PaginationMeta,
    SimulationRequest,
    SimulationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons/{lagoon_id}/simulations", tags=["Simulations"])


@router.get("", response_model=PaginatedSimulations, summary="List simulations")
async def list_simulations(
    lagoon_id: UUID = Path(...),
    pagination: PaginationDep = ...,
    db: DatabaseDep = ...,
) -> PaginatedSimulations:
    from backend.database.repositories.simulation_repo import (
        SimulationRepository,  # type: ignore[import]
    )

    repo = SimulationRepository(db)
    items = await repo.list(lagoon_id, skip=pagination.skip, limit=pagination.limit)
    return PaginatedSimulations(
        items=[SimulationResponse(**i) for i in items],
        meta=PaginationMeta(skip=pagination.skip, limit=pagination.limit, total=len(items)),
    )


@router.post(
    "",
    response_model=SimulationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a simulation run",
)
async def trigger_simulation(
    body: SimulationRequest,
    lagoon_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("scientist")),
) -> SimulationResponse:
    """Submit a simulation job to the background worker queue.

    Returns immediately with status 'queued'. Poll the returned ID for status.
    """
    from backend.database.repositories.simulation_repo import (
        SimulationRepository,  # type: ignore[import]
    )
    from backend.workers.tasks.simulation_tasks import run_simulation_task  # type: ignore[import]

    sim_id = uuid4()
    record = {
        "id": str(sim_id),
        "lagoon_id": str(lagoon_id),
        "simulation_type": body.simulation_type,
        "status": "queued",
        "scenario_name": body.scenario_name,
        "description": body.description,
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "parameters": body.parameters,
        "submitted_by": str(current_user["id"]),
        "submitted_at": datetime.now(UTC).isoformat(),
    }

    repo = SimulationRepository(db)
    created = await repo.create(record)

    # Dispatch to Celery
    try:
        task = run_simulation_task.apply_async(
            args=[str(sim_id), str(lagoon_id), body.simulation_type, body.parameters],
            task_id=str(sim_id),
            queue="simulations",
        )
        await repo.update(sim_id, {"task_id": task.id})
        created["task_id"] = task.id
    except Exception as exc:
        logger.error("Failed to dispatch simulation task: %s", exc)
        await repo.update(sim_id, {"status": "failed", "error_message": str(exc)})
        created["status"] = "failed"
        created["error_message"] = str(exc)

    logger.info(
        "Simulation queued: id=%s lagoon=%s type=%s",
        sim_id,
        lagoon_id,
        body.simulation_type,
    )
    return SimulationResponse(**created)


@router.get("/{simulation_id}", response_model=SimulationResponse, summary="Get simulation status")
async def get_simulation(
    lagoon_id: UUID = Path(...),
    simulation_id: UUID = Path(...),
    db: DatabaseDep = ...,
) -> SimulationResponse:
    from backend.database.repositories.simulation_repo import (
        SimulationRepository,  # type: ignore[import]
    )

    repo = SimulationRepository(db)
    item = await repo.get(simulation_id, lagoon_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found")
    return SimulationResponse(**item)


@router.post(
    "/{simulation_id}/cancel",
    summary="Cancel a queued or running simulation",
)
async def cancel_simulation(
    lagoon_id: UUID = Path(...),
    simulation_id: UUID = Path(...),
    db: DatabaseDep = ...,
    _: dict = Depends(require_role("scientist")),
) -> dict:
    from backend.database.repositories.simulation_repo import (
        SimulationRepository,  # type: ignore[import]
    )

    repo = SimulationRepository(db)
    item = await repo.get(simulation_id, lagoon_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found")
    if item.get("status") not in ("queued", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel simulation with status '{item.get('status')}'",
        )

    # Revoke Celery task if available
    task_id = item.get("task_id")
    if task_id:
        try:
            from backend.workers.celery_app import app as celery_app

            celery_app.control.revoke(task_id, terminate=True)
        except Exception as exc:
            logger.warning("Failed to revoke Celery task %s: %s", task_id, exc)

    await repo.update(simulation_id, {"status": "cancelled"})
    return {"simulation_id": str(simulation_id), "status": "cancelled"}
