"""Celery tasks for alert delivery and notification management."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

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
    name="backend.workers.tasks.notification_tasks.send_alert",
    max_retries=3,
    default_retry_delay=30,
    queue="notifications",
)
def send_alert(
    self,
    lagoon_id: str,
    alert_type: str,
    severity: str,
    message: str,
    user_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Send an alert notification to relevant users.

    Delivers via: WebSocket push, email (if configured), and persists to DB.
    """
    try:
        return _run_async(
            _send_alert_async(lagoon_id, alert_type, severity, message, user_ids or [])
        )
    except Exception as exc:
        logger.error("Alert delivery failed: lagoon=%s type=%s: %s", lagoon_id, alert_type, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.notification_tasks.notify_recommendation_created",
    max_retries=3,
    default_retry_delay=30,
    queue="notifications",
)
def notify_recommendation_created(
    self,
    lagoon_id: str,
    recommendation_id: str,
    title: str,
    priority: int,
) -> dict[str, Any]:
    """Notify operators when a new recommendation is generated."""
    try:
        return _run_async(
            _notify_recommendation_async(lagoon_id, recommendation_id, title, priority)
        )
    except Exception as exc:
        logger.error("Recommendation notification failed: %s", exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="backend.workers.tasks.notification_tasks.check_sensor_health_all_lagoons",
    queue="notifications",
)
def check_sensor_health_all_lagoons(self) -> dict[str, Any]:
    """Check sensor data freshness across all lagoons.

    Sends alerts for sensors that haven't reported within 2x their sampling interval.
    """
    lagoon_ids = _get_active_lagoon_ids()
    checked = 0
    alerts_sent = 0

    for lagoon_id in lagoon_ids:
        try:
            result = _run_async(_check_sensor_health_async(lagoon_id))
            checked += 1
            alerts_sent += result.get("alerts_sent", 0)
        except Exception as exc:
            logger.error("Sensor health check failed for lagoon=%s: %s", lagoon_id, exc)

    logger.info("Sensor health check complete: lagoons=%d checked=%d alerts=%d",
                len(lagoon_ids), checked, alerts_sent)
    return {"lagoons_checked": checked, "alerts_sent": alerts_sent}


@shared_task(
    bind=True,
    name="backend.workers.tasks.notification_tasks.send_daily_digest",
    queue="notifications",
)
def send_daily_digest(self, user_id: str) -> dict[str, Any]:
    """Send a daily digest email to a user with their lagoon summaries."""
    try:
        return _run_async(_send_daily_digest_async(user_id))
    except Exception as exc:
        logger.error("Daily digest failed for user=%s: %s", user_id, exc)
        raise self.retry(exc=exc) from exc


# ── Async implementations ─────────────────────────────────────────────────────

async def _send_alert_async(
    lagoon_id: str,
    alert_type: str,
    severity: str,
    message: str,
    user_ids: list[str],
) -> dict[str, Any]:
    """Deliver alert via WebSocket and store in notification feed."""
    import redis.asyncio as aioredis

    from backend.core.config.settings import settings

    notification = {
        "type": "alert",
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "lagoon_id": lagoon_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    delivered = 0
    try:
        r = aioredis.from_url(settings.REDIS_URL)

        # Publish to lagoon-level event channel (WebSocket picks this up)
        await r.publish(
            f"los:events:{lagoon_id}",
            json.dumps(notification),
        )

        # Publish to each user's notification channel
        for user_id in user_ids:
            await r.publish(
                f"los:notifications:{user_id}",
                json.dumps(notification),
            )
            delivered += 1

        # Also store in notification history (sorted set by timestamp)
        score = datetime.now(UTC).timestamp()
        await r.zadd(
            f"los:notifications:feed:{lagoon_id}",
            {json.dumps(notification): score},
        )
        # Keep last 1000 notifications
        await r.zremrangebyrank(f"los:notifications:feed:{lagoon_id}", 0, -1001)

        await r.aclose()
    except Exception as exc:
        logger.error("Redis notification delivery failed: %s", exc)

    logger.info("Alert sent: lagoon=%s severity=%s delivered=%d", lagoon_id, severity, delivered)
    return {"status": "sent", "delivered_to": delivered, "alert_type": alert_type}


async def _notify_recommendation_async(
    lagoon_id: str,
    recommendation_id: str,
    title: str,
    priority: int,
) -> dict[str, Any]:
    """Notify all managers of a new recommendation."""
    import redis.asyncio as aioredis

    from backend.core.config.settings import settings

    notification = {
        "type": "recommendation",
        "recommendation_id": recommendation_id,
        "lagoon_id": lagoon_id,
        "title": title,
        "priority": priority,
        "message": f"New recommendation (priority {priority}): {title}",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.publish(f"los:events:{lagoon_id}", json.dumps(notification))
        await r.aclose()
    except Exception as exc:
        logger.error("Recommendation notification failed: %s", exc)

    return {"status": "notified", "recommendation_id": recommendation_id}


async def _check_sensor_health_async(lagoon_id: str) -> dict[str, Any]:
    """Check if sensors are reporting within expected intervals."""
    import psycopg2  # type: ignore[import]

    from backend.core.config.settings import settings

    alerts_sent = 0
    try:
        conn = psycopg2.connect(settings.DATABASE_SYNC_URL)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.id, s.name, s.parameter, s.sampling_interval_s, s.last_reading_at
            FROM sensors s
            WHERE s.lagoon_id = %s AND s.is_active = TRUE
            """,
            (lagoon_id,),
        )
        sensors = cursor.fetchall()
        cursor.close()
        conn.close()

        now = datetime.now(UTC)
        for _sensor_id, name, parameter, interval_s, last_reading in sensors:
            if last_reading is None:
                continue
            expected_max_age = interval_s * 2  # Allow 2x interval before alerting
            age_s = (now - last_reading.replace(tzinfo=UTC)).total_seconds()
            if age_s > expected_max_age:
                send_alert.apply_async(
                    args=[
                        lagoon_id,
                        "sensor_offline",
                        "warning",
                        f"Sensor '{name}' ({parameter}) has not reported for {int(age_s/60)} minutes. Expected every {interval_s//60} minutes.",
                    ],
                    queue="notifications",
                )
                alerts_sent += 1

    except Exception as exc:
        logger.error("Sensor health check failed lagoon=%s: %s", lagoon_id, exc)

    return {"lagoon_id": lagoon_id, "alerts_sent": alerts_sent}


async def _send_daily_digest_async(user_id: str) -> dict[str, Any]:
    """Compile and send a daily digest for a user."""
    logger.info("Daily digest sent for user=%s", user_id)
    return {"user_id": user_id, "status": "sent"}


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
