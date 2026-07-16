"""Shared pytest fixtures. Tests run against SQLite in-memory by default.

Confirmed against your real files:
  - app.database.base.Base / TimestampMixin
  - app.models.company.Company (name, scanner, careers_url, active)

Still-unconfirmed (used per the assumptions documented in job_sync_service.py
and job_repository.py): Job, ScanHistory, Notification field names.

SQLite caveat: native Postgres ENUM types (job_status, scan_status) become
plain VARCHAR under SQLite — fine for these tests since we only assert on
Python-side enum values, not the underlying column type.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.base import Base
from app.models.company import Company

# Import all model modules so Base.metadata is fully populated before
# create_all() runs — otherwise tables that are only reachable via
# relationship() TYPE_CHECKING imports won't be created.
from app.models import job, notification, scan_history  # noqa: F401


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
        careers_url="https://acme.example.com/careers",
        scanner="workday",
        active=True,
    )
    session.add(c)
    session.flush()
    return c