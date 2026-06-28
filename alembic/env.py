"""Alembic environment configuration for the Lagoons Operating System.

Uses async SQLAlchemy engine for online migrations and synchronous psycopg2
driver for offline SQL generation.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Import Base so all ORM models are registered in metadata.
from backend.database.connection import Base
import backend.database.models  # noqa: F401 — registers all ORM models with Base

# Alembic Config object (gives access to alembic.ini values).
config = context.config

# Set up Python logging from alembic.ini [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata used for autogenerate support.
target_metadata = Base.metadata


def _get_database_url() -> str:
    """Resolve the sync database URL for migrations.

    Reads DATABASE_URL from the environment and converts asyncpg → psycopg2
    so that Alembic can use the synchronous driver.
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        # Fall back to individual components.
        user = os.environ.get("POSTGRES_USER", "los")
        password = os.environ.get("POSTGRES_PASSWORD", "los")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ.get("POSTGRES_DB", "los")
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    # Convert async driver to sync driver.
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://").replace(
        "postgresql://", "postgresql+psycopg2://"
    )


def run_migrations_offline() -> None:
    """Generate SQL without connecting to the database.

    Used for reviewing migrations before applying them to production.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=True,
            render_as_batch=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
