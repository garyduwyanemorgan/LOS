"""Read-only event log access endpoints."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from backend.api.v1.dependencies import (
    CurrentUserDep,
    DatabaseDep,
    PaginationDep,
)
from backend.api.v1.schemas import EventResponse, PaginatedEvents, PaginationMeta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons/{lagoon_id}/events", tags=["Events"])


@router.get("", response_model=PaginatedEvents, summary="List lagoon events")
async def list_events(
    lagoon_id: UUID = Path(...),
    pagination: PaginationDep = ...,
    severity: str | None = Query(default=None, pattern="^(info|warning|critical)$"),
    event_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    db: DatabaseDep = ...,
) -> PaginatedEvents:
    """Return paginated event log for a lagoon, with optional filters."""
    from backend.database.repositories.event_repo import EventRepository  # type: ignore[import]

    repo = EventRepository(db)
    events = await repo.list(
        lagoon_id=lagoon_id,
        skip=pagination.skip,
        limit=pagination.limit,
        severity=severity,
        event_type=event_type,
        since=since,
    )
    return PaginatedEvents(
        items=[EventResponse(**e) for e in events],
        meta=PaginationMeta(skip=pagination.skip, limit=pagination.limit, total=len(events)),
    )


@router.get("/{event_id}", response_model=EventResponse, summary="Get event details")
async def get_event(
    lagoon_id: UUID = Path(...),
    event_id: UUID = Path(...),
    db: DatabaseDep = ...,
) -> EventResponse:
    from backend.database.repositories.event_repo import EventRepository  # type: ignore[import]

    repo = EventRepository(db)
    event = await repo.get(event_id, lagoon_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventResponse(**event)


@router.post("/{event_id}/acknowledge", summary="Acknowledge an event")
async def acknowledge_event(
    lagoon_id: UUID = Path(...),
    event_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
) -> dict:
    from backend.database.repositories.event_repo import EventRepository  # type: ignore[import]

    repo = EventRepository(db)
    event = await repo.get(event_id, lagoon_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.get("acknowledged_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event already acknowledged",
        )

    updated = await repo.acknowledge(
        event_id=event_id,
        acknowledged_by=UUID(str(current_user["id"])),
        acknowledged_at=datetime.now(UTC),
    )
    return {"status": "acknowledged", "event_id": str(event_id), "acknowledged_at": updated.get("acknowledged_at")}
