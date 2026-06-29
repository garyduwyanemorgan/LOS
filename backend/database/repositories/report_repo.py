"""ReportRepository — in-process store; reports generated on demand and cached in memory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Module-level in-memory store keyed by lagoon_id string, newest first.
_REPORT_STORE: dict[str, list[dict[str, Any]]] = {}


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Persist report in the in-process store and return with generated id/created_at."""
        report = dict(data)
        if "id" not in report or report["id"] is None:
            report["id"] = str(uuid.uuid4())
        if "created_at" not in report or report["created_at"] is None:
            report["created_at"] = datetime.now(tz=UTC).isoformat()

        lagoon_key = str(report.get("lagoon_id", ""))
        if lagoon_key:
            if lagoon_key not in _REPORT_STORE:
                _REPORT_STORE[lagoon_key] = []
            _REPORT_STORE[lagoon_key].insert(0, report)  # newest first

        return report

    async def list(self, lagoon_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return all stored reports for a lagoon, newest first."""
        return list(_REPORT_STORE.get(str(lagoon_id), []))

    async def get(self, report_id: uuid.UUID, lagoon_id: uuid.UUID) -> dict[str, Any] | None:
        """Find a specific report by id within a lagoon's store."""
        rid = str(report_id)
        for report in _REPORT_STORE.get(str(lagoon_id), []):
            if str(report.get("id")) == rid:
                return report
        return None

    async def get_latest(self, lagoon_id: uuid.UUID, report_type: str) -> dict[str, Any] | None:
        """Return the most recent stored report of a given type for a lagoon."""
        for report in _REPORT_STORE.get(str(lagoon_id), []):
            if report.get("report_type") == report_type:
                return report
        return None
