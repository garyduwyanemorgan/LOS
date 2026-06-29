"""Intervention CRUD and outcome recording endpoints."""
from __future__ import annotations

import logging
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status

from backend.api.v1.dependencies import (
    CurrentUserDep,
    DatabaseDep,
    EventBusDep,
    PaginationDep,
    require_role,
)
from backend.api.v1.schemas import (
    InterventionCreate,
    InterventionResponse,
    InterventionUpdate,
    PaginatedInterventions,
    PaginationMeta,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons/{lagoon_id}/interventions", tags=["Interventions"])


@router.get("", response_model=PaginatedInterventions, summary="List interventions")
async def list_interventions(
    lagoon_id: UUID = Path(...),
    pagination: PaginationDep = ...,
    db: DatabaseDep = ...,
) -> PaginatedInterventions:
    from backend.database.repositories.intervention_repo import (
        InterventionRepository,  # type: ignore[import]
    )

    repo = InterventionRepository(db)
    items = await repo.list(lagoon_id, skip=pagination.skip, limit=pagination.limit)
    return PaginatedInterventions(
        items=[InterventionResponse(**i) for i in items],
        meta=PaginationMeta(skip=pagination.skip, limit=pagination.limit, total=len(items)),
    )


@router.post(
    "",
    response_model=InterventionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log an intervention",
)
async def create_intervention(
    body: InterventionCreate,
    lagoon_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("operator")),
) -> InterventionResponse:
    """Record a planned or completed intervention for the lagoon."""
    from datetime import datetime

    from backend.database.repositories.intervention_repo import (
        InterventionRepository,  # type: ignore[import]
    )

    repo = InterventionRepository(db)
    record = {
        **body.model_dump(exclude_none=True),
        "lagoon_id": str(lagoon_id),
        "created_by": str(current_user["id"]),
        "status": "planned",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    created = await repo.create(record)

    await event_bus.publish(
        "intervention.logged",
        {
            "intervention_id": created.get("id"),
            "lagoon_id": str(lagoon_id),
            "type": body.intervention_type,
        },
    )

    return InterventionResponse(**created)


@router.get("/{intervention_id}", response_model=InterventionResponse, summary="Get intervention")
async def get_intervention(
    lagoon_id: UUID = Path(...),
    intervention_id: UUID = Path(...),
    db: DatabaseDep = ...,
) -> InterventionResponse:
    from backend.database.repositories.intervention_repo import (
        InterventionRepository,  # type: ignore[import]
    )

    repo = InterventionRepository(db)
    item = await repo.get(intervention_id, lagoon_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intervention not found")
    return InterventionResponse(**item)


@router.patch("/{intervention_id}", response_model=InterventionResponse, summary="Update intervention")
async def update_intervention(
    body: InterventionUpdate,
    lagoon_id: UUID = Path(...),
    intervention_id: UUID = Path(...),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("operator")),
) -> InterventionResponse:
    from datetime import datetime

    from backend.database.repositories.intervention_repo import (
        InterventionRepository,  # type: ignore[import]
    )

    repo = InterventionRepository(db)
    data = body.model_dump(exclude_none=True)
    data["updated_at"] = datetime.now(UTC).isoformat()
    updated = await repo.update(intervention_id, lagoon_id, data)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intervention not found")

    if body.status == "completed":
        await event_bus.publish(
            "intervention.completed",
            {
                "intervention_id": str(intervention_id),
                "lagoon_id": str(lagoon_id),
                "effectiveness_score": body.effectiveness_score,
            },
        )

    return InterventionResponse(**updated)


@router.post(
    "/{intervention_id}/outcome",
    response_model=InterventionResponse,
    summary="Record intervention outcome",
)
async def record_outcome(
    outcome_description: str,
    effectiveness_score: float,
    lagoon_id: UUID = Path(...),
    intervention_id: UUID = Path(...),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("operator")),
) -> InterventionResponse:
    """Record the observed outcome of a completed intervention."""
    from datetime import datetime

    from backend.database.repositories.intervention_repo import (
        InterventionRepository,  # type: ignore[import]
    )

    if not 0.0 <= effectiveness_score <= 1.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="effectiveness_score must be between 0.0 and 1.0",
        )

    repo = InterventionRepository(db)
    updated = await repo.update(
        intervention_id,
        lagoon_id,
        {
            "status": "completed",
            "outcome_description": outcome_description,
            "effectiveness_score": effectiveness_score,
            "executed_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intervention not found")
    return InterventionResponse(**updated)
