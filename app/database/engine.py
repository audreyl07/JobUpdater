from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.utils.logger import get_logger

logger = get_logger(__name__)

POSTGRESQL_PSYCOPG_PREFIX = "postgresql+psycopg://"
SQLITE_PREFIXES = ("sqlite://", "sqlite+pysqlite://")


class DatabaseConfigurationError(ValueError):
    """Raised when DATABASE_URL is missing or malformed."""


class DatabaseConnectionError(RuntimeError):
    """Raised when the database engine cannot be created or validated."""


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Validated database connection settings."""

    url: str

    @classmethod
    def from_env(cls, env_var: str = "DATABASE_URL") -> DatabaseSettings:
        raw_value = os.getenv(env_var)
        if raw_value is None or not raw_value.strip():
            raise DatabaseConfigurationError(
                f"{env_var} is not set. Expected a PostgreSQL URL like "
                f'"{POSTGRESQL_PSYCOPG_PREFIX}user:password@localhost/career_monitor".'
            )

        return cls(url=validate_database_url(raw_value.strip()))

    def redacted_url(self) -> str:
        return redact_database_url(self.url)


def validate_database_url(database_url: str) -> str:
    """
    Validate and normalize the database URL.

    Production requires PostgreSQL via psycopg3. SQLite is allowed for tests.
    """
    if not database_url:
        raise DatabaseConfigurationError("DATABASE_URL is empty.")

    if database_url.startswith(SQLITE_PREFIXES):
        return database_url

    if not database_url.startswith(POSTGRESQL_PSYCOPG_PREFIX):
        raise DatabaseConfigurationError(
            "DATABASE_URL must start with "
            f'"{POSTGRESQL_PSYCOPG_PREFIX}". '
            "Do not use bare 'postgresql://' or 'postgres://' URLs."
        )

    try:
        url = make_url(database_url)
    except Exception as exc:  # SQLAlchemy URL parsing raises ValueError-like errors
        raise DatabaseConfigurationError(
            "DATABASE_URL is malformed. Expected format: "
            f'"{POSTGRESQL_PSYCOPG_PREFIX}user:password@host:5432/database".'
        ) from exc

    if url.drivername != "postgresql+psycopg":
        raise DatabaseConfigurationError(
            "DATABASE_URL must use the psycopg driver: "
            f'"{POSTGRESQL_PSYCOPG_PREFIX}..."'
        )

    if not url.host:
        raise DatabaseConfigurationError("DATABASE_URL is missing a host.")
    if not url.database:
        raise DatabaseConfigurationError("DATABASE_URL is missing a database name.")

    return str(url)


def redact_database_url(database_url: str) -> str:
    """Redact credentials before logging."""
    try:
        url = make_url(database_url)
    except Exception:
        return "<invalid-database-url>"

    if url.password is not None:
        url = url.set(password="***")
    return str(url)


def create_database_engine(
    database_url: str,
    *,
    echo: bool = False,
    connect_args: dict[str, Any] | None = None,
) -> Engine:
    """
    Create a SQLAlchemy engine after validating the connection URL.

    Raises:
        DatabaseConfigurationError: invalid URL or unsupported scheme.
        DatabaseConnectionError: engine creation failure.
    """
    validated_url = validate_database_url(database_url)

    engine_kwargs: dict[str, Any] = {
        "echo": echo,
        "future": True,
        "pool_pre_ping": True,
    }

    if connect_args:
        engine_kwargs["connect_args"] = connect_args

    try:
        engine = create_engine(validated_url, **engine_kwargs)
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(
            f"Failed to create database engine for {redact_database_url(validated_url)}"
        ) from exc

    logger.info("Database engine created for %s", redact_database_url(validated_url))
    return engine


def create_database_engine_from_env(
    env_var: str = "DATABASE_URL",
    *,
    echo: bool = False,
) -> Engine:
    """Read DATABASE_URL from the environment and create an engine."""
    settings = DatabaseSettings.from_env(env_var=env_var)
    return create_database_engine(settings.url, echo=echo)