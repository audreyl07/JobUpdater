"""Database repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from logging import Logger, getLogger
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import JobRecord, ScanHistoryRecord


class RepositoryError(Exception):
    """Raised when a repository operation fails."""


@dataclass(frozen=True, slots=True)
class JobSaveResult:
    """Result returned when saving a job."""

    record: JobRecord
    is_new: bool


class JobRepository:
    """Repository for job persistence and duplicate detection."""

    def __init__(self, session: Session, logger: Logger | None = None) -> None:
        self.session = session
        self.logger = logger or getLogger(__name__)

    def save(self, job: object) -> JobSaveResult:
        """Save a job if it does not already exist.

        If a job with the same job_id already exists, return the existing record
        and mark it as not new.
        """
        job_id = self._get_required_text(job, "job_id")

        existing = self.get_by_job_id(job_id)
        if existing is not None:
            return JobSaveResult(record=existing, is_new=False)

        payload = self._serialize_payload(job)
        record = JobRecord(**payload)

        try:
            self.session.add(record)
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            existing = self.get_by_job_id(job_id)
            if existing is not None:
                return JobSaveResult(record=existing, is_new=False)
            raise RepositoryError(f"Failed to save job {job_id}") from exc
        except Exception as exc:
            self.session.rollback()
            raise RepositoryError(f"Failed to save job {job_id}") from exc

        self.logger.info(
            "new_job_saved",
            extra={"job_id": record.job_id, "company": record.company, "is_new": True},
        )
        return JobSaveResult(record=record, is_new=True)

    def get_by_job_id(self, job_id: str) -> JobRecord | None:
        """Return a job record by job_id, or None if missing."""
        statement = select(JobRecord).where(JobRecord.job_id == job_id)
        return self.session.execute(statement).scalar_one_or_none()

    def _serialize_payload(self, job: object) -> dict[str, Any]:
        payload = {
            "job_id": self._get_required_text(job, "job_id"),
            "company": self._get_required_text(job, "company"),
            "title": self._get_required_text(job, "title"),
            "location": self._get_optional_text(job, "location"),
            "url": self._get_optional_text(job, "url"),
            "description": self._get_optional_text(job, "description"),
            "employment_type": self._get_optional_text(job, "employment_type"),
            "remote": self._get_optional_bool(job, "remote"),
            "source": self._get_optional_text(job, "source"),
            "posted_at": self._get_optional_datetime(job, "posted_at"),
        }
        payload["payload"] = {
            key: value for key, value in payload.items()
        }
        return payload

    def _get_required_text(self, job: object, field_name: str) -> str:
        value = getattr(job, field_name, None)
        if not isinstance(value, str) or not value.strip():
            raise RepositoryError(f"Missing required field: {field_name}")
        return value.strip()

    def _get_optional_text(self, job: object, field_name: str) -> str | None:
        value = getattr(job, field_name, None)
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value)

    def _get_optional_bool(self, job: object, field_name: str) -> bool | None:
        value = getattr(job, field_name, None)
        if value is None:
            return None
        return bool(value)

    def _get_optional_datetime(self, job: object, field_name: str) -> datetime | None:
        value = getattr(job, field_name, None)
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return None


@dataclass(frozen=True, slots=True)
class ScanHistorySaveResult:
    """Result returned when saving a scan history record."""

    record: ScanHistoryRecord
    is_new: bool


class ScanHistoryRepository:
    """Repository for scan history records."""

    def __init__(self, session: Session, logger: Logger | None = None) -> None:
        self.session = session
        self.logger = logger or getLogger(__name__)

    def add(self, history: object) -> ScanHistorySaveResult:
        payload = self._serialize_payload(history)
        record = ScanHistoryRecord(**payload)

        try:
            self.session.add(record)
            self.session.flush()
        except Exception as exc:
            self.session.rollback()
            raise RepositoryError("Failed to save scan history") from exc

        return ScanHistorySaveResult(record=record, is_new=True)

    def list(self) -> list[ScanHistoryRecord]:
        statement = select(ScanHistoryRecord).order_by(ScanHistoryRecord.id.asc())
        return list(self.session.execute(statement).scalars().all())

    def _serialize_payload(self, history: object) -> dict[str, Any]:
        company = getattr(history, "company", None)
        scanner = getattr(history, "scanner", None)
        if not isinstance(company, str) or not company.strip():
            raise RepositoryError("Missing required field: company")
        if not isinstance(scanner, str) or not scanner.strip():
            raise RepositoryError("Missing required field: scanner")

        started_at = getattr(history, "started_at", None)
        if started_at is None:
            started_at = datetime.now(timezone.utc)
        elif isinstance(started_at, datetime) and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        completed_at = getattr(history, "completed_at", None)
        if isinstance(completed_at, datetime) and completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)

        return {
            "company": company.strip(),
            "scanner": scanner.strip(),
            "started_at": started_at,
            "completed_at": completed_at,
            "jobs_found": int(getattr(history, "jobs_found", 0) or 0),
            "jobs_filtered": int(getattr(history, "jobs_filtered", 0) or 0),
            "status": str(getattr(history, "status", "running") or "running"),
            "error_message": self._optional_text(getattr(history, "error_message", None)),
        }

    def _optional_text(self, value: object | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value)