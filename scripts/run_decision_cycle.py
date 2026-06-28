"""
Full decision cycle script:
  1. Fetch latest sensor readings from DB
  2. Inject into scientific services
  3. Compute all loop states
  4. Write to Redis shared memory
  5. Run Decision Engine
  6. Persist top recommendation to DB

Run inside the backend container:
  docker exec los_backend python /app/scripts/run_decision_cycle.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("decision_cycle")

LAGOON_ID = UUID("11111111-1111-1111-1111-111111111111")


async def main() -> None:
    import os
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    DATABASE_URL = os.environ["DATABASE_URL"]
    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    # ── 1. Fetch latest observation per parameter ─────────────────────────────
    print("Fetching latest sensor readings...", flush=True)
    async with async_session() as session:
        rows = await session.execute(text("""
            SELECT DISTINCT ON (parameter)
                parameter, value, unit, timestamp
            FROM observations
            WHERE lagoon_id = :lid
            ORDER BY parameter, timestamp DESC
        """), {"lid": LAGOON_ID})
        readings = {r.parameter: {"value": r.value, "unit": r.unit, "ts": r.timestamp}
                    for r in rows.fetchall()}

    print(f"  Got {len(readings)} parameters: {list(readings)}", flush=True)

    # Map our DB parameter names to what services expect in their cache
    PARAM_MAP = {
        "dissolved_oxygen": "do_mg_l",
        "ph": "ph",
        "orp": "orp_mv",
        "water_temperature": "temperature_c",
        "turbidity": "turbidity_ntu",
        "chlorophyll_a": "chlorophyll_a_ug_l",
        "conductivity": "conductivity_us_cm",
    }
    sensor_cache: dict[str, float] = {}
    for db_param, svc_key in PARAM_MAP.items():
        if db_param in readings:
            sensor_cache[svc_key] = readings[db_param]["value"]

    # Derive salinity from conductivity (mS/cm → ppt approx, for brackish)
    if "conductivity_us_cm" in sensor_cache:
        cond_ms = sensor_cache["conductivity_us_cm"]  # already mS/cm from our seed
        sensor_cache["salinity_ppt"] = max(0.0, cond_ms * 0.55)  # rough conversion

    print(f"  Service cache: {sensor_cache}", flush=True)

    # ── 2. Run scientific services ────────────────────────────────────────────
    from backend.shared_memory.service import SharedMemoryService
    shared_memory = SharedMemoryService(redis)

    class NullBus:
        async def publish(self, *a, **kw): pass
        async def subscribe(self, *a, **kw): pass

    bus = NullBus()

    from backend.scientific_services.chemical.service import ChemicalService
    from backend.scientific_services.ecological.service import EcologicalService
    from backend.scientific_services.hydrological.service import HydrologicalService
    from backend.scientific_services.infrastructure.service import InfrastructureService

    loop_results: dict[str, dict] = {}

    for name, svc_class in [
        ("chemical", ChemicalService),
        ("ecological", EcologicalService),
        ("hydrological", HydrologicalService),
        ("infrastructure", InfrastructureService),
    ]:
        print(f"  Running {name} loop...", flush=True)
        try:
            svc = svc_class(shared_memory=shared_memory, event_bus=bus)
            if hasattr(svc, '_sensor_cache'):
                svc._sensor_cache[LAGOON_ID] = dict(sensor_cache)
            state = await svc.compute_state(LAGOON_ID)
            conf = state.get("confidence", 0.0)
            loop_results[name] = state
            print(f"    {name}: confidence={conf:.0%}", flush=True)

            # Store in shared memory so decision engine can read it
            await shared_memory.store_scientific_memory(
                LAGOON_ID, name, "state", state
            )
            await shared_memory.store_short_term(
                LAGOON_ID, f"loop_{name}", state
            )
        except Exception as exc:
            print(f"    {name} ERROR: {exc}", flush=True)
            import traceback; traceback.print_exc()

    # Also store confidence scores in short-term memory
    scores = {name: s.get("confidence", 0.0) for name, s in loop_results.items()}
    await shared_memory.store_short_term(LAGOON_ID, "confidence_scores", scores)
    print(f"  Confidence scores stored: {scores}", flush=True)

    # ── 3. Run Decision Engine ────────────────────────────────────────────────
    print("\nRunning Decision Engine...", flush=True)
    from backend.decision_engine.engine import DecisionEngine

    engine = DecisionEngine(shared_memory=shared_memory)
    rec = await engine.run_decision_cycle(
        lagoon_id=LAGOON_ID,
        trigger_event="manual_trigger",
    )

    if rec is None:
        print("  No recommendation generated", flush=True)
        await engine_cleanup(redis, engine)
        return

    print(f"  Action: {rec.recommended_action}", flush=True)
    print(f"  Category: {rec.category}", flush=True)
    print(f"  Urgency: {rec.urgency}", flush=True)
    print(f"  Confidence: {rec.confidence:.0%}", flush=True)
    print(f"  Score: {rec.overall_score:.3f}", flush=True)
    print(f"  Why: {rec.why_recommended[:100]}...", flush=True)

    # ── 4. Persist recommendation to DB ──────────────────────────────────────
    print("\nPersisting recommendation to DB...", flush=True)
    async with async_session() as session:
        rec_id = uuid.uuid4()
        # Map engine enums → DB check constraint values
        CATEGORY_MAP = {
            "aeration": "aeration", "chemical_dosing": "chemical_dosing",
            "tse_management": "water_management", "circulation": "water_management",
            "maintenance": "maintenance", "monitoring": "monitoring",
            "dredging": "dredging", "observation": "monitoring",
            "no_action": "other",
        }
        PRIORITY_MAP = {
            "immediate": "critical", "urgent": "high",
            "routine": "normal", "planned": "low", "monitoring": "low",
        }
        raw_cat = rec.category.value if hasattr(rec.category, 'value') else str(rec.category)
        raw_urg = rec.urgency.value if hasattr(rec.urgency, 'value') else str(rec.urgency)
        category_val = CATEGORY_MAP.get(raw_cat, "other")
        urgency_val = PRIORITY_MAP.get(raw_urg, "normal")

        alt_json = json.dumps([
            {"action": a.get("action_title", a.get("recommended_action", "")),
             "score": a.get("overall_score", 0)} if isinstance(a, dict) else
            {"action": a.recommended_action, "score": a.overall_score}
            for a in (rec.alternative_options or [])
        ] if rec.alternative_options else [])
        timeframe_days = None
        if hasattr(rec, 'expected_timeframe_hours') and rec.expected_timeframe_hours:
            timeframe_days = max(1, int(rec.expected_timeframe_hours / 24))

        await session.execute(text("""
            INSERT INTO recommendations (
                id, lagoon_id,
                action, action_category, scientific_reason,
                contributing_loops, evidence, confidence,
                priority, expected_outcome, expected_timeframe_days,
                alternative_options, operating_objective_ids,
                status, created_by_system,
                created_at, updated_at
            ) VALUES (
                :id, :lagoon_id,
                :action, :action_category, :scientific_reason,
                CAST(:contributing_loops AS jsonb),
                CAST(:evidence AS jsonb),
                :confidence,
                :priority, :expected_outcome, :timeframe_days,
                CAST(:alternatives AS jsonb),
                CAST('[]' AS jsonb),
                'pending', true,
                NOW(), NOW()
            )
        """), {
            "id": rec_id,
            "lagoon_id": LAGOON_ID,
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
        print(f"  Saved recommendation {rec_id}", flush=True)

    # ── 5. Store events in shared memory ─────────────────────────────────────
    events = [
        {
            "id": str(uuid.uuid4()),
            "type": "recommendation_generated",
            "lagoon_id": str(LAGOON_ID),
            "title": "Decision Engine Cycle Complete",
            "message": f"Recommended: {rec.recommended_action} (confidence {rec.confidence:.0%})",
            "severity": "info",
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "type": "loop_evaluation_complete",
            "lagoon_id": str(LAGOON_ID),
            "title": "Scientific Loops Evaluated",
            "message": f"Chemical {scores.get('chemical', 0):.0%} | Ecological {scores.get('ecological', 0):.0%} | Hydro {scores.get('hydrological', 0):.0%}",
            "severity": "info",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]
    # Add a water quality alert if DO is low
    if sensor_cache.get("do_mg_l", 99) < 5.0:
        events.append({
            "id": str(uuid.uuid4()),
            "type": "alert",
            "lagoon_id": str(LAGOON_ID),
            "title": "Low Dissolved Oxygen Alert",
            "message": f"DO at {sensor_cache['do_mg_l']:.1f} mg/L — below 5 mg/L threshold",
            "severity": "warning",
            "timestamp": datetime.now(UTC).isoformat(),
        })
    if sensor_cache.get("chlorophyll_a_ug_l", 0) > 50:
        events.append({
            "id": str(uuid.uuid4()),
            "type": "alert",
            "lagoon_id": str(LAGOON_ID),
            "title": "Elevated Chlorophyll-a",
            "message": f"Chl-a at {sensor_cache['chlorophyll_a_ug_l']:.1f} µg/L — bloom risk elevated",
            "severity": "warning",
            "timestamp": datetime.now(UTC).isoformat(),
        })

    await shared_memory.store_short_term(LAGOON_ID, "recent_events", events)
    print(f"  {len(events)} events stored in shared memory", flush=True)

    await redis.aclose()
    await engine.dispose() if hasattr(engine, 'dispose') else None
    print("\nDecision cycle complete.", flush=True)


async def engine_cleanup(redis, engine):
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
