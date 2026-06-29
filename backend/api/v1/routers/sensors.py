"""Sensor CRUD and calibration management endpoints."""
from __future__ import annotations

import logging
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
    PaginatedSensors,
    PaginationMeta,
    SensorCalibrationCreate,
    SensorCreate,
    SensorResponse,
    SensorUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons/{lagoon_id}/sensors", tags=["Sensors"])


@router.get("", response_model=PaginatedSensors, summary="List sensors for a lagoon")
async def list_sensors(
    lagoon_id: UUID = Path(...),
    pagination: PaginationDep = ...,
    db: DatabaseDep = ...,
) -> PaginatedSensors:
    from backend.database.repositories.sensor_repo import SensorRepository  # type: ignore[import]

    repo = SensorRepository(db)
    sensors = await repo.list(lagoon_id, skip=pagination.skip, limit=pagination.limit)
    return PaginatedSensors(
        items=[SensorResponse(**s) for s in sensors],
        meta=PaginationMeta(skip=pagination.skip, limit=pagination.limit, total=len(sensors)),
    )


@router.post(
    "",
    response_model=SensorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new sensor",
)
async def create_sensor(
    body: SensorCreate,
    lagoon_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("operator")),
) -> SensorResponse:
    from backend.database.repositories.sensor_repo import SensorRepository  # type: ignore[import]

    repo = SensorRepository(db)
    data = body.model_dump(exclude_none=True)
    # Fields not present on the Sensor ORM model go into extra_metadata
    META_KEYS = {"parameter", "accuracy", "detection_limit", "sampling_interval_s",
                 "location_description", "latitude", "longitude"}
    meta = {k: data.pop(k) for k in list(data) if k in META_KEYS}
    record = {
        **data,
        "lagoon_id": str(lagoon_id),
        "is_active": True,
        "metadata": meta,
    }
    created = await repo.create(record)
    # Merge metadata back so SensorResponse fields are populated
    created.update(created.pop("metadata", {}) or {})
    return SensorResponse(**created)


@router.get("/{sensor_id}", response_model=SensorResponse, summary="Get sensor details")
async def get_sensor(
    lagoon_id: UUID = Path(...),
    sensor_id: UUID = Path(...),
    db: DatabaseDep = ...,
) -> SensorResponse:
    from backend.database.repositories.sensor_repo import SensorRepository  # type: ignore[import]

    repo = SensorRepository(db)
    sensor = await repo.get(sensor_id, lagoon_id)
    if sensor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")
    return SensorResponse(**sensor)


@router.patch("/{sensor_id}", response_model=SensorResponse, summary="Update sensor")
async def update_sensor(
    body: SensorUpdate,
    lagoon_id: UUID = Path(...),
    sensor_id: UUID = Path(...),
    db: DatabaseDep = ...,
    _: dict = Depends(require_role("operator")),
) -> SensorResponse:
    from backend.database.repositories.sensor_repo import SensorRepository  # type: ignore[import]

    repo = SensorRepository(db)
    updated = await repo.update(sensor_id, lagoon_id, body.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")
    return SensorResponse(**updated)


@router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Deactivate sensor")
async def delete_sensor(
    lagoon_id: UUID = Path(...),
    sensor_id: UUID = Path(...),
    db: DatabaseDep = ...,
    _: dict = Depends(require_role("manager")),
) -> None:
    from backend.database.repositories.sensor_repo import SensorRepository  # type: ignore[import]

    repo = SensorRepository(db)
    success = await repo.deactivate(sensor_id, lagoon_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")


@router.post(
    "/{sensor_id}/calibrations",
    status_code=status.HTTP_201_CREATED,
    summary="Record sensor calibration",
)
async def record_calibration(
    body: SensorCalibrationCreate,
    lagoon_id: UUID = Path(...),
    sensor_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("operator")),
) -> dict:
    from backend.database.repositories.sensor_repo import SensorRepository  # type: ignore[import]

    repo = SensorRepository(db)
    sensor = await repo.get(sensor_id, lagoon_id)
    if sensor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")

    cal = await repo.create_calibration(
        sensor_id=sensor_id,
        data={
            **body.model_dump(exclude_none=True),
            "recorded_by": str(current_user["id"]),
        },
    )
    return cal
