"""User repository — authentication-aware user data access."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from backend.database.models import User
from backend.database.repositories.base import BaseRepository

try:
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError:
    pass  # type: ignore[assignment]


def _to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "org_id": user.org_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "last_login": user.last_login,
        "preferences": user.preferences,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        user = await self.get_by_id(user_id)
        return _to_dict(user) if user is not None else None

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        return _to_dict(user) if user is not None else None

    async def get_by_email_for_auth(self, email: str) -> dict[str, Any] | None:
        """Return user dict including hashed_password for authentication only."""
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        d = _to_dict(user)
        d["hashed_password"] = user.hashed_password
        return d

    async def get_with_password(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Return user dict including hashed_password for password change flow."""
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        d = _to_dict(user)
        d["hashed_password"] = user.hashed_password
        return d

    async def list(self, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        users = await super().list(skip=skip, limit=limit)
        return [_to_dict(u) for u in users]

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        user = await super().create(data)
        return _to_dict(user)

    async def update(self, user_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        user = await super().update(user_id, data)
        return _to_dict(user) if user is not None else None
