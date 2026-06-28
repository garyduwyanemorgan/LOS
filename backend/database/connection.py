"""SQLAlchemy async engine and session factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.core.config.settings import settings
from backend.core.logging.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

log = get_logger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    Using a single base ensures that all models are registered in the same
    metadata registry, which is required for Alembic auto-generation.
    """
    pass


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=True,  # verify connections before use
    echo=settings.DEBUG,
    echo_pool=settings.DEBUG,
    future=True,
)


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession as a FastAPI dependency.

    The session is automatically committed on success and rolled back on
    any exception, then closed in the finally block.

    Usage in a router::

        @router.get("/lagoons")
        async def list_lagoons(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Verify the database connection and log the server version.

    This is called once at application startup.  Table creation is handled
    by Alembic migrations, not by this function.
    """
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            log.info("database-connected", postgres_version=version)

            # Verify PostGIS is installed.
            postgis_result = await conn.execute(text("SELECT PostGIS_Version()"))
            postgis_version = postgis_result.scalar()
            log.info("postgis-available", postgis_version=postgis_version)
    except Exception as exc:
        log.error("database-init-failed", error=str(exc))
        raise


async def check_db_health() -> dict[str, str | bool]:
    """Health check — returns connection status for use in /health endpoint."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "connected": True}
    except Exception as exc:
        return {"status": "unhealthy", "connected": False, "error": str(exc)}


async def close_db() -> None:
    """Dispose of all engine connections.  Call at application shutdown."""
    await engine.dispose()
    log.info("database-connections-closed")
