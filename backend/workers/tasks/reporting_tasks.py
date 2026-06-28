"""Celery tasks for scheduled and on-demand report generation."""
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
    name="backend.workers.tasks.reporting_tasks.generate_all_daily_reports",
    queue="reporting",
)
def generate_all_daily_reports(self) -> dict[str, Any]:
    """Generate operational + compliance daily reports for all active lagoons."""
    lagoon_ids = _get_active_lagoon_ids()
    generated = 0
    errors = 0

    for lagoon_id in lagoon_ids:
        for report_type in ("operational", "compliance"):
            try:
                generate_lagoon_report.apply_async(
                    args=[lagoon_id, report_type, 1],
                    queue="reporting",
                )
                generated += 1
            except Exception as exc:
                logger.error("Failed to dispatch report for lagoon=%s type=%s: %s",
                             lagoon_id, report_type, exc)
                errors += 1

    logger.info("Daily reports dispatched: lagoons=%d reports=%d errors=%d",
                len(lagoon_ids), generated, errors)
    return {"lagoons": len(lagoon_ids), "dispatched": generated, "errors": errors}


@shared_task(
    bind=True,
    name="backend.workers.tasks.reporting_tasks.generate_weekly_executive_reports",
    queue="reporting",
)
def generate_weekly_executive_reports(self) -> dict[str, Any]:
    """Generate weekly executive reports for all active lagoons."""
    lagoon_ids = _get_active_lagoon_ids()
    generated = 0
    errors = 0

    for lagoon_id in lagoon_ids:
        try:
            generate_lagoon_report.apply_async(
                args=[lagoon_id, "executive", 7],
                queue="reporting",
            )
            generated += 1
        except Exception as exc:
            logger.error("Failed to dispatch executive report for lagoon=%s: %s", lagoon_id, exc)
            errors += 1

    return {"lagoons": len(lagoon_ids), "dispatched": generated, "errors": errors}


@shared_task(
    bind=True,
    name="backend.workers.tasks.reporting_tasks.generate_lagoon_report",
    max_retries=2,
    default_retry_delay=300,
    queue="reporting",
)
def generate_lagoon_report(
    self,
    lagoon_id: str,
    report_type: str,
    period_days: int,
) -> dict[str, Any]:
    """Generate and persist a single lagoon report.

    Stores the report content in the database for retrieval via the API.
    """
    try:
        return _run_async(_generate_and_store_report(lagoon_id, report_type, period_days))
    except Exception as exc:
        logger.error("Report generation failed: lagoon=%s type=%s error=%s",
                     lagoon_id, report_type, exc)
        raise self.retry(exc=exc) from exc


async def _generate_and_store_report(
    lagoon_id: str,
    report_type: str,
    period_days: int,
) -> dict[str, Any]:
    """Generate report content and write to the reports table."""
    from datetime import datetime

    from backend.application.services.report_service import ReportService
    from backend.database.repositories.report_data_provider import (
        DBReportDataProvider,  # type: ignore[import]
    )
    from backend.database.session import AsyncSessionLocal  # type: ignore[import]

    async with AsyncSessionLocal() as db:
        provider = DBReportDataProvider(db)
        svc = ReportService(provider)

        generators = {
            "executive": svc.generate_executive_report,
            "scientific": svc.generate_scientific_report,
            "compliance": svc.generate_compliance_report,
            "operational": svc.generate_operational_report,
        }

        generator = generators.get(report_type)
        if generator is None:
            raise ValueError(f"Unknown report type: {report_type}")

        content = await generator(lagoon_id=UUID(lagoon_id), period_days=period_days)

        # Persist the report
        from uuid import uuid4

        from backend.database.repositories.report_repo import (
            ReportRepository,  # type: ignore[import]
        )

        repo = ReportRepository(db)
        report_record = {
            "id": str(uuid4()),
            "lagoon_id": lagoon_id,
            "report_type": report_type,
            "period_days": period_days,
            "format": "markdown",
            "content": content,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        await repo.create(report_record)
        await db.commit()

    logger.info("Report generated and stored: lagoon=%s type=%s period=%d",
                lagoon_id, report_type, period_days)
    return {
        "lagoon_id": lagoon_id,
        "report_type": report_type,
        "period_days": period_days,
        "status": "complete",
        "content_length": len(content),
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
