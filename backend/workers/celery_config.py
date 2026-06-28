"""Celery configuration for the LOS worker system."""
from __future__ import annotations

from celery.schedules import crontab
from kombu import Exchange, Queue

from backend.core.config.settings import settings

# ── Broker / Backend ──────────────────────────────────────────────────────────

broker_url = settings.CELERY_BROKER_URL
result_backend = settings.CELERY_RESULT_BACKEND
result_expires = 86400  # 24 hours

# ── Serialisation ─────────────────────────────────────────────────────────────

task_serializer = settings.CELERY_TASK_SERIALIZER
result_serializer = settings.CELERY_RESULT_SERIALIZER
accept_content = ["json"]
timezone = "UTC"
enable_utc = True

# ── Task behaviour ────────────────────────────────────────────────────────────

task_always_eager = settings.CELERY_TASK_ALWAYS_EAGER
task_eager_propagates = True
task_acks_late = True
task_reject_on_worker_lost = True
task_track_started = True
worker_prefetch_multiplier = 1  # One task at a time for heavy scientific tasks

# ── Queues ────────────────────────────────────────────────────────────────────

default_exchange = Exchange("default", type="direct")
scientific_exchange = Exchange("scientific", type="direct")
simulation_exchange = Exchange("simulations", type="direct")
notification_exchange = Exchange("notifications", type="direct")
reporting_exchange = Exchange("reporting", type="direct")

task_queues = (
    Queue("default",       default_exchange,       routing_key="default"),
    Queue("scientific",    scientific_exchange,    routing_key="scientific"),
    Queue("simulations",   simulation_exchange,    routing_key="simulations"),
    Queue("notifications", notification_exchange,  routing_key="notifications"),
    Queue("reporting",     reporting_exchange,     routing_key="reporting"),
)

task_default_queue = "default"
task_default_exchange = "default"
task_default_routing_key = "default"

# ── Routing ───────────────────────────────────────────────────────────────────

task_routes = {
    "backend.workers.tasks.scientific_tasks.*":   {"queue": "scientific"},
    "backend.workers.tasks.simulation_tasks.*":   {"queue": "simulations"},
    "backend.workers.tasks.reporting_tasks.*":    {"queue": "reporting"},
    "backend.workers.tasks.notification_tasks.*": {"queue": "notifications"},
    "backend.workers.tasks.learning_tasks.*":     {"queue": "scientific"},
}

# ── Time limits ───────────────────────────────────────────────────────────────

task_soft_time_limit = 3600    # 1 hour: soft limit raises SoftTimeLimitExceeded
task_time_limit = 7200         # 2 hours: hard kill

# Override for simulation tasks (MODFLOW/PHREEQC can run for hours)
task_annotations = {
    "backend.workers.tasks.simulation_tasks.run_modflow_simulation": {
        "soft_time_limit": 21600,  # 6 hours
        "time_limit": 28800,       # 8 hours
    },
    "backend.workers.tasks.simulation_tasks.run_phreeqc_simulation": {
        "soft_time_limit": 7200,
        "time_limit": 10800,
    },
}

# ── Beat schedule ─────────────────────────────────────────────────────────────

beat_schedule = {
    # Scientific loops — every 15 minutes
    "run-scientific-loops-every-15min": {
        "task": "backend.workers.tasks.scientific_tasks.run_all_scientific_loops",
        "schedule": settings.SCIENTIFIC_LOOP_INTERVAL_MINUTES * 60,
        "options": {"queue": "scientific"},
    },
    # Decision engine — every hour
    "run-decision-engine-every-hour": {
        "task": "backend.workers.tasks.scientific_tasks.run_decision_engine_all_lagoons",
        "schedule": settings.DECISION_ENGINE_INTERVAL_MINUTES * 60,
        "options": {"queue": "scientific"},
    },
    # Learning cycle — every 6 hours
    "run-learning-cycle-every-6h": {
        "task": "backend.workers.tasks.learning_tasks.run_learning_cycle_all_lagoons",
        "schedule": settings.LEARNING_CYCLE_INTERVAL_HOURS * 3600,
        "options": {"queue": "scientific"},
    },
    # Daily reports — 06:00 UTC
    "generate-daily-reports": {
        "task": "backend.workers.tasks.reporting_tasks.generate_all_daily_reports",
        "schedule": crontab(hour=6, minute=0),
        "options": {"queue": "reporting"},
    },
    # Weekly executive reports — Monday 07:00 UTC
    "generate-weekly-executive-reports": {
        "task": "backend.workers.tasks.reporting_tasks.generate_weekly_executive_reports",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),
        "options": {"queue": "reporting"},
    },
    # Sensor health check — every 30 minutes
    "check-sensor-health": {
        "task": "backend.workers.tasks.notification_tasks.check_sensor_health_all_lagoons",
        "schedule": 1800.0,
        "options": {"queue": "notifications"},
    },
}

# ── Worker concurrency ────────────────────────────────────────────────────────

worker_concurrency = 4  # default; override per worker with -c flag
worker_max_tasks_per_child = 100  # restart child process after N tasks (memory hygiene)
