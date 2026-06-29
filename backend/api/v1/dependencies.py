"""FastAPI dependency injection for the LOS API.

All shared resources (DB sessions, current user, event bus) are
resolved here and injected via Depends().
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.settings import settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

# ── OAuth2 scheme ─────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Database ──────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session and close it after the request."""
    # Import here to avoid circular imports at module load time
    from backend.database.connection import AsyncSessionLocal  # type: ignore[import]

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


DatabaseDep = Annotated[AsyncSession, Depends(get_db)]


# ── Event bus ─────────────────────────────────────────────────────────────────

async def get_event_bus() -> object:
    """Return the application-scoped event bus singleton (Redis Streams)."""
    from backend.event_bus.bus import event_bus  # type: ignore[import]

    return event_bus


EventBusDep = Annotated[object, Depends(get_event_bus)]


# ── Shared memory ─────────────────────────────────────────────────────────────

_redis_client: object | None = None


async def get_shared_memory() -> object:
    """Return a SharedMemoryService backed by the application Redis connection."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis  # type: ignore[import]

        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
        )

    from backend.shared_memory.service import SharedMemoryService  # type: ignore[import]

    return SharedMemoryService(redis_client=_redis_client)


SharedMemoryDep = Annotated[object, Depends(get_shared_memory)]


# ── Authentication ────────────────────────────────────────────────────────────

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DatabaseDep,
) -> dict:
    """Decode and validate the JWT, return the user record.

    Raises HTTP 401 if the token is invalid or the user is not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    # Attempt to load user from DB
    try:
        from backend.database.repositories.user_repo import UserRepository  # type: ignore[import]

        repo = UserRepository(db)
        user = await repo.get(UUID(user_id))
        if user is None:
            raise credentials_exception
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )
        return user
    except (ValueError, Exception) as exc:
        logger.warning("get_current_user failed: %s", exc)
        raise credentials_exception from exc


CurrentUserDep = Annotated[dict, Depends(get_current_user)]


async def get_current_active_user(current_user: CurrentUserDep) -> dict:
    """Alias that makes the dependency chain explicit."""
    return current_user


# ── RBAC ─────────────────────────────────────────────────────────────────────

ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "operator": 2,
    "scientist": 3,
    "manager": 4,
    "admin": 5,
}


def require_role(minimum_role: str):  # type: ignore[no-untyped-def]
    """Dependency factory: raise 403 if the user's role is below minimum_role."""

    async def _check(current_user: CurrentUserDep) -> dict:
        user_role = current_user.get("role", "viewer").lower()
        required_level = ROLE_HIERARCHY.get(minimum_role.lower(), 99)
        user_level = ROLE_HIERARCHY.get(user_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires role '{minimum_role}' or above. "
                f"Your role: '{user_role}'.",
            )
        return current_user

    return _check


# ── Pagination ────────────────────────────────────────────────────────────────

class PaginationParams:
    """Common query-string pagination parameters."""

    def __init__(
        self,
        skip: int = Query(default=0, ge=0, description="Number of items to skip"),
        limit: int = Query(default=50, ge=1, le=500, description="Maximum items to return"),
    ) -> None:
        self.skip = skip
        self.limit = limit


def paginate(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> PaginationParams:
    """Resolve pagination query parameters."""
    p = PaginationParams.__new__(PaginationParams)
    p.skip = skip
    p.limit = limit
    return p


PaginationDep = Annotated[PaginationParams, Depends(paginate)]


# ── Org scoping ───────────────────────────────────────────────────────────────

async def get_org_id(current_user: CurrentUserDep) -> UUID:
    """Extract the organisation ID from the authenticated user.

    Raises 400 if the user has no org assigned (system users, fresh accounts).
    """
    org_id = current_user.get("org_id")
    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with an organisation.",
        )
    return UUID(str(org_id)) if not isinstance(org_id, UUID) else org_id


OrgDep = Annotated[UUID, Depends(get_org_id)]
