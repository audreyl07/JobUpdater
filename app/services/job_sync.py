"""Service layer that syncs filtered scanner output into PostgreSQL.

Sits between the filtering stage and the notification stage:

    discover -> normalize -> filter -> [this service] -> notify -> record history

Key design facts confirmed from your real files:
  - Scanner produces Job dataclasses (job_id, company string, title, etc.)
  - ORM Job uses external_job_id, company_id FK, and a one-to-one JobHash
    relationship for content hashing — NOT a content_hash column directly.
  - JobRepository.preload_by_company() eagerly loads hash_record via
    joinedload, so no per-job hash queries are needed in the diff loop.
  - JobRepository.update() accepts keyword-only fields; update_many()
    just flushes already-mutated ORM objects.
  - JobRepository.mark_removed_many() sets status = REMOVED and flushes.
  - NotificationRepository.create_if_missing(job_id, notification_type)
    is the atomic dedup primitive.
  - notification_type encodes the specific change so the (job_id,
    notification_type) unique constraint deduplicates same-event re-sends
    without blocking future distinct-change notifications.
  - Scanner Job.company is a string name; CompanyRepository is used to
    resolve it to a company_id in main.py before calling sync().
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Sequence

from sqlalchemy.orm import Session

from app.models.job import Job as OrmJob
from app.models.job import JobHash, JobStatus
from app.repositories.job_repository import JobRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.scan_repositories import ScanPersistenceError, ScanRepository

if TYPE_CHECKING:
    from app.models.job import Job as ScannedJob  # the scanner dataclass

logger = logging.getLogger(__name__)

# Fields that participate in the content hash.
# Timestamps and status are deliberately excluded.
_HASHED_FIELDS = (
    "title",
    "location",
    "department",
    "description",
    "url",
)


class JobSyncError(Exception):
    """Base exception for job sync failures."""


class JobSyncTransactionError(JobSyncError):
    """Raised when the sync transaction fails; caller should roll back."""


@dataclass
class SyncSummary:
    """Result of syncing one company's scan against the database."""

    company_id: int
    scan_id: int
    jobs_found: int = 0
    jobs_added: int = 0
    jobs_updated: int = 0
    jobs_removed: int = 0
    jobs_to_notify: list[OrmJob] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"SyncSummary(company_id={self.company_id}, scan_id={self.scan_id}, "
            f"found={self.jobs_found}, added={self.jobs_added}, "
            f"updated={self.jobs_updated}, removed={self.jobs_removed}, "
            f"notify={len(self.jobs_to_notify)})"
        )


