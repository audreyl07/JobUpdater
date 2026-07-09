"""Service layer that syncs filtered scanner output into PostgreSQL.

Sits between the filtering stage and the notification stage:

    discover -> normalize -> filter -> [ this service ] -> notify -> record history

Owns no Session directly — all persistence goes through
CompanyRepository / JobRepository / NotificationRepository / ScanRepository,
per the "repositories are the only code that touches Session" rule.

ASSUMPTIONS (adjust if your actual models differ):
  - Job model has: id, company_id, external_job_id, title, location,
    description, department, salary, employment_type, content_hash,
    status (JobStatus.ACTIVE / JobStatus.REMOVED), first_seen, last_seen.
  - JobRepository exposes:
      get_all_for_company(company_id) -> list[Job]
      bulk_insert(jobs: list[Job]) -> None
      bulk_update(jobs: list[Job]) -> None   # updates already-attached ORM objects
  - NotificationRepository exposes:
      has_notified(job_id: int) -> bool
      create(job_id: int, company_id: int, reason: str) -> Notification
  - ScannedJob (scanner output, post-filter) has the same field names as
    Job's content fields, plus `external_job_id`.

If any of these don't match your real repositories/models, tell me the
actual signatures and I'll patch this file.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol

from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus
from app.repositories.job_repository import JobRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.scan_repository import (
    ScanPersistenceError,
    ScanRepository,
)

logger = logging.getLogger(__name__)

# Fields that participate in the content hash. Timestamps are deliberately
# excluded so unchanged postings don't register as "updated".
_HASHED_FIELDS = ("title", "location", "description", "department", "salary", "employment_type")


class ScannedJob(Protocol):
    """Structural type for filtered scanner output. Matches Job's content fields."""

    external_job_id: str
    title: str
    location: str | None
    description: str | None
    department: str | None
    salary: str | None
    employment_type: str | None
    url: str | None


class JobSyncError(Exception):
    """Base exception for job sync failures."""


class JobSyncTransactionError(JobSyncError):
    """Raised when the sync transaction fails and is rolled back."""


@dataclass
class SyncSummary:
    """Result of syncing one company's scan against the database."""

    company_id: int
    scan_id: int
    jobs_found: int = 0
    jobs_added: int = 0
    jobs_updated: int = 0
    jobs_removed: int = 0
    jobs_to_notify: list[Job] = field(default_factory=list)


def compute_content_hash(job: ScannedJob) -> str:
    """SHA256 over normalized content fields, ignoring timestamps.

    Normalization: lowercase, strip whitespace, treat None as empty string.
    Field order is fixed so the hash is deterministic.
    """
    parts = []
    for field_name in _HASHED_FIELDS:
        value = getattr(job, field_name, None) or ""
        parts.append(value.strip().lower())
    payload = "\x1f".join(parts)  # unit-separator avoids field collision
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JobSyncService:
    """Diffs filtered scanner output against stored jobs for one company.

    One instance call = one company scan = one transaction. The caller
    (orchestration entry point) is expected to commit the session after
    `sync` returns successfully, and roll back if it raises.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._jobs = JobRepository(session)
        self._notifications = NotificationRepository(session)
        self._scans = ScanRepository(session)

    def sync(self, company_id: int, scanned_jobs: Iterable[ScannedJob]) -> SyncSummary:
        """Sync one company's filtered scan results into the database.

        Steps:
          1. begin_scan
          2. preload existing jobs for company keyed by external_job_id
          3. diff: insert new / update changed / touch unchanged / remove missing
          4. determine notification-worthy jobs, deduped via NotificationRepository
          5. save_statistics + record_success (or record_failure on error)

        Raises JobSyncTransactionError on failure; caller should roll back
        the session in that case.
        """
        scanned_jobs = list(scanned_jobs)
        scan = self._scans.begin_scan(company_id)

        try:
            summary = self._diff_and_apply(company_id, scan.id, scanned_jobs)
            self._scans.save_statistics(
                scan.id,
                jobs_found=summary.jobs_found,
                jobs_added=summary.jobs_added,
                jobs_updated=summary.jobs_updated,
                jobs_removed=summary.jobs_removed,
            )
            self._scans.record_success(scan.id)
            logger.info(
                "Sync complete: company_id=%s scan_id=%s found=%s added=%s "
                "updated=%s removed=%s notify=%s",
                company_id,
                scan.id,
                summary.jobs_found,
                summary.jobs_added,
                summary.jobs_updated,
                summary.jobs_removed,
                len(summary.jobs_to_notify),
            )
            return summary
        except Exception as exc:  # noqa: BLE001 - intentional: wrap everything
            logger.error(
                "Sync failed for company_id=%s scan_id=%s: %s", company_id, scan.id, exc
            )
            try:
                self._scans.record_failure(scan.id, str(exc))
            except ScanPersistenceError:
                logger.error(
                    "Also failed to record failure state for scan_id=%s", scan.id
                )
            raise JobSyncTransactionError(
                f"Job sync failed for company_id={company_id}"
            ) from exc

    # -- internals ----------------------------------------------------------

    def _diff_and_apply(
        self, company_id: int, scan_id: int, scanned_jobs: list[ScannedJob]
    ) -> SyncSummary:
        now = datetime.now(timezone.utc)
        existing_by_ext_id: dict[str, Job] = {
            job.external_job_id: job
            for job in self._jobs.get_all_for_company(company_id)
        }
        seen_ext_ids: set[str] = set()

        to_insert: list[Job] = []
        to_update: list[Job] = []
        to_notify: list[Job] = []
        changed_count = 0
        touched_count = 0

        for scanned in scanned_jobs:
            seen_ext_ids.add(scanned.external_job_id)
            new_hash = compute_content_hash(scanned)
            existing = existing_by_ext_id.get(scanned.external_job_id)

            if existing is None:
                job = Job(
                    company_id=company_id,
                    external_job_id=scanned.external_job_id,
                    title=scanned.title,
                    location=scanned.location,
                    description=scanned.description,
                    department=scanned.department,
                    salary=scanned.salary,
                    employment_type=scanned.employment_type,
                    url=getattr(scanned, "url", None),
                    content_hash=new_hash,
                    status=JobStatus.ACTIVE,
                    first_seen=now,
                    last_seen=now,
                )
                to_insert.append(job)
                to_notify.append(job)
                continue

            if existing.content_hash != new_hash:
                existing.title = scanned.title
                existing.location = scanned.location
                existing.description = scanned.description
                existing.department = scanned.department
                existing.salary = scanned.salary
                existing.employment_type = scanned.employment_type
                existing.content_hash = new_hash
                existing.status = JobStatus.ACTIVE
                existing.last_seen = now
                to_update.append(existing)
                to_notify.append(existing)
                changed_count += 1
            else:
                existing.last_seen = now
                if existing.status != JobStatus.ACTIVE:
                    existing.status = JobStatus.ACTIVE
                to_update.append(existing)
                touched_count += 1

        removed: list[Job] = []
        for ext_id, job in existing_by_ext_id.items():
            if ext_id not in seen_ext_ids and job.status != JobStatus.REMOVED:
                job.status = JobStatus.REMOVED
                removed.append(job)
                to_update.append(job)

        if to_insert:
            self._jobs.bulk_insert(to_insert)
        if to_update:
            self._jobs.bulk_update(to_update)

        logger.debug(
            "Diff detail: unchanged_touched=%s changed=%s", touched_count, changed_count
        )

        deduped_notify = self._dedupe_notifications(company_id, to_notify)

        return SyncSummary(
            company_id=company_id,
            scan_id=scan_id,
            jobs_found=len(scanned_jobs),
            jobs_added=len(to_insert),
            jobs_updated=changed_count,
            jobs_removed=len(removed),
            jobs_to_notify=deduped_notify,
        )

    def _dedupe_notifications(self, company_id: int, candidates: list[Job]) -> list[Job]:
        """Filter candidates down to jobs that haven't already been notified."""
        result: list[Job] = []
        for job in candidates:
            if self._notifications.has_notified(job.id):
                continue
            self._notifications.create(
                job_id=job.id,
                company_id=company_id,
                reason="new_or_updated_job",
            )
            result.append(job)
        return result