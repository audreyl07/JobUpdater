"""Alembic migration environment for JobUpdater.

Wires Alembic to the SQLAlchemy `Base` metadata and to the same
DATABASE_URL validation used by the application at runtime (app.database.engine),
so a migration can never run against an invalidated or malformed URL, and
never logs raw credentials.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the project root (parent of this alembic/ dir) is on sys.path
# so `app` can be imported regardless of the current working directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.base import Base  # noqa: E402
from app.database.engine import DatabaseSettings  # noqa: E402

# Import all model modules so Base.metadata is fully populated for autogenerate.
from app.models import company, job, notification, scan_history  # noqa: F401, E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata


def _resolve_database_url() -> str:
    """Fetch and validate DATABASE_URL using the app's own DatabaseSettings.

    Reusing DatabaseSettings.from_env() (rather than reimplementing the
    validation here) guarantees migrations and the running app can never
    disagree about what a valid URL looks like, and reuses the app's own
    credential redaction for logging.
    """
    settings = DatabaseSettings.from_env()
    logger.info("Alembic using database: %s", settings.redacted_url())
    return settings.url


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection, emitting raw SQL."""
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _resolve_database_url()

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
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()