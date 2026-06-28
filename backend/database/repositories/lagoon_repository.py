"""Lagoon repository — organisation-scoped lagoon data access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from backend.database.models import Lagoon
from backend.database.repositories.base import BaseRepository

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class LagoonRepository(BaseRepository[Lagoon]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Lagoon, session)

    async def get_by_slug(self, org_id: uuid.UUID, slug: str) -> Lagoon | None:
        """Fetch a lagoon by organisation + slug (unique composite key)."""
        result = await self.session.execute(
            select(Lagoon).where(Lagoon.org_id == org_id, Lagoon.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_org(
        self,
        org_id: uuid.UUID,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Lagoon]:
        """List all lagoons belonging to an organisation."""
        stmt = select(Lagoon).where(Lagoon.org_id == org_id)
        if active_only:
            stmt = stmt.where(Lagoon.is_active.is_(True))
        stmt = stmt.order_by(Lagoon.name.asc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_org(self, org_id: uuid.UUID, active_only: bool = True) -> int:
        """Count lagoons for an organisation."""
        return await self.count(
            filters={"org_id": org_id, **({"is_active": True} if active_only else {})}
        )

    async def update_operating_parameters(
        self, lagoon_id: uuid.UUID, parameters: dict[str, Any]
    ) -> Lagoon | None:
        """Merge new key-value pairs into the operating_parameters JSONB column."""
        lagoon = await self.get_by_id(lagoon_id)
        if lagoon is None:
            return None
        existing = dict(lagoon.operating_parameters or {})
        existing.update(parameters)
        return await self.update(lagoon_id, {"operating_parameters": existing})

    async def get_active_lagoon_ids(self, org_id: uuid.UUID) -> list[uuid.UUID]:
        """Return a list of active lagoon UUIDs for an organisation (lightweight)."""
        result = await self.session.execute(
            select(Lagoon.id).where(Lagoon.org_id == org_id, Lagoon.is_active.is_(True))
        )
        return [row[0] for row in result.all()]
