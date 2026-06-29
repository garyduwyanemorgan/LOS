"""Report generation and retrieval endpoints."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse

from backend.api.v1.dependencies import (
    CurrentUserDep,
    DatabaseDep,
    require_role,
)
from backend.api.v1.schemas import ReportRequest, ReportResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lagoons/{lagoon_id}/reports", tags=["Reports"])


def _get_service(db: DatabaseDep):
    from backend.application.services.report_service import ReportService
    from backend.database.repositories.report_data_provider import (
        DBReportDataProvider,  # type: ignore[import]
    )

    provider = DBReportDataProvider(db)
    return ReportService(provider)


@router.get(
    "",
    summary="List generated reports for a lagoon",
)
async def list_reports(
    lagoon_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
) -> list:
    """Return all previously generated reports for this lagoon, newest first."""
    from backend.database.repositories.report_repo import ReportRepository  # type: ignore[import]

    repo = ReportRepository(db)
    return await repo.list(lagoon_id)


@router.post(
    "",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a report",
)
async def generate_report(
    body: ReportRequest,
    lagoon_id: UUID = Path(...),
    current_user: CurrentUserDep = ...,
    db: DatabaseDep = ...,
    _: dict = Depends(require_role("operator")),
) -> ReportResponse:
    """Generate a report of the specified type and return the content.

    Supported types: executive, scientific, compliance, operational.
    Formats: markdown, html (rendered from markdown).
    """
    svc = _get_service(db)

    generators = {
        "executive": svc.generate_executive_report,
        "scientific": svc.generate_scientific_report,
        "compliance": svc.generate_compliance_report,
        "operational": svc.generate_operational_report,
    }

    generator = generators.get(body.report_type)
    if generator is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown report type: {body.report_type}",
        )

    try:
        content = await generator(lagoon_id=lagoon_id, period_days=body.period_days)
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report generation failed. Check logs for details.",
        ) from exc

    if body.format == "html":
        try:
            import markdown

            content = markdown.markdown(content, extensions=["tables", "fenced_code"])
        except ImportError:
            # markdown package optional — fall back to raw
            logger.warning("markdown package not installed; returning raw Markdown")

    # Persist so the list endpoint can return it
    from backend.database.repositories.report_repo import ReportRepository  # type: ignore[import]

    repo = ReportRepository(db)
    now = datetime.now(UTC)
    saved = await repo.create({
        "lagoon_id": str(lagoon_id),
        "report_type": body.report_type,
        "period_days": body.period_days,
        "format": body.format,
        "content": content,
        "status": "completed",
        "generated_at": now.isoformat(),
        "generated_by": str(current_user["id"]),
    })

    return ReportResponse(
        id=UUID(saved["id"]),
        lagoon_id=lagoon_id,
        report_type=body.report_type,
        period_days=body.period_days,
        format=body.format,
        content=content,
        generated_at=now,
        generated_by=UUID(str(current_user["id"])),
    )


@router.get(
    "/{report_type}/latest",
    summary="Download most recent cached report",
    response_model=None,
)
async def get_latest_report(
    lagoon_id: UUID = Path(...),
    report_type: str = Path(pattern="^(executive|scientific|compliance|operational)$"),
    format: str = Query(default="markdown", pattern="^(markdown|html)$"),
    db: DatabaseDep = ...,
) -> PlainTextResponse | HTMLResponse:
    """Return the latest cached report for this lagoon and type."""
    from backend.database.repositories.report_repo import ReportRepository  # type: ignore[import]

    repo = ReportRepository(db)
    report = await repo.get_latest(lagoon_id, report_type)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {report_type} report found for this lagoon. Generate one first.",
        )

    content = report.get("content", "")
    if format == "html":
        try:
            import markdown

            content = markdown.markdown(content, extensions=["tables", "fenced_code"])
            return HTMLResponse(content=content)
        except ImportError:
            pass

    return PlainTextResponse(content=content, media_type="text/markdown")
