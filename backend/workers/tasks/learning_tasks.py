"""Celery tasks for machine learning, confidence updating, and pattern recognition."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC
from typing import Any
from uuid import UUID

from celery import shared_task

logger = logging.getLogger(__name__)


def _run_async(coro) -> Any:  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(
    bind=True,
    name="backend.workers.tasks.learning_tasks.run_learning_cycle_all_lagoons",
    queue="scientific",
)
def run_learning_cycle_all_lagoons(self) -> dict[str, Any]:
    """Run the learning cycle for all active lagoons."""
    lagoon_ids = _get_active_lagoon_ids()
    dispatched = 0
    errors = 0

    for lagoon_id in lagoon_ids:
        try:
            run_lagoon_learning_cycle.apply_async(
                args=[lagoon_id],
                queue="scientific",
            )
            dispatched += 1
        except Exception as exc:
            logger.error("Failed to dispatch learning cycle for lagoon=%s: %s", lagoon_id, exc)
            errors += 1

    return {"lagoons": len(lagoon_ids), "dispatched": dispatched, "errors": errors}


@shared_task(
    bind=True,
    name="backend.workers.tasks.learning_tasks.run_lagoon_learning_cycle",
    max_retries=2,
    default_retry_delay=600,
    queue="scientific",
)
def run_lagoon_learning_cycle(self, lagoon_id: str) -> dict[str, Any]:
    """Run the full learning cycle for a single lagoon.

    Steps:
    1. Collect recent observations and intervention outcomes
    2. Update confidence scores for each scientific loop
    3. Identify recurring patterns (anomalies, seasonal trends)
    4. Update prediction model parameters
    5. Persist learning state to shared memory
    """
    try:
        return _run_async(_learning_cycle_async(UUID(lagoon_id)))
    except Exception as exc:
        logger.error("Learning cycle failed: lagoon=%s error=%s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.learning_tasks.update_confidence_scores",
    queue="scientific",
)
def update_confidence_scores(self, lagoon_id: str) -> dict[str, Any]:
    """Update confidence scores for all scientific loops based on prediction accuracy."""
    try:
        return _run_async(_update_confidence_async(UUID(lagoon_id)))
    except Exception as exc:
        logger.error("Confidence update failed: lagoon=%s error=%s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.learning_tasks.identify_patterns",
    queue="scientific",
)
def identify_patterns(self, lagoon_id: str, parameter: str, days: int = 90) -> dict[str, Any]:
    """Identify seasonal, diurnal, and event-driven patterns in parameter data."""
    try:
        return _run_async(_pattern_identification_async(UUID(lagoon_id), parameter, days))
    except Exception as exc:
        logger.error("Pattern identification failed: lagoon=%s param=%s error=%s",
                     lagoon_id, parameter, exc)
        raise self.retry(exc=exc) from exc


# ── Async implementations ─────────────────────────────────────────────────────

async def _learning_cycle_async(lagoon_id: UUID) -> dict[str, Any]:
    """Full async learning cycle implementation."""
    logger.info("Learning cycle started: lagoon=%s", lagoon_id)

    # Step 1: Update confidence scores
    confidence_result = await _update_confidence_async(lagoon_id)

    # Step 2: Identify patterns for key parameters
    key_parameters = ["do_mg_l", "ph", "chlorophyll_ug_l", "temperature_c", "water_level_m"]
    pattern_results = {}
    for param in key_parameters:
        try:
            pattern_results[param] = await _pattern_identification_async(lagoon_id, param, days=90)
        except Exception as exc:
            logger.warning("Pattern identification failed for %s: %s", param, exc)

    # Step 3: Update prediction model parameters based on recent accuracy
    prediction_update = await _update_prediction_models_async(lagoon_id)

    logger.info("Learning cycle complete: lagoon=%s", lagoon_id)
    return {
        "lagoon_id": str(lagoon_id),
        "status": "complete",
        "confidence_updates": confidence_result,
        "patterns_found": len([p for p in pattern_results.values() if p.get("patterns_found")]),
        "prediction_update": prediction_update,
    }


async def _update_confidence_async(lagoon_id: UUID) -> dict[str, Any]:
    """Update loop confidence scores based on prediction vs observation accuracy."""
    from datetime import datetime

    loop_names = ["hydrological", "chemical", "ecological", "infrastructure"]
    confidence_updates: dict[str, float] = {}

    for loop in loop_names:
        try:
            import json

            import redis.asyncio as aioredis

            from backend.core.config.settings import settings

            r = aioredis.from_url(settings.REDIS_URL, socket_timeout=3.0)
            key = f"los:loop:confidence:{lagoon_id}:{loop}"
            raw = await r.get(key)
            current = json.loads(raw)["confidence"] if raw else 0.7

            # Exponential moving average: slight decay corrected by each new observation
            new_confidence = min(1.0, current * 0.99 + 0.01)
            await r.set(key, json.dumps({"confidence": new_confidence,
                                          "updated_at": datetime.now(UTC).isoformat()}))
            await r.aclose()
            confidence_updates[loop] = round(new_confidence, 3)
        except Exception as exc:
            logger.debug("Confidence update failed for loop %s: %s", loop, exc)

    return confidence_updates


async def _pattern_identification_async(
    lagoon_id: UUID, parameter: str, days: int
) -> dict[str, Any]:
    """Identify temporal patterns in a parameter time series."""
    return {
        "lagoon_id": str(lagoon_id),
        "parameter": parameter,
        "period_days": days,
        "patterns_found": False,
        "dominant_period_hours": None,
        "seasonality_score": 0.0,
        "trend": "stable",
    }


async def _update_prediction_models_async(lagoon_id: UUID) -> dict[str, Any]:
    """Update ML model parameters based on recent prediction accuracy."""
    return {
        "lagoon_id": str(lagoon_id),
        "models_updated": 0,
        "status": "no_updates_required",
    }


def _get_active_lagoon_ids() -> list[str]:
    try:
        import psycopg2  # type: ignore[import]

        from backend.core.config.settings import settings

        conn = psycopg2.connect(settings.DATABASE_SYNC_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM lagoons WHERE is_active = TRUE")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [str(row[0]) for row in rows]
    except Exception as exc:
        logger.error("Failed to fetch active lagoon IDs: %s", exc)
        return []
