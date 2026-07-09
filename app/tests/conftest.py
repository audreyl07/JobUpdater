"""Shared pytest fixtures. Tests run against SQLite in-memory by default.

ASSUMPTIONS (adjust import paths if your layout differs):
  - app.db.base.Base is the declarative base.
  - app.models.company.Company, app.models.job.Job / JobStatus,
    app.models.scan_history.ScanHistory / ScanStatus,
    app.models.notification.Notification exist and are importable
    (they're in your "already implemented" list).

SQLite caveat: native Postgres ENUM types (job_status, scan_status) become
plain VARCHAR under SQLite — fine for these tests since we only assert on
Python-side enum values, not the underlying column type.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.company import Company


@pytest.fixture()
def engine():
    """Fresh in-memory SQLite engine per test — no state leaks between tests."""
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def session(engine) -> Session:
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with factory() as sess:
        yield sess
        sess.rollback()


@pytest.fixture()
def company(session) -> Company:
    """A minimal persisted company row for tests that need a company_id."""
    c = Company(
        name="Acme Corp",
        career_site_url="https://acme.example.com/careers",
        scanner_type="workday",
        is_active=True,
    )
    session.add(c)
    session.flush()
    return c