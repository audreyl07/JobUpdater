"""Database repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from logging import Logger, getLogger
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.exceptions import RepositoryError
from app.database.models import Company, JobRecord, ScanHistoryRecord


@dataclass(frozen=True, slots=True)
class CompanySaveResult:
    """Result returned when getting or creating a company."""

    record: Company
    is_new: bool


class CompanyRepository:
    """Repository for company get-or-create lookups."""

    def __init__(self, session: Session, logger: Logger | None = None) -> None:
        self.session = session
        self.logger = logger or getLogger(__name__)

    def get_by_name(self, name: str) -> Company | None:
        statement = select(Company).where(Company.name == name)
        return self.session.execute(statement).scalar_one_or_none()

    def get_or_create(self, name: str, careers_url: str, scanner: str) -> CompanySaveResult:
        existing = self.get_by_name(name)
        if existing is not None:
            return CompanySaveResult(record=existing, is_new=False)

        record = Company(
            name=name,
            careers_url=careers_url,
            scanner=scanner,
            active=True,
        )

        try:
            self.session.add(record)
            self.session.flush()  # assigns record.id without ending the transaction
        except IntegrityError as exc:
            self.session.rollback()
            existing = self.get_by_name(name)
            if existing is not None:
                return CompanySaveResult(record=existing, is_new=False)
            raise RepositoryError(f"Failed to save company {name}") from exc
        except Exception as exc:
            self.session.rollback()
            raise RepositoryError(f"Failed to save company {name}") from exc

        return CompanySaveResult(record=record, is_new=True)


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

    def save(self, job: object, company_id: int) -> JobSaveResult:
        job_id = self._get_required_text(job, "job_id")
        existing = self.get_by_job_id(company_id, job_id)

        now = datetime.now(timezone.utc)

        if existing is not None:
            # Seen again on this scan — refresh last_seen so we can tell
            # active postings from ones that have stopped appearing.
            existing.last_seen = now
            try:
                self.session.flush()
            except Exception as exc:
                self.session.rollback()
                raise RepositoryError(f"Failed to update job {job_id}") from exc
            return JobSaveResult(record=existing, is_new=False)

        payload = self._serialize_payload(job, company_id=company_id, timestamp=now)
        record = JobRecord(**payload)

        try:
            self.session.add(record)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            existing = self.get_by_job_id(company_id, job_id)
            if existing is not None:
                return JobSaveResult(record=existing, is_new=False)
            raise RepositoryError(f"Failed to save job {job_id}") from exc
        except Exception as exc:
            self.session.rollback()
            raise RepositoryError(f"Failed to save job {job_id}") from exc

        self.logger.info(
            "new_job_saved",
            extra={"job_id": record.job_id, "company_id": record.company_id, "is_new": True},
        )
        return JobSaveResult(record=record, is_new=True)

    def get_by_job_id(self, company_id: int, job_id: str) -> JobRecord | None:
        statement = select(JobRecord).where(
            JobRecord.company_id == company_id,
            JobRecord.job_id == job_id,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def _serialize_payload(
        self, job: object, *, company_id: int, timestamp: datetime
    ) -> dict[str, Any]:
        return {
            "company_id": company_id,
            "job_id": self._get_required_text(job, "job_id"),
            "title": self._get_required_text(job, "title"),
            "location": self._get_optional_text(job, "location"),
            "department": self._get_optional_text(job, "department"),
            "employment_type": self._get_optional_text(job, "employment_type"),
            "remote": self._get_optional_bool(job, "remote"),
            "salary": self._get_optional_text(job, "salary"),
            "url": self._get_required_text(job, "url"),
            "description": self._get_optional_text(job, "description"),
            "posted_at": self._get_optional_datetime(job, "posted_date"),
            "first_seen": timestamp,
            "last_seen": timestamp,
            "status": "ACTIVE",
        }

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
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            raise RepositoryError("Failed to save scan history") from exc

        return ScanHistorySaveResult(record=record, is_new=True)

    def list(self) -> list[ScanHistoryRecord]:
        statement = select(ScanHistoryRecord).order_by(ScanHistoryRecord.id.asc())
        return list(self.session.execute(statement).scalars().all())

    def _serialize_payload(self, history: object) -> dict[str, Any]:
        company_id = getattr(history, "company_id", None)
        if not isinstance(company_id, int):
            raise RepositoryError("Missing required field: company_id")

        started_at = getattr(history, "started_at", None)
        if started_at is None:
            started_at = datetime.now(timezone.utc)
        elif isinstance(started_at, datetime) and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        finished_at = getattr(history, "finished_at", None)
        if isinstance(finished_at, datetime) and finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=timezone.utc)

        return {
            "company_id": company_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "jobs_found": int(getattr(history, "jobs_found", 0) or 0),
            "jobs_added": int(getattr(history, "jobs_added", 0) or 0),
            "jobs_updated": int(getattr(history, "jobs_updated", 0) or 0),
            "jobs_removed": int(getattr(history, "jobs_removed", 0) or 0),
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