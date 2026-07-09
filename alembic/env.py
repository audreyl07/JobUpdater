"""Alembic migration environment for JobUpdater.

Wires Alembic to the SQLAlchemy `Base` metadata and to the same
`DATABASE_URL` validation used by the application at runtime, so a
migration can never run against an unvalidated or malformed URL.

ASSUMPTIONS (adjust imports if your actual module layout differs):
  - app.db.engine exposes `get_validated_database_url() -> str`, which
    performs the same eager validation described in the spec (must start
    with "postgresql+psycopg://", raises on malformed URLs). This is the
    "already implemented" engine.py from your project.
  - app.db.base exposes `Base` (the declarative base all models inherit).
  - Models are imported here purely for their side effect of registering
    tables on `Base.metadata` — required for `alembic revision --autogenerate`
    to see them.

If your engine.py's validation function has a different name/location,
tell me and I'll adjust the import.
"""

from __future__ import annotations

import logging
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- Import Base and all models so Base.metadata is fully populated -----
from app.db.base import Base  # noqa: E402
from app.db.engine import get_validated_database_url  # noqa: E402
from app.models import company, job, notification, scan_history  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata


def _redact(url: str) -> str:
    """Strip credentials from a DB URL before it ever touches a log line."""
    return re.sub(r"(postgresql\+psycopg://)[^@/]+@", r"\1***:***@", url)


def _resolve_database_url() -> str:
    """Fetch and validate DATABASE_URL using the app's own validation logic.

    Reusing get_validated_database_url() (rather than re-implementing the
    "postgresql+psycopg://" check here) guarantees migrations and the
    running app can never disagree about what a valid URL looks like.
    """
    url = get_validated_database_url()
    logger.info("Alembic using database: %s", _redact(url))
    return url


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