"""Celery tasks for scientific loop evaluation.

Each task corresponds to one of the LOS scientific service loops.
Tasks are idempotent: running them twice produces the same final state.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


# ── Helper: run async in Celery worker ───────────────────────────────────────

def _run_async(coro) -> Any:  # type: ignore[no-untyped-def]
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Per-lagoon loop tasks ─────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_hydrological_loop",
    max_retries=3,
    default_retry_delay=60,
    queue="scientific",
)
def run_hydrological_loop(self, lagoon_id: str) -> dict[str, Any]:
    """Run hydrological loop evaluation for a single lagoon.

    Computes: water balance, residence time, ET0, groundwater flux,
    tidal exchange, and hydraulic connectivity score.
    """
    try:
        return _run_async(_hydrological_loop_async(UUID(lagoon_id)))
    except SoftTimeLimitExceeded:
        logger.warning("Hydrological loop soft time limit exceeded: lagoon=%s", lagoon_id)
        return {"status": "timeout", "lagoon_id": lagoon_id}
    except Exception as exc:
        logger.error("Hydrological loop error lagoon=%s: %s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_chemical_loop",
    max_retries=3,
    default_retry_delay=60,
    queue="scientific",
)
def run_chemical_loop(self, lagoon_id: str) -> dict[str, Any]:
    """Run chemical analysis loop for a single lagoon.

    Computes: redox state, DO saturation, internal loading risk,
    carbonate system, TSI, and nutrient status.
    """
    try:
        return _run_async(_chemical_loop_async(UUID(lagoon_id)))
    except SoftTimeLimitExceeded:
        logger.warning("Chemical loop soft time limit exceeded: lagoon=%s", lagoon_id)
        return {"status": "timeout", "lagoon_id": lagoon_id}
    except Exception as exc:
        logger.error("Chemical loop error lagoon=%s: %s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_ecological_loop",
    max_retries=3,
    default_retry_delay=60,
    queue="scientific",
)
def run_ecological_loop(self, lagoon_id: str) -> dict[str, Any]:
    """Run ecological assessment loop for a single lagoon.

    Computes: bloom probability, cyanobacteria advantage index,
    succession stage, trophic state, and biodiversity stress indicators.
    """
    try:
        return _run_async(_ecological_loop_async(UUID(lagoon_id)))
    except SoftTimeLimitExceeded:
        logger.warning("Ecological loop soft time limit exceeded: lagoon=%s", lagoon_id)
        return {"status": "timeout", "lagoon_id": lagoon_id}
    except Exception as exc:
        logger.error("Ecological loop error lagoon=%s: %s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_infrastructure_loop",
    max_retries=3,
    default_retry_delay=60,
    queue="scientific",
)
def run_infrastructure_loop(self, lagoon_id: str) -> dict[str, Any]:
    """Run infrastructure assessment loop for a single lagoon.

    Evaluates: pump efficiency, sensor health, structure integrity,
    SCADA connectivity, and maintenance scheduling.
    """
    try:
        return _run_async(_infrastructure_loop_async(UUID(lagoon_id)))
    except SoftTimeLimitExceeded:
        logger.warning("Infrastructure loop soft time limit exceeded: lagoon=%s", lagoon_id)
        return {"status": "timeout", "lagoon_id": lagoon_id}
    except Exception as exc:
        logger.error("Infrastructure loop error lagoon=%s: %s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_compliance_loop",
    max_retries=3,
    default_retry_delay=60,
    queue="scientific",
)
def run_compliance_loop(self, lagoon_id: str) -> dict[str, Any]:
    """Run compliance evaluation loop for a single lagoon.

    Evaluates current conditions against UAE Environmental Agency limits,
    permit conditions, and internal KPIs. Publishes violations as events.
    """
    try:
        return _run_async(_compliance_loop_async(UUID(lagoon_id)))
    except SoftTimeLimitExceeded:
        logger.warning("Compliance loop soft time limit exceeded: lagoon=%s", lagoon_id)
        return {"status": "timeout", "lagoon_id": lagoon_id}
    except Exception as exc:
        logger.error("Compliance loop error lagoon=%s: %s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_decision_engine",
    max_retries=2,
    default_retry_delay=120,
    queue="scientific",
)
def run_decision_engine(self, lagoon_id: str) -> dict[str, Any]:
    """Run decision engine evaluation for a single lagoon.

    Reads all loop states, generates and scores intervention options,
    persists top recommendations, and notifies operators.
    """
    try:
        return _run_async(_decision_engine_async(UUID(lagoon_id)))
    except SoftTimeLimitExceeded:
        logger.warning("Decision engine soft time limit exceeded: lagoon=%s", lagoon_id)
        return {"status": "timeout", "lagoon_id": lagoon_id}
    except Exception as exc:
        logger.error("Decision engine error lagoon=%s: %s", lagoon_id, exc)
        raise self.retry(exc=exc) from exc


# ── Fleet-wide orchestration tasks ───────────────────────────────────────────

@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_all_scientific_loops",
    queue="scientific",
)
def run_all_scientific_loops(self) -> dict[str, Any]:
    """Run all scientific loops for all active lagoons.

    Dispatches individual loop tasks for each lagoon in parallel.
    """
    lagoon_ids = _get_active_lagoon_ids()
    dispatched = 0
    errors = 0

    for lagoon_id in lagoon_ids:
        try:
            run_hydrological_loop.apply_async(args=[lagoon_id], queue="scientific")
            run_chemical_loop.apply_async(args=[lagoon_id], queue="scientific")
            run_ecological_loop.apply_async(args=[lagoon_id], queue="scientific")
            run_infrastructure_loop.apply_async(args=[lagoon_id], queue="scientific")
            run_compliance_loop.apply_async(args=[lagoon_id], queue="scientific")
            dispatched += 5
        except Exception as exc:
            logger.error("Failed to dispatch loops for lagoon=%s: %s", lagoon_id, exc)
            errors += 1

    logger.info("Scientific loops dispatched: lagoons=%d tasks=%d errors=%d",
                len(lagoon_ids), dispatched, errors)
    return {"lagoons": len(lagoon_ids), "tasks_dispatched": dispatched, "errors": errors}


@shared_task(
    bind=True,
    name="backend.workers.tasks.scientific_tasks.run_decision_engine_all_lagoons",
    queue="scientific",
)
def run_decision_engine_all_lagoons(self) -> dict[str, Any]:
    """Run the decision engine for all active lagoons."""
    lagoon_ids = _get_active_lagoon_ids()
    dispatched = 0
    errors = 0

    for lagoon_id in lagoon_ids:
        try:
            run_decision_engine.apply_async(args=[lagoon_id], queue="scientific")
            dispatched += 1
        except Exception as exc:
            logger.error("Failed to dispatch decision engine for lagoon=%s: %s", lagoon_id, exc)
            errors += 1

    logger.info("Decision engine dispatched: lagoons=%d dispatched=%d errors=%d",
                len(lagoon_ids), dispatched, errors)
    return {"lagoons": len(lagoon_ids), "dispatched": dispatched, "errors": errors}


# ── Async implementations ─────────────────────────────────────────────────────

async def _hydrological_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    """Async implementation of hydrological loop evaluation."""
    from backend.scientific_services.hydrological import HydrologicalService  # type: ignore[import]

    service = await _build_scientific_service(HydrologicalService, lagoon_id)
    state = await service.compute_state(lagoon_id)
    await service.publish_state(lagoon_id)
    logger.info("Hydrological loop complete: lagoon=%s confidence=%.2f",
                lagoon_id, state.get("confidence", 0))
    return {"lagoon_id": str(lagoon_id), "status": "complete", **state}


async def _chemical_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    """Async implementation of chemical loop evaluation."""
    from backend.scientific_services.chemical import ChemicalService  # type: ignore[import]

    service = await _build_scientific_service(ChemicalService, lagoon_id)
    state = await service.compute_state(lagoon_id)
    await service.publish_state(lagoon_id)
    logger.info("Chemical loop complete: lagoon=%s confidence=%.2f",
                lagoon_id, state.get("confidence", 0))
    return {"lagoon_id": str(lagoon_id), "status": "complete", **state}


async def _ecological_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    """Async implementation of ecological loop evaluation."""
    from backend.scientific_services.ecological import EcologicalService  # type: ignore[import]

    service = await _build_scientific_service(EcologicalService, lagoon_id)
    state = await service.compute_state(lagoon_id)
    await service.publish_state(lagoon_id)
    return {"lagoon_id": str(lagoon_id), "status": "complete", **state}


async def _infrastructure_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    """Async implementation of infrastructure loop evaluation."""
    from backend.scientific_services.infrastructure import (
        InfrastructureService,  # type: ignore[import]
    )

    service = await _build_scientific_service(InfrastructureService, lagoon_id)
    state = await service.compute_state(lagoon_id)
    await service.publish_state(lagoon_id)
    return {"lagoon_id": str(lagoon_id), "status": "complete", **state}


async def _compliance_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    """Async implementation of compliance evaluation loop."""
    from backend.scientific_services.compliance import ComplianceService  # type: ignore[import]

    service = ComplianceService(shared_memory=None, event_bus=None)
    status = await service.evaluate_lagoon(lagoon_id)
    logger.info(
        "Compliance loop complete: lagoon=%s level=%s violations=%d",
        lagoon_id, status.overall_level.value, status.violations_count,
    )
    return {
        "lagoon_id": str(lagoon_id),
        "status": "complete",
        "compliance_level": status.overall_level.value,
        "violations_count": status.violations_count,
        "critical_count": status.critical_count,
    }


async def _decision_engine_async(lagoon_id: UUID) -> dict[str, Any]:
    """Async implementation of decision engine evaluation."""
    from backend.decision_engine.engine import DecisionEngine  # type: ignore[import]

    engine = DecisionEngine()
    result = await engine.evaluate_lagoon(lagoon_id)
    return {"lagoon_id": str(lagoon_id), "status": "complete", **result}


async def _build_scientific_service(service_class: type, lagoon_id: UUID) -> Any:
    """Construct a scientific service with its dependencies."""
    # In production, this would wire up the full dependency graph.
    # For worker context, we create standalone service instances.
    service = service_class()
    return service


def _get_active_lagoon_ids() -> list[str]:
    """Return IDs of all active lagoons from the database.

    Uses a synchronous DB connection since this runs in a Celery worker.
    """
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
