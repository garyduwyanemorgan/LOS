"""ReportRepository — MVP: no DB storage; reports are generated on demand."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return data with a generated id and created_at; no DB write for MVP."""
        report = dict(data)
        if "id" not in report or report["id"] is None:
            report["id"] = str(uuid.uuid4())
        if "created_at" not in report or report["created_at"] is None:
            report["created_at"] = datetime.now(tz=UTC).isoformat()
        return report

    async def get(self, report_id: uuid.UUID, lagoon_id: uuid.UUID) -> dict[str, Any] | None:
        """No persistent storage for MVP — always returns None."""
        return None
