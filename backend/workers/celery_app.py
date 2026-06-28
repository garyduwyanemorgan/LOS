"""Celery application factory for the LOS background worker system."""
from __future__ import annotations

from celery import Celery

# ── Application ───────────────────────────────────────────────────────────────

app = Celery("los")
app.config_from_object("backend.workers.celery_config")

# ── Auto-discovery ────────────────────────────────────────────────────────────

app.autodiscover_tasks(
    packages=[
        "backend.workers.tasks.scientific_tasks",
        "backend.workers.tasks.simulation_tasks",
        "backend.workers.tasks.reporting_tasks",
        "backend.workers.tasks.learning_tasks",
        "backend.workers.tasks.notification_tasks",
    ],
    force=True,
)


# ── Signals ───────────────────────────────────────────────────────────────────

@app.on_after_configure.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    """Register periodic tasks programmatically (supplements beat_schedule in config)."""
    pass  # Defined in celery_config.beat_schedule


from celery.signals import worker_ready  # noqa: E402


@worker_ready.connect
def _run_loops_on_startup(sender: object, **kwargs: object) -> None:
    """Warm up Redis with fresh loop states immediately after worker start."""
    try:
        from backend.workers.tasks.scientific_tasks import run_all_scientific_loops
        run_all_scientific_loops.apply_async(queue='scientific', countdown=5)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Startup loop warmup failed: %s", exc)


@app.task(bind=True)
def debug_task(self) -> str:  # type: ignore[type-arg]
    """Simple debug task for health checks."""
    return f"Request: {self.request!r}"
