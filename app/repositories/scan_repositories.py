"""Repository for managing scan lifecycle and scan history persistence.

Owns all Session access related to ScanHistory rows. No business logic
about job diffing lives here — that belongs in job_sync_service.py. This
repository only tracks the lifecycle of a single company scan: begin,
record success/failure, save statistics, finish.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.scan_history import ScanHistory, ScanStatus

logger = logging.getLogger(__name__)


class ScanRepositoryError(Exception):
    """Base exception for scan repository failures."""


class ScanNotFoundError(ScanRepositoryError):
    """Raised when a scan_id does not correspond to an existing row."""

    def __init__(self, scan_id: int) -> None:
        super().__init__(f"Scan with id={scan_id} not found")
        self.scan_id = scan_id


class ScanAlreadyFinishedError(ScanRepositoryError):
    """Raised when attempting to finish/update a scan that is already closed."""

    def __init__(self, scan_id: int) -> None:
        super().__init__(f"Scan with id={scan_id} is already finished")
        self.scan_id = scan_id


class ScanPersistenceError(ScanRepositoryError):
    """Raised when a database operation fails unexpectedly."""


class ScanRepository:
    """Handles the one-company-one-transaction scan lifecycle.

    Callers are expected to manage the transaction boundary (commit/rollback)
    at the call site — typically the service layer — so that scan-history
    writes commit atomically together with job sync writes for the same
    company scan.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def begin_scan(self, company_id: int) -> ScanHistory:
        """Create and flush a new RUNNING scan row for a company.

        Flushes (not commits) so the row gets an id usable by callers
        within the same transaction. Raises ScanPersistenceError on
        constraint violations (e.g. invalid company_id).
        """
        scan = ScanHistory(
            company_id=company_id,
            status=ScanStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            jobs_found=0,
            jobs_added=0,
            jobs_updated=0,
            jobs_removed=0,
        )
        try:
            self._session.add(scan)
            self._session.flush()
        except SQLAlchemyError as exc:
            logger.error("Failed to begin scan for company_id=%s: %s", company_id, exc)
            raise ScanPersistenceError(
                f"Could not begin scan for company_id={company_id}"
            ) from exc

        logger.info("Scan started: scan_id=%s company_id=%s", scan.id, company_id)
        return scan

    def save_statistics(
        self,
        scan_id: int,
        *,
        jobs_found: int,
        jobs_added: int,
        jobs_updated: int,
        jobs_removed: int,
    ) -> ScanHistory:
        """Attach discovered/added/updated/removed counts to an in-progress scan."""
        scan = self._get_scan_or_raise(scan_id)
        if scan.status != ScanStatus.RUNNING:
            raise ScanAlreadyFinishedError(scan_id)

        scan.jobs_found = jobs_found
        scan.jobs_added = jobs_added
        scan.jobs_updated = jobs_updated
        scan.jobs_removed = jobs_removed

        try:
            self._session.flush()
        except SQLAlchemyError as exc:
            logger.error("Failed to save statistics for scan_id=%s: %s", scan_id, exc)
            raise ScanPersistenceError(
                f"Could not save statistics for scan_id={scan_id}"
            ) from exc

        logger.info(
            "Scan statistics saved: scan_id=%s found=%s added=%s updated=%s removed=%s",
            scan_id,
            jobs_found,
            jobs_added,
            jobs_updated,
            jobs_removed,
        )
        return scan

    def record_success(self, scan_id: int) -> ScanHistory:
        """Mark a scan as SUCCESS and set finished_at."""
        return self._finish(scan_id, status=ScanStatus.SUCCESS, error_message=None)

    def record_failure(self, scan_id: int, error_message: str) -> ScanHistory:
        """Mark a scan as FAILED with a redacted, truncated error message.

        Truncates to avoid unbounded error text and never logs the raw
        DATABASE_URL or credentials if present in the error message.
        """
        safe_message = self._redact(error_message)[:2000]
        return self._finish(scan_id, status=ScanStatus.FAILED, error_message=safe_message)

    def finish_scan(self, scan_id: int) -> ScanHistory:
        """Finalize a scan without changing its status.

        Use when the caller has already set status via record_success /
        record_failure and just needs to ensure finished_at is stamped.
        Idempotent-safe: raises if already finished to prevent double writes.
        """
        scan = self._get_scan_or_raise(scan_id)
        if scan.finished_at is not None:
            raise ScanAlreadyFinishedError(scan_id)

        scan.finished_at = datetime.now(timezone.utc)
        try:
            self._session.flush()
        except SQLAlchemyError as exc:
            logger.error("Failed to finish scan_id=%s: %s", scan_id, exc)
            raise ScanPersistenceError(f"Could not finish scan_id={scan_id}") from exc

        logger.info("Scan finished: scan_id=%s status=%s", scan_id, scan.status)
        return scan

    def get_latest_scan_for_company(self, company_id: int) -> Optional[ScanHistory]:
        """Return the most recent scan row for a company, or None."""
        stmt = (
            select(ScanHistory)
            .where(ScanHistory.company_id == company_id)
            .order_by(ScanHistory.started_at.desc())
            .limit(1)
        )
        try:
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to fetch latest scan for company_id=%s: %s", company_id, exc
            )
            raise ScanPersistenceError(
                f"Could not fetch latest scan for company_id={company_id}"
            ) from exc

    # -- internal helpers -------------------------------------------------

    def _finish(
        self, scan_id: int, *, status: ScanStatus, error_message: Optional[str]
    ) -> ScanHistory:
        scan = self._get_scan_or_raise(scan_id)
        if scan.status != ScanStatus.RUNNING:
            raise ScanAlreadyFinishedError(scan_id)

        scan.status = status
        scan.error_message = error_message
        scan.finished_at = datetime.now(timezone.utc)

        try:
            self._session.flush()
        except SQLAlchemyError as exc:
            logger.error(
                "Failed to record %s for scan_id=%s: %s", status, scan_id, exc
            )
            raise ScanPersistenceError(
                f"Could not record {status} for scan_id={scan_id}"
            ) from exc

        logger.info("Scan %s: scan_id=%s", status, scan_id)
        return scan

    def _get_scan_or_raise(self, scan_id: int) -> ScanHistory:
        scan = self._session.get(ScanHistory, scan_id)
        if scan is None:
            raise ScanNotFoundError(scan_id)
        return scan

    @staticmethod
    def _redact(message: str) -> str:
        """Strip credentials from postgresql+psycopg:// URLs in error text."""
        import re

        return re.sub(
            r"(postgresql\+psycopg://)[^@/]+@",
            r"\1***:***@",
            message,
        )