# filepath: main.py
from __future__ import annotations

import argparse
from pathlib import Path

from app.config.loader import ConfigLoader
from app.database.engine import create_database_engine_from_env
from app.database.session import DatabaseTransactionError, session_scope
from app.filters.engine import FilterEngine
from app.filters.loader import FilterConfigLoader
from app.repositories.company_repository import CompanyRepository
from app.scanners.manager import ScannerManager
from app.scanners.workday import WorkdayScanner
from app.services.job_sync import JobSyncService, JobSyncTransactionError
from app.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run Career Monitor scanners.")

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/companies.yaml"),
        help="Path to the companies YAML configuration.",
    )
    parser.add_argument(
        "--filters",
        type=Path,
        default=Path("config/filters.yaml"),
        help="Path to the filters YAML configuration.",
    )
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # --- config --------------------------------------------------------------
    loader = ConfigLoader()
    config = loader.load(args.config)
    filter_config = FilterConfigLoader().load(args.filters)

    # --- database engine (validates DATABASE_URL eagerly at startup) ---------
    engine = create_database_engine_from_env()

    # --- scan ----------------------------------------------------------------
    scanner_factories = {
        "workday": lambda company: WorkdayScanner(
            company_name=company.name,
            base_url=company.url,
            page_size=args.page_size,
            timeout=args.timeout,
        )
    }
    manager = ScannerManager(scanner_factories)
    jobs = manager.run(config)
    filtered_jobs = FilterEngine.from_config(filter_config).filter_jobs(jobs)

    # Group filtered results by company name so each company gets its own
    # sync transaction. Uses job.company (the scanner dataclass string field)
    # as the grouping key — no scanner internals are touched.
    jobs_by_company: dict[str, list] = {}
    for job in filtered_jobs:
        jobs_by_company.setdefault(job.company, []).append(job)

    # --- sync + notify -------------------------------------------------------
    total_added = total_updated = total_removed = total_notified = 0

    for company_config in config.companies:
        company_name = company_config.name
        company_jobs = jobs_by_company.get(company_name, [])

        try:
            with session_scope(engine) as session:
                companies = CompanyRepository(session)

                # Upsert so a company row always exists even on first run.
                company_row = companies.get_or_create(
                    name=company_name,
                    scanner=company_config.scanner,
                    careers_url=company_config.url,
                )

                summary = JobSyncService(session).sync(
                    company_id=company_row.id,
                    scanned_jobs=company_jobs,
                )

            total_added += summary.jobs_added
            total_updated += summary.jobs_updated
            total_removed += summary.jobs_removed

            # Notify outside the DB transaction so a Discord failure never
            # rolls back a successful sync.
            if summary.jobs_to_notify:
                _send_notifications(summary.jobs_to_notify, company_name)
                total_notified += len(summary.jobs_to_notify)

        except (JobSyncTransactionError, DatabaseTransactionError):
            # Already logged with full traceback inside the service / session_scope.
            logger.error("Skipping notifications for %s due to sync failure.", company_name)
            continue

    # --- summary -------------------------------------------------------------
    print("\n============================")
    print("Career Monitor")
    print("============================")
    print(f"Companies scanned : {len(config.companies)}")
    print(f"Jobs found        : {len(jobs)}")
    print(f"Jobs accepted     : {len(filtered_jobs)}")
    print(f"Jobs added        : {total_added}")
    print(f"Jobs updated      : {total_updated}")
    print(f"Jobs removed      : {total_removed}")
    print(f"Notifications sent: {total_notified}")
    print()

    for job in filtered_jobs:
        print(f"{job.title}")
        print(f"  {job.url}")
        print()

    logger.info(
        "Completed scan: %s companies, %s found, %s accepted, "
        "%s added, %s updated, %s removed, %s notified",
        len(config.companies),
        len(jobs),
        len(filtered_jobs),
        total_added,
        total_updated,
        total_removed,
        total_notified,
    )

    return 0


def _send_notifications(jobs: list, company_name: str) -> None:
    """Send Discord notifications for jobs flagged by the sync service.

    Keeping this as a stub: plug your existing Discord notifier here.
    The jobs list contains ORM Job objects (id, title, url, status, etc.)
    that were either inserted, updated, or reappeared in this scan.
    """
    for job in jobs:
        logger.info(
            "NOTIFY [%s] %s — %s",
            company_name,
            job.title,
            job.url,
        )


if __name__ == "__main__":
    raise SystemExit(main())