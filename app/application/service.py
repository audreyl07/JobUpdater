"""Application service for the Career Monitor pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from logging import Logger, getLogger
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.config.filter_loader import FilterConfigLoader
from app.config.loader import ConfigLoader
from app.db.repositories import JobRepository, JobSaveResult, ScanHistoryRepository
from app.db.session import DatabaseSessionManager
from app.filtering.engine import FilterEngine
from app.filtering.models import FilterRules
from app.notifications.interfaces import NotificationProvider
from app.notifications.models import Notification
from app.scanners.manager import ScannerManager


@dataclass(frozen=True, slots=True)
class ScanRunHistory:
    """History payload stored after one pipeline run."""

    company: str
    scanner: str
    started_at: datetime
    completed_at: datetime
    jobs_found: int
    jobs_filtered: int
    status: str
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class CareerMonitorRunSummary:
    """Result summary for one application run."""

    jobs_found: int
    jobs_filtered: int
    new_jobs: int
    duplicates: int
    notifications_sent: int
    notification_failures: int


@dataclass(slots=True)
class CareerMonitorService:
    """Orchestrate the full Career Monitor pipeline."""

    config_loader: ConfigLoader
    filter_loader: FilterConfigLoader
    scanner_manager: ScannerManager
    database_session_manager: DatabaseSessionManager
    notification_provider: NotificationProvider
    logger: Logger | None = None
    filter_engine_factory: Callable[[FilterRules], FilterEngine] = FilterEngine
    job_repository_factory: Callable[[Session], JobRepository] = JobRepository
    scan_history_repository_factory: Callable[[Session], ScanHistoryRepository] = ScanHistoryRepository

    def __post_init__(self) -> None:
        """Initialize defaults."""
        if self.logger is None:
            self.logger = getLogger(__name__)

    def run(self, companies_config_path: str | Path, filters_config_path: str | Path) -> CareerMonitorRunSummary:
        """Execute the full pipeline."""
        self.logger.info(
            "pipeline_started",
            extra={
                "companies_config_path": str(companies_config_path),
                "filters_config_path": str(filters_config_path),
            },
        )

        started_at = datetime.now(timezone.utc)
        application_config = self.config_loader.load(companies_config_path)
        filter_rules = self.filter_loader.load(filters_config_path)
        filter_engine = self.filter_engine_factory(filter_rules)

        discovered_jobs = list(self.scanner_manager.run(application_config))
        filtered_jobs = filter_engine.filter_jobs(discovered_jobs)

        self.logger.info("jobs_found", extra={"jobs_found": len(discovered_jobs)})
        self.logger.info(
            "jobs_filtered",
            extra={"jobs_in": len(discovered_jobs), "jobs_out": len(filtered_jobs)},
        )

        new_jobs = 0
        duplicates = 0
        notifications_sent = 0
        notification_failures = 0

        with self.database_session_manager.session_scope() as session:
            job_repository = self.job_repository_factory(session)
            history_repository = self.scan_history_repository_factory(session)

            for job in filtered_jobs:
                save_result = job_repository.save(job)
                if save_result.is_new:
                    new_jobs += 1
                    self.logger.info(
                        "new_job_detected",
                        extra={"job_id": save_result.record.job_id, "company": save_result.record.company},
                    )
                    try:
                        self.notification_provider.send(self._build_notification(job))
                    except Exception:
                        notification_failures += 1
                        self.logger.exception(
                            "notification_error",
                            extra={"job_id": save_result.record.job_id, "company": save_result.record.company},
                        )
                    else:
                        notifications_sent += 1
                        self.logger.info(
                            "notification_sent",
                            extra={"job_id": save_result.record.job_id, "company": save_result.record.company},
                        )
                else:
                    duplicates += 1
                    self.logger.info(
                        "duplicate_job_detected",
                        extra={"job_id": save_result.record.job_id, "company": save_result.record.company},
                    )

            completed_at = datetime.now(timezone.utc)
            history_repository.add(
                ScanRunHistory(
                    company="all",
                    scanner="pipeline",
                    started_at=started_at,
                    completed_at=completed_at,
                    jobs_found=len(discovered_jobs),
                    jobs_filtered=len(filtered_jobs),
                    status="completed",
                )
            )

        self.logger.info(
            "pipeline_completed",
            extra={
                "jobs_found": len(discovered_jobs),
                "jobs_filtered": len(filtered_jobs),
                "new_jobs": new_jobs,
                "duplicates": duplicates,
                "notifications_sent": notifications_sent,
                "notification_failures": notification_failures,
            },
        )

        return CareerMonitorRunSummary(
            jobs_found=len(discovered_jobs),
            jobs_filtered=len(filtered_jobs),
            new_jobs=new_jobs,
            duplicates=duplicates,
            notifications_sent=notifications_sent,
            notification_failures=notification_failures,
        )

    def _build_notification(self, job: object) -> Notification:
        """Convert a job object into a notification payload."""
        title = self._get_text(job, "title") or "New job found"
        company = self._get_text(job, "company")
        location = self._get_text(job, "location")
        url = self._get_text(job, "url")
        employment_type = self._get_text(job, "employment_type")
        source = self._get_text(job, "source")
        job_id = self._get_text(job, "job_id")

        metadata: dict[str, str] = {"job_id": job_id}
        if company:
            metadata["company"] = company
        if location:
            metadata["location"] = location
        if employment_type:
            metadata["employment_type"] = employment_type
        if source:
            metadata["source"] = source

        message_parts = [part for part in [company, title] if part]
        message = " - ".join(message_parts) if message_parts else title

        return Notification(
            title=f"New job: {title}",
            message=message,
            url=url or None,
            metadata=metadata,
        )

    def _get_text(self, job: object, field_name: str) -> str:
        """Read a text field from a job object."""
        value = getattr(job, field_name, "")
        return value.strip() if isinstance(value, str) else ""