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


@app.task(bind=True)
def debug_task(self) -> str:  # type: ignore[type-arg]
    """Simple debug task for health checks."""
    return f"Request: {self.request!r}"
