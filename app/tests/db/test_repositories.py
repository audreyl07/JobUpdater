"""Tests for job duplicate detection in the repository layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.db.models import Base, JobRecord
from app.db.repositories import JobRepository
from app.db.session import DatabaseSessionManager


@dataclass
class FakeJob:
    """Test double for a job object."""

    job_id: str
    company: str
    title: str
    location: str = "Toronto"
    url: str = "https://example.com/jobs/1"
    description: str = "Python role"
    employment_type: str = "full-time"
    remote: bool = True
    source: str = "workday"
    posted_at: object | None = None


def _manager(tmp_path: Path) -> DatabaseSessionManager:
    database_path = tmp_path / "jobs.db"
    return DatabaseSessionManager(f"sqlite+pysqlite:///{database_path.as_posix()}")


def test_save_new_job_marks_as_new(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.create_tables()

    with manager.session_scope() as session:
        repo = JobRepository(session)
        result = repo.save(FakeJob(job_id="job-1", company="Nokia", title="Software Engineer"))

        assert result.is_new is True
        assert result.record.job_id == "job-1"
        assert result.record.company == "Nokia"

    with manager.session_scope() as session:
        rows = session.execute(select(JobRecord)).scalars().all()
        assert len(rows) == 1
        assert rows[0].job_id == "job-1"


def test_save_duplicate_job_returns_existing_record(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.create_tables()

    with manager.session_scope() as session:
        repo = JobRepository(session)

        first = repo.save(FakeJob(job_id="job-1", company="Nokia", title="Software Engineer"))
        second = repo.save(FakeJob(job_id="job-1", company="Nokia", title="Software Engineer"))

        assert first.is_new is True
        assert second.is_new is False
        assert first.record.id == second.record.id

    with manager.session_scope() as session:
        rows = session.execute(select(JobRecord)).scalars().all()
        assert len(rows) == 1