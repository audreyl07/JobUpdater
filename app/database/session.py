"""Database session management."""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base


class DatabaseSessionManager:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url)
        self._session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def create_tables(self) -> None:
        """Create all database tables."""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session_scope(self):
        """Provide a transactional session scope."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()