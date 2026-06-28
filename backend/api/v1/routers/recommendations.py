"""Recommendation viewing, approval, and rejection endpoints."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from backend.api.v1.dependencies import (
    CurrentUserDep,
    DatabaseDep,
    EventBusDep,
    PaginationDep,
    require_role,
)
from backend.api.v1.schemas import (
    DecisionCycleResponse,
    PaginatedRecommendations,
    PaginationMeta,
    RecommendationApproveRequest,
    RecommendationRejectRequest,
    RecommendationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons/{lagoon_id}/recommendations", tags=["Recommendations"])


def _get_service(db: DatabaseDep, event_bus: EventBusDep):
    from backend.application.services.recommendation_service import RecommendationApplicationService
    from backend.database.repositories.recommendation_repo import (
        RecommendationRepository,  # type: ignore[import]
    )
    from backend.decision_engine.engine import DecisionEngine  # type: ignore[import]

    repo = RecommendationRepository(db)
    engine = DecisionEngine()
    return RecommendationApplicationService(repo, event_bus, engine)


@router.get("", response_model=PaginatedRecommendations, summary="List recommendations")
async def list_recommendations(
    lagoon_id: UUID = Path(...),
    pagination: PaginationDep = ...,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern="^(pending|approved|rejected|implemented|superseded)$",
    ),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
) -> PaginatedRecommendations:
    """Return recommendations for a lagoon, optionally filtered by status."""
    svc = _get_service(db, event_bus)
    try:
        recs = await svc.get_recommendations(lagoon_id, status=status_filter)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    page = recs[pagination.skip : pagination.skip + pagination.limit]
    return PaginatedRecommendations(
        items=[RecommendationResponse(**r) for r in page],
        meta=PaginationMeta(skip=pagination.skip, limit=pagination.limit, total=len(recs)),
    )


@router.post(
    "/{recommendation_id}/approve",
    response_model=RecommendationResponse,
    summary="Approve a recommendation",
)
async def approve_recommendation(
    body: RecommendationApproveRequest,
    lagoon_id: UUID = Path(...),
    recommendation_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("manager")),
) -> RecommendationResponse:
    """Approve a pending recommendation. Requires manager role."""
    svc = _get_service(db, event_bus)
    try:
        updated = await svc.approve_recommendation(
            recommendation_id=recommendation_id,
            user_id=UUID(str(current_user["id"])),
            notes=body.notes,
        )
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in detail else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return RecommendationResponse(**updated)


@router.post(
    "/{recommendation_id}/reject",
    response_model=RecommendationResponse,
    summary="Reject a recommendation",
)
async def reject_recommendation(
    body: RecommendationRejectRequest,
    lagoon_id: UUID = Path(...),
    recommendation_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("operator")),
) -> RecommendationResponse:
    """Reject a pending recommendation with a mandatory reason."""
    svc = _get_service(db, event_bus)
    try:
        updated = await svc.reject_recommendation(
            recommendation_id=recommendation_id,
            user_id=UUID(str(current_user["id"])),
            reason=body.reason,
        )
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in detail else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    return RecommendationResponse(**updated)


@router.post(
    "/trigger-cycle",
    response_model=DecisionCycleResponse,
    summary="Manually trigger a decision cycle",
)
async def trigger_decision_cycle(
    lagoon_id: UUID = Path(...),
    db: DatabaseDep = ...,
    event_bus: EventBusDep = ...,
    _: dict = Depends(require_role("operator")),
) -> DecisionCycleResponse:
    """Queue an immediate decision engine evaluation for this lagoon."""
    svc = _get_service(db, event_bus)
    result = await svc.trigger_decision_cycle(lagoon_id)
    return DecisionCycleResponse(**result)
