"""Tests for database session management."""

from __future__ import annotations

from app.db.models import Base
from app.db.session import DatabaseSessionManager


def test_session_manager_creates_tables() -> None:
    manager = DatabaseSessionManager("sqlite+pysqlite:///:memory:")
    manager.create_tables()

    assert Base.metadata.tables["jobs"].name == "jobs"
    assert Base.metadata.tables["scan_history"].name == "scan_history"