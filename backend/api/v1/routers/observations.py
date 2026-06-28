"""Observation ingestion and time-series retrieval endpoints."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from backend.api.v1.schemas import (
    BulkIngestResponse,
    BulkObservationCreate,
    LatestReadingsResponse,
    ObservationCreate,
    ObservationResponse,
    StatisticsResponse,
    TimeSeriesResponse,
)

if TYPE_CHECKING:
    from backend.api.v1.dependencies import (
        CurrentUserDep,
        DatabaseDep,
        EventBusDep,
    )

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons/{lagoon_id}/observations", tags=["Observations"])


def _get_service(db: DatabaseDep, event_bus: EventBusDep):
    from backend.application.services.observation_service import ObservationService
    from backend.database.repositories.observation_repo import (
        ObservationRepository,  # type: ignore[import]
    )

    repo = ObservationRepository(db)
    return ObservationService(repo, event_bus)


@router.post(
    "",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single observation",
)
async def ingest_observation(
    body: ObservationCreate,
    lagoon_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
) -> ObservationResponse:
    """Validate and store a single sensor/manual observation.

    Publishes an ObservationIngested event to trigger downstream processing.
    """
    svc = _get_service(db, event_bus)
    try:
        created = await svc.ingest_observation(
            data=body.model_dump(),
            lagoon_id=lagoon_id,
            user_id=UUID(str(current_user["id"])),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ObservationResponse(**created)


@router.post(
    "/bulk",
    response_model=BulkIngestResponse,
    status_code=status.HTTP_207_MULTI_STATUS,
    summary="Bulk ingest observations",
)
async def bulk_ingest(
    body: BulkObservationCreate,
    lagoon_id: UUID = Path(...),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
) -> BulkIngestResponse:
    """Batch-insert up to 10,000 observations in a single request.

    Returns accepted/rejected counts. Invalid rows are skipped and detailed
    in the response.
    """
    svc = _get_service(db, event_bus)
    result = await svc.bulk_ingest(
        observations=[o.model_dump() for o in body.observations],
        lagoon_id=lagoon_id,
    )
    return BulkIngestResponse(**result)


@router.get(
    "/latest",
    response_model=LatestReadingsResponse,
    summary="Get latest sensor readings",
)
async def get_latest_readings(
    lagoon_id: UUID = Path(...),
    parameters: list[str] | None = Query(default=None),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
) -> LatestReadingsResponse:
    """Return the most recent value for each parameter (or for a specified subset)."""
    svc = _get_service(db, event_bus)
    try:
        result = await svc.get_latest_readings(lagoon_id, parameters)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return LatestReadingsResponse(**result)


@router.get(
    "/timeseries/{parameter}",
    response_model=TimeSeriesResponse,
    summary="Get parameter time series",
)
async def get_time_series(
    lagoon_id: UUID = Path(...),
    parameter: str = Path(...),
    start: datetime = Query(default_factory=lambda: datetime.now(UTC) - timedelta(days=7)),
    end: datetime = Query(default_factory=lambda: datetime.now(UTC)),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
) -> TimeSeriesResponse:
    """Return ordered time series for a single parameter between start and end."""
    svc = _get_service(db, event_bus)
    try:
        data = await svc.get_time_series(lagoon_id, parameter, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return TimeSeriesResponse(
        lagoon_id=lagoon_id,
        parameter=parameter,
        start=start,
        end=end,
        count=len(data),
        data=data,
    )


@router.get(
    "/statistics/{parameter}",
    response_model=StatisticsResponse,
    summary="Get parameter statistics",
)
async def get_statistics(
    lagoon_id: UUID = Path(...),
    parameter: str = Path(...),
    days: int = Query(default=30, ge=1, le=365),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
) -> StatisticsResponse:
    """Return descriptive statistics (mean, std, percentiles) for a parameter."""
    svc = _get_service(db, event_bus)
    try:
        result = await svc.get_statistics(lagoon_id, parameter, days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return StatisticsResponse(**result)
