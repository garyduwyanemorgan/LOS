"""Lagoon CRUD, status, objectives, and performance history endpoints."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from backend.api.v1.dependencies import (
    CurrentUserDep,
    DatabaseDep,
    EventBusDep,
    OrgDep,
    PaginationDep,
    SharedMemoryDep,
    require_role,
)
from backend.api.v1.schemas import (
    LagoonCreate,
    LagoonResponse,
    LagoonStatusResponse,
    LagoonUpdate,
    OperatingObjectiveCreate,
    OperatingObjectiveResponse,
    PaginatedLagoons,
    PaginationMeta,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons", tags=["Lagoons"])


def _get_service(db: DatabaseDep, event_bus: EventBusDep, shared_memory: SharedMemoryDep):
    from backend.application.services.lagoon_service import LagoonService
    from backend.database.repositories.lagoon_repo import LagoonRepository  # type: ignore[import]

    repo = LagoonRepository(db)
    return LagoonService(repo, event_bus, shared_memory)


# â”€â”€ List / Create â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("", response_model=PaginatedLagoons, summary="List lagoons for the organisation")
async def list_lagoons(
    org_id: OrgDep,
    pagination: PaginationDep,
    db: DatabaseDep,
    event_bus: EventBusDep,
    shared_memory: SharedMemoryDep,
) -> PaginatedLagoons:
    """Return paginated list of lagoons belonging to the caller's organisation."""
    svc = _get_service(db, event_bus, shared_memory)
    lagoons = await svc.list_lagoons(org_id, skip=pagination.skip, limit=pagination.limit)
    return PaginatedLagoons(
        items=[LagoonResponse(**lg) for lg in lagoons],
        meta=PaginationMeta(skip=pagination.skip, limit=pagination.limit, total=len(lagoons)),
    )


@router.post(
    "",
    response_model=LagoonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new lagoon",
)
async def create_lagoon(
    body: LagoonCreate,
    org_id: OrgDep,
    current_user: CurrentUserDep,
    db: DatabaseDep,
    event_bus: EventBusDep,
    shared_memory: SharedMemoryDep,
    _: dict = Depends(require_role("manager")),
) -> LagoonResponse:
    """Create a new lagoon within the caller's organisation.

    Requires manager role or above.
    """
    svc = _get_service(db, event_bus, shared_memory)
    try:
        created = await svc.create_lagoon(
            data=body.model_dump(exclude_none=True),
            org_id=org_id,
            created_by=UUID(str(current_user["id"])),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return LagoonResponse(**created)


# â”€â”€ Get / Update / Delete â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/{lagoon_id}", response_model=LagoonResponse, summary="Get lagoon details")
async def get_lagoon(
    lagoon_id: UUID = Path(...),
    org_id: OrgDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    shared_memory: SharedMemoryDep = ...,
) -> LagoonResponse:
    svc = _get_service(db, event_bus, shared_memory)
    try:
        lagoon = await svc.get_lagoon(lagoon_id, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lagoon not found") from exc
    return LagoonResponse(**lagoon)


@router.patch("/{lagoon_id}", response_model=LagoonResponse, summary="Update lagoon fields")
async def update_lagoon(
    body: LagoonUpdate,
    lagoon_id: UUID = Path(...),
    org_id: OrgDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    shared_memory: SharedMemoryDep = ...,
    _: dict = Depends(require_role("operator")),
) -> LagoonResponse:
    svc = _get_service(db, event_bus, shared_memory)
    try:
        updated = await svc.update_lagoon(
            lagoon_id=lagoon_id,
            data=body.model_dump(exclude_none=True),
            org_id=org_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return LagoonResponse(**updated)


# â”€â”€ Status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get(
    "/{lagoon_id}/status",
    response_model=LagoonStatusResponse,
    summary="Get live lagoon system state",
)
async def get_lagoon_status(
    lagoon_id: UUID = Path(...),
    org_id: OrgDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    shared_memory: SharedMemoryDep = ...,
) -> LagoonStatusResponse:
    """Return the current composite system state: all loop states, confidence scores,
    recent events, and operating objectives."""
    svc = _get_service(db, event_bus, shared_memory)
    try:
        status_data = await svc.get_lagoon_status(lagoon_id, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lagoon not found") from exc
    return LagoonStatusResponse(**status_data)


# â”€â”€ Operating Objectives â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get(
    "/{lagoon_id}/objectives",
    response_model=list[OperatingObjectiveResponse],
    summary="Get operating objectives",
)
async def get_objectives(
    lagoon_id: UUID = Path(...),
    org_id: OrgDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    shared_memory: SharedMemoryDep = ...,
) -> list[OperatingObjectiveResponse]:
    svc = _get_service(db, event_bus, shared_memory)
    try:
        await svc.get_lagoon(lagoon_id, org_id)  # verify access
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lagoon not found") from exc

    from backend.database.repositories.lagoon_repo import LagoonRepository  # type: ignore[import]

    repo = LagoonRepository(db)
    objectives = await repo.get_objectives(lagoon_id)
    return [OperatingObjectiveResponse(**o) for o in objectives]


@router.put(
    "/{lagoon_id}/objectives",
    response_model=list[OperatingObjectiveResponse],
    summary="Replace operating objectives",
)
async def update_objectives(
    body: list[OperatingObjectiveCreate],
    lagoon_id: UUID = Path(...),
    org_id: OrgDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    shared_memory: SharedMemoryDep = ...,
    _: dict = Depends(require_role("manager")),
) -> list[OperatingObjectiveResponse]:
    """Replace all operating objectives for the lagoon.

    Requires manager role. The entire set is replaced atomically.
    """
    svc = _get_service(db, event_bus, shared_memory)
    try:
        saved = await svc.update_operating_objectives(
            lagoon_id=lagoon_id,
            objectives=[obj.model_dump() for obj in body],
            org_id=org_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return [OperatingObjectiveResponse(**o) for o in saved]


# â”€â”€ Performance History â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get(
    "/{lagoon_id}/performance",
    summary="Get performance history",
)
async def get_performance_history(
    lagoon_id: UUID = Path(...),
    org_id: OrgDep = ...,
    days: int = Query(default=30, ge=1, le=365),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    shared_memory: SharedMemoryDep = ...,
) -> dict:
    svc = _get_service(db, event_bus, shared_memory)
    try:
        history = await svc.get_performance_history(lagoon_id, days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lagoon not found") from exc
    return history