def compute_content_hash(job: "ScannedJob") -> str:
    """SHA256 over normalized content fields, ignoring timestamps and status.

    Normalization: lowercase + strip, None treated as empty string.
    Field order is fixed so the hash is deterministic.
    Unit-separator (\\x1f) between fields prevents cross-field collision.
    """
    parts = []
    for field_name in _HASHED_FIELDS:
        value = getattr(job, field_name, None) or ""
        parts.append(value.strip().lower())
    payload = "\x1f".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JobSyncService:
    """Diffs filtered scanner output against stored jobs for one company.

    One .sync() call = one company scan = one transaction boundary.
    The caller (main.py) owns commit/rollback via session_scope().
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._jobs = JobRepository(session)
        self._notifications = NotificationRepository(session)
        self._scans = ScanRepository(session)

    def sync(
        self,
        company_id: int,
        scanned_jobs: Sequence["ScannedJob"],
    ) -> SyncSummary:
        """Sync one company's filtered scan results into the database.

        Steps:
          1. Begin scan history row (RUNNING).
          2. Preload all existing ORM jobs for the company (one query,
             hash_record eagerly loaded).
          3. Diff: insert new / update changed / touch unchanged /
             mark missing as REMOVED / notify reappeared.
          4. Deduplicate notifications via NotificationRepository.
          5. Save statistics + record SUCCESS (or FAILED on error).

        Raises JobSyncTransactionError on failure; session_scope() in
        main.py will roll back.
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
                "Sync complete: company_id=%s scan_id=%s found=%s "
                "added=%s updated=%s removed=%s notify=%s",
                company_id,
                scan.id,
                summary.jobs_found,
                summary.jobs_added,
                summary.jobs_updated,
                summary.jobs_removed,
                len(summary.jobs_to_notify),
            )
            return summary

        except Exception as exc:
            logger.error(
                "Sync failed: company_id=%s scan_id=%s error=%s",
                company_id,
                scan.id,
                exc,
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
        self,
        company_id: int,
        scan_id: int,
        scanned_jobs: list["ScannedJob"],
    ) -> SyncSummary:
        now = datetime.now(timezone.utc)

        # One query, hash_record eagerly loaded — no per-job queries below.
        existing_by_ext_id: dict[str, OrmJob] = self._jobs.preload_by_company(company_id)
        seen_ext_ids: set[str] = set()

        to_insert: list[OrmJob] = []
        insert_hashes: list[str] = []
        to_notify: list[tuple[OrmJob, str]] = []
        changed_count = 0

        for scanned in scanned_jobs:
            ext_id = scanned.job_id
            seen_ext_ids.add(ext_id)
            new_hash = compute_content_hash(scanned)
            existing = existing_by_ext_id.get(ext_id)

            if existing is None:
                # Brand new job.
                orm_job = OrmJob(
                    company_id=company_id,
                    external_job_id=ext_id,
                    title=scanned.title,
                    location=scanned.location,
                    department=scanned.department,
                    description=scanned.description,
                    url=scanned.url,
                    posted_date=getattr(scanned, "posted_date", None),
                    status=JobStatus.ACTIVE,
                    first_seen=now,
                    last_seen=now,
                )
                to_insert.append(orm_job)
                insert_hashes.append(new_hash)
                to_notify.append((orm_job, "new_job"))
                continue

            current_hash = (
                existing.hash_record.content_hash
                if existing.hash_record is not None
                else None
            )

            was_removed = existing.status == JobStatus.REMOVED

            if current_hash != new_hash:
                # Content changed (or hash was missing) — update all fields.
                notification_type = (
                    "job_reappeared" if was_removed else f"content_change:{new_hash}"
                )
                self._jobs.update(
                    existing,
                    title=scanned.title,
                    location=scanned.location,
                    department=scanned.department,
                    description=scanned.description,
                    url=scanned.url,
                    posted_date=getattr(scanned, "posted_date", None),
                    last_seen=now,
                    status=JobStatus.ACTIVE,
                    content_hash=new_hash,
                )
                to_notify.append((existing, notification_type))
                changed_count += 1
            else:
                # Content unchanged — touch last_seen and reactivate if needed.
                if was_removed:
                    # Job reappeared with identical content to when it was last
                    # active. Still notify — the absence itself was meaningful.
                    self._jobs.update(
                        existing,
                        last_seen=now,
                        status=JobStatus.ACTIVE,
                    )
                    to_notify.append((existing, "job_reappeared"))
                    changed_count += 1
                else:
                    existing.last_seen = now

        # Bulk insert new jobs with their hashes.
        if to_insert:
            self._jobs.insert_many(to_insert, content_hashes=insert_hashes)

        # Mark jobs absent from this scan as REMOVED.
        removed_count = 0
        to_remove = [
            job
            for ext_id, job in existing_by_ext_id.items()
            if ext_id not in seen_ext_ids and job.status != JobStatus.REMOVED
        ]
        if to_remove:
            self._jobs.mark_removed_many(to_remove)
            removed_count = len(to_remove)

        # Flush touches (last_seen only, no explicit repo call needed since
        # session_scope commits; flush here so IDs are available for dedup).
        self._session.flush()

        deduped_notify = self._dedupe_notifications(to_notify)

        return SyncSummary(
            company_id=company_id,
            scan_id=scan_id,
            jobs_found=len(scanned_jobs),
            jobs_added=len(to_insert),
            jobs_updated=changed_count,
            jobs_removed=removed_count,
            jobs_to_notify=deduped_notify,
        )

    def _dedupe_notifications(
        self, candidates: list[tuple[OrmJob, str]]
    ) -> list[OrmJob]:
        """Create notification rows for candidates that haven't been sent yet.

        notification_type encodes the specific event:
          "new_job"                  — first time this external_job_id appeared
          "content_change:{hash}"    — content changed (hash is the NEW hash)
          "job_reappeared"           — previously REMOVED, now back in the feed

        The (job_id, notification_type) unique constraint on the notifications
        table ensures identical events are never double-sent even under
        concurrent scans. create_if_missing() exploits that constraint rather
        than doing an explicit SELECT before every INSERT.
        """
        result: list[OrmJob] = []
        for orm_job, notification_type in candidates:
            notification = self._notifications.create_if_missing(
                job_id=orm_job.id,
                notification_type=notification_type,
            )
            if notification is not None:
                result.append(orm_job)
        return result