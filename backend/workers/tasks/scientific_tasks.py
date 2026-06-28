"""Celery tasks for scientific loop evaluation.

Each task corresponds to one of the LOS scientific service loops.
Tasks are idempotent: running them twice produces the same final state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
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
    """Run hydrological loop evaluation for a single lagoon."""
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
    """Run chemical analysis loop for a single lagoon."""
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
    """Run ecological assessment loop for a single lagoon."""
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
    """Run infrastructure assessment loop for a single lagoon."""
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
    """Run compliance evaluation loop for a single lagoon."""
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
    """Run decision engine evaluation for a single lagoon."""
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
    """Run all scientific loops for all active lagoons."""
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


# ── Dependency wiring ─────────────────────────────────────────────────────────

class _NullBus:
    async def publish(self, *a: Any, **kw: Any) -> None: pass
    async def subscribe(self, *a: Any, **kw: Any) -> None: pass


async def _make_deps() -> tuple[Any, Any]:
    """Create SharedMemoryService + Redis client for use in worker tasks."""
    import os
    import redis.asyncio as aioredis
    from backend.shared_memory.service import SharedMemoryService

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    shared_memory = SharedMemoryService(redis_client)
    return shared_memory, redis_client


async def _fetch_sensor_cache(lagoon_id: UUID) -> dict[str, float]:
    """Fetch latest readings from DB and map to service cache keys."""
    import os
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    PARAM_MAP = {
        "dissolved_oxygen": "do_mg_l",
        "ph": "ph",
        "orp": "orp_mv",
        "water_temperature": "temperature_c",
        "turbidity": "turbidity_ntu",
        "chlorophyll_a": "chlorophyll_a_ug_l",
        "conductivity": "conductivity_us_cm",
    }

    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session() as session:
            rows = await session.execute(text("""
                SELECT DISTINCT ON (parameter) parameter, value
                FROM observations
                WHERE lagoon_id = :lid
                ORDER BY parameter, timestamp DESC
            """), {"lid": lagoon_id})
            readings = {r.parameter: r.value for r in rows.fetchall()}
    finally:
        await engine.dispose()

    cache: dict[str, float] = {}
    for db_param, svc_key in PARAM_MAP.items():
        if db_param in readings:
            cache[svc_key] = readings[db_param]

    if "conductivity_us_cm" in cache:
        cache["salinity_ppt"] = max(0.0, cache["conductivity_us_cm"] * 0.55)

    return cache


async def _build_scientific_service(service_class: type, lagoon_id: UUID) -> tuple[Any, Any, Any]:
    """Construct a scientific service with proper dependencies and sensor data."""
    shared_memory, redis_client = await _make_deps()
    service = service_class(shared_memory=shared_memory, event_bus=_NullBus())

    sensor_cache = await _fetch_sensor_cache(lagoon_id)
    if hasattr(service, '_sensor_cache'):
        service._sensor_cache[lagoon_id] = sensor_cache

    return service, shared_memory, redis_client


# ── Async implementations ─────────────────────────────────────────────────────

async def _hydrological_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    from backend.scientific_services.hydrological.service import HydrologicalService  # type: ignore[import]

    service, shared_memory, redis_client = await _build_scientific_service(HydrologicalService, lagoon_id)
    try:
        state = await service.compute_state(lagoon_id)
        await shared_memory.store_scientific_memory(lagoon_id, "hydrological", "state", state)
        logger.info("Hydrological loop complete: lagoon=%s confidence=%.2f",
                    lagoon_id, state.get("confidence", 0))
        return {"lagoon_id": str(lagoon_id), "status": "complete", **state}
    finally:
        await redis_client.aclose()


async def _chemical_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    from backend.scientific_services.chemical.service import ChemicalService  # type: ignore[import]

    service, shared_memory, redis_client = await _build_scientific_service(ChemicalService, lagoon_id)
    try:
        state = await service.compute_state(lagoon_id)
        await shared_memory.store_scientific_memory(lagoon_id, "chemical", "state", state)
        logger.info("Chemical loop complete: lagoon=%s confidence=%.2f",
                    lagoon_id, state.get("confidence", 0))
        return {"lagoon_id": str(lagoon_id), "status": "complete", **state}
    finally:
        await redis_client.aclose()


async def _ecological_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    from backend.scientific_services.ecological.service import EcologicalService  # type: ignore[import]

    service, shared_memory, redis_client = await _build_scientific_service(EcologicalService, lagoon_id)
    try:
        state = await service.compute_state(lagoon_id)
        await shared_memory.store_scientific_memory(lagoon_id, "ecological", "state", state)
        logger.info("Ecological loop complete: lagoon=%s confidence=%.2f",
                    lagoon_id, state.get("confidence", 0))
        return {"lagoon_id": str(lagoon_id), "status": "complete", **state}
    finally:
        await redis_client.aclose()


async def _infrastructure_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    from backend.scientific_services.infrastructure.service import InfrastructureService  # type: ignore[import]

    service, shared_memory, redis_client = await _build_scientific_service(InfrastructureService, lagoon_id)
    try:
        state = await service.compute_state(lagoon_id)
        await shared_memory.store_scientific_memory(lagoon_id, "infrastructure", "state", state)
        logger.info("Infrastructure loop complete: lagoon=%s confidence=%.2f",
                    lagoon_id, state.get("confidence", 0))
        return {"lagoon_id": str(lagoon_id), "status": "complete", **state}
    finally:
        await redis_client.aclose()


async def _compliance_loop_async(lagoon_id: UUID) -> dict[str, Any]:
    from backend.scientific_services.compliance.service import ComplianceService  # type: ignore[import]

    shared_memory, redis_client = await _make_deps()
    try:
        service = ComplianceService(shared_memory=shared_memory, event_bus=_NullBus())
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
    finally:
        await redis_client.aclose()


async def _decision_engine_async(lagoon_id: UUID) -> dict[str, Any]:
    import os
    from datetime import UTC, datetime
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text
    from backend.decision_engine.engine import DecisionEngine  # type: ignore[import]

    shared_memory, redis_client = await _make_deps()
    try:
        engine = DecisionEngine(shared_memory=shared_memory)
        rec = await engine.run_decision_cycle(
            lagoon_id=lagoon_id,
            trigger_event="scheduled",
        )

        if rec is None:
            logger.info("Decision engine: no recommendation for lagoon=%s", lagoon_id)
            return {"lagoon_id": str(lagoon_id), "status": "no_action"}

        logger.info("Decision engine: lagoon=%s action=%r confidence=%.2f",
                    lagoon_id, rec.recommended_action, rec.confidence)

        # Persist recommendation to DB
        CATEGORY_MAP = {
            "aeration": "aeration", "chemical_dosing": "chemical_dosing",
            "tse_management": "water_management", "circulation": "water_management",
            "maintenance": "maintenance", "monitoring": "monitoring",
            "dredging": "dredging", "observation": "monitoring", "no_action": "other",
        }
        PRIORITY_MAP = {
            "immediate": "critical", "urgent": "high",
            "routine": "normal", "planned": "low", "monitoring": "low",
        }
        raw_cat = rec.category.value if hasattr(rec.category, 'value') else str(rec.category)
        raw_urg = rec.urgency.value if hasattr(rec.urgency, 'value') else str(rec.urgency)
        category_val = CATEGORY_MAP.get(raw_cat, "other")
        urgency_val = PRIORITY_MAP.get(raw_urg, "normal")
        timeframe_days = None
        if hasattr(rec, 'expected_timeframe_hours') and rec.expected_timeframe_hours:
            timeframe_days = max(1, int(rec.expected_timeframe_hours / 24))

        alt_json = json.dumps([
            {"action": a.get("action_title", a.get("recommended_action", "")),
             "score": a.get("overall_score", 0)} if isinstance(a, dict) else
            {"action": a.recommended_action, "score": a.overall_score}
            for a in (rec.alternative_options or [])
        ] if rec.alternative_options else [])

        db_engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
        async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with async_session() as session:
                await session.execute(text("""
                    INSERT INTO recommendations (
                        id, lagoon_id, action, action_category, scientific_reason,
                        contributing_loops, evidence, confidence,
                        priority, expected_outcome, expected_timeframe_days,
                        alternative_options, operating_objective_ids,
                        status, created_by_system, created_at, updated_at
                    ) VALUES (
                        :id, :lagoon_id, :action, :action_category, :scientific_reason,
                        CAST(:contributing_loops AS jsonb), CAST(:evidence AS jsonb),
                        :confidence, :priority, :expected_outcome, :timeframe_days,
                        CAST(:alternatives AS jsonb), CAST('[]' AS jsonb),
                        'pending', true, NOW(), NOW()
                    )
                """), {
                    "id": uuid.uuid4(),
                    "lagoon_id": lagoon_id,
                    "action": rec.recommended_action,
                    "action_category": category_val,
                    "scientific_reason": rec.why_recommended,
                    "contributing_loops": json.dumps(rec.contributing_loops),
                    "evidence": json.dumps(rec.supporting_evidence or []),
                    "confidence": rec.confidence,
                    "priority": urgency_val,
                    "expected_outcome": rec.what_will_happen or "",
                    "timeframe_days": timeframe_days,
                    "alternatives": alt_json,
                })
                await session.commit()
        finally:
            await db_engine.dispose()

        return {
            "lagoon_id": str(lagoon_id),
            "status": "complete",
            "action": rec.recommended_action,
            "confidence": rec.confidence,
        }
    finally:
        await redis_client.aclose()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_active_lagoon_ids() -> list[str]:
    """Return IDs of all active lagoons from the database."""
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
