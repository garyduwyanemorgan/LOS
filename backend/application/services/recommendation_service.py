"""Application service for recommendation lifecycle management."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)


# ── Protocols ────────────────────────────────────────────────────────────────

class RecommendationRepository(Protocol):
    async def list(self, lagoon_id: UUID, status: str | None) -> list[dict[str, Any]]: ...
    async def get(self, recommendation_id: UUID) -> dict[str, Any] | None: ...
    async def update_status(
        self,
        recommendation_id: UUID,
        status: str,
        reviewed_by: UUID,
        notes: str | None,
    ) -> dict[str, Any]: ...


class EventBus(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class DecisionEngine(Protocol):
    async def evaluate_lagoon(self, lagoon_id: UUID) -> dict[str, Any]: ...


# ── Service ──────────────────────────────────────────────────────────────────

VALID_STATUSES = {"pending", "approved", "rejected", "implemented", "superseded"}


class RecommendationApplicationService:
    """Manages the recommendation review and approval workflow."""

    def __init__(
        self,
        recommendation_repo: RecommendationRepository,
        event_bus: EventBus,
        decision_engine: DecisionEngine,
    ) -> None:
        self._repo = recommendation_repo
        self._bus = event_bus
        self._engine = decision_engine

    async def get_recommendations(
        self,
        lagoon_id: UUID,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recommendations for a lagoon, optionally filtered by status."""
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}")
        return await self._repo.list(lagoon_id, status)

    async def approve_recommendation(
        self,
        recommendation_id: UUID,
        user_id: UUID,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Mark a recommendation as approved.

        Only 'pending' recommendations can be approved.
        """
        rec = await self._get_and_validate(recommendation_id, expected_status="pending")

        updated = await self._repo.update_status(
            recommendation_id,
            status="approved",
            reviewed_by=user_id,
            notes=notes,
        )

        await self._bus.publish(
            "recommendation.approved",
            {
                "recommendation_id": str(recommendation_id),
                "lagoon_id": rec.get("lagoon_id"),
                "approved_by": str(user_id),
                "notes": notes,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        logger.info(
            "Recommendation approved id=%s by_user=%s",
            recommendation_id,
            user_id,
        )
        return updated

    async def reject_recommendation(
        self,
        recommendation_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> dict[str, Any]:
        """Mark a recommendation as rejected with a mandatory reason.

        Only 'pending' recommendations can be rejected.
        """
        if not reason or not reason.strip():
            raise ValueError("A rejection reason is required")

        rec = await self._get_and_validate(recommendation_id, expected_status="pending")

        updated = await self._repo.update_status(
            recommendation_id,
            status="rejected",
            reviewed_by=user_id,
            notes=reason,
        )

        await self._bus.publish(
            "recommendation.rejected",
            {
                "recommendation_id": str(recommendation_id),
                "lagoon_id": rec.get("lagoon_id"),
                "rejected_by": str(user_id),
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        logger.info(
            "Recommendation rejected id=%s by_user=%s",
            recommendation_id,
            user_id,
        )
        return updated

    async def trigger_decision_cycle(self, lagoon_id: UUID) -> dict[str, Any]:
        """Immediately invoke the decision engine for a lagoon.

        Publishes a trigger event so the background worker picks it up
        and also runs the engine directly for a synchronous summary.
        """
        await self._bus.publish(
            "decision_engine.cycle_requested",
            {
                "lagoon_id": str(lagoon_id),
                "triggered_at": datetime.now(UTC).isoformat(),
                "source": "manual_api_trigger",
            },
        )

        logger.info("Decision cycle triggered lagoon=%s", lagoon_id)
        return {
            "lagoon_id": str(lagoon_id),
            "status": "triggered",
            "message": "Decision engine cycle queued. Results will appear in recommendations.",
            "triggered_at": datetime.now(UTC).isoformat(),
        }

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _get_and_validate(
        self,
        recommendation_id: UUID,
        expected_status: str,
    ) -> dict[str, Any]:
        rec = await self._repo.get(recommendation_id)
        if rec is None:
            raise ValueError(f"Recommendation {recommendation_id} not found")
        current_status = rec.get("status")
        if current_status != expected_status:
            raise ValueError(
                f"Recommendation is '{current_status}', expected '{expected_status}'"
            )
        return rec
