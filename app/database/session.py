from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database.engine import DatabaseConnectionError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseTransactionError(RuntimeError):
    """Raised when a transactional database operation fails."""


@dataclass(frozen=True, slots=True)
class SessionFactory:
    """Factory for SQLAlchemy sessions bound to a specific engine."""

    engine: Engine

    def create(self) -> sessionmaker[Session]:
        return sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """
    Provide a transactional scope around a series of operations.

    Commits on success, rolls back on failure, and always closes the session.
    """
    factory = SessionFactory(engine).create()
    session = factory()

    try:
        yield session
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Database transaction failed; rolled back changes.")
        raise DatabaseTransactionError("Database transaction failed.") from exc
    except Exception:
        session.rollback()
        logger.exception("Unexpected failure during database transaction; rolled back changes.")
        raise
    finally:
        session.close()


def validate_engine(engine: Engine) -> None:
    """Fail fast if the engine cannot connect."""
    try:
        with engine.connect() as connection:
            connection.execute("SELECT 1")
    except Exception as exc:
        raise DatabaseConnectionError("Database connection validation failed.") from exc