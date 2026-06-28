"""Trigger all scientific loops synchronously for Al Qudra Lake 1."""
import sys

LAGOON = '11111111-1111-1111-1111-111111111111'

from backend.workers.tasks.scientific_tasks import (
    run_hydrological_loop,
    run_chemical_loop,
    run_ecological_loop,
    run_infrastructure_loop,
    run_compliance_loop,
)

tasks = [
    ('Hydrological', run_hydrological_loop),
    ('Chemical',     run_chemical_loop),
    ('Ecological',   run_ecological_loop),
    ('Infrastructure', run_infrastructure_loop),
    ('Compliance',   run_compliance_loop),
]

for name, task in tasks:
    print(f"Running {name} loop...", flush=True)
    try:
        r = task.apply(args=[LAGOON])
        result = r.result
        if isinstance(result, dict):
            conf = result.get('confidence', result.get('score', '?'))
            status = result.get('status', 'ok')
            print(f"  {name}: status={status} confidence={conf}", flush=True)
        else:
            print(f"  {name}: {result}", flush=True)
    except Exception as e:
        print(f"  {name} ERROR: {e}", flush=True)

print("\nNow running Decision Engine...", flush=True)
try:
    from backend.decision_engine.engine import DecisionEngine
    import asyncio

    async def run():
        engine = DecisionEngine()
        result = await engine.run_decision_cycle(
            lagoon_id=__import__('uuid').UUID(LAGOON),
            trigger_event='manual',
        )
        if result:
            print(f"  Recommendation: {result.recommended_action}")
            print(f"  Confidence: {result.confidence:.0%}")
            print(f"  Score: {result.overall_score:.3f}")
            print(f"  Urgency: {result.urgency}")
            return result
        else:
            print("  No recommendation generated")
            return None

    rec = asyncio.run(run())
except Exception as e:
    print(f"  Decision Engine ERROR: {e}", flush=True)
    import traceback; traceback.print_exc()

print("\nDone.", flush=True)
