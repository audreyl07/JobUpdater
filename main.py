# filepath: main.py
from __future__ import annotations

import argparse
from pathlib import Path

from app.config.loader import ConfigLoader
from app.database import (
    DatabaseSessionManager,
    JobRepository,
    ScanHistoryRepository,
)
from app.database.exceptions import RepositoryError
from app.filters.engine import FilterEngine
from app.filters.loader import FilterConfigLoader
from app.scanners.manager import ScannerManager
from app.scanners.workday import WorkdayScanner
from app.utils.logger import get_logger


logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run Career Monitor scanners."
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/companies.yaml"),
        help="Path to companies YAML configuration.",
    )

    parser.add_argument(
        "--filters",
        type=Path,
        default=Path("config/filters.yaml"),
        help="Path to filters YAML configuration.",
    )

    parser.add_argument(
        "--database",
        type=str,
        default="sqlite:///career_monitor.db",
        help="Database connection URL.",
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # ----------------------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------------------

    config = ConfigLoader().load(args.config)
    filter_config = FilterConfigLoader().load(args.filters)

    # ----------------------------------------------------------------------
    # Database initialization
    # ----------------------------------------------------------------------

    database = DatabaseSessionManager(
        args.database
    )

    database.create_tables()

    logger.info(
        "Database initialized"
    )


    # ----------------------------------------------------------------------
    # Scanner setup
    # ----------------------------------------------------------------------

    scanner_factories = {
        "workday": lambda company: WorkdayScanner(
            company_name=company.name,
            base_url=company.url,
            page_size=args.page_size,
            timeout=args.timeout,
        )
    }


    manager = ScannerManager(
        scanner_factories
    )


    # ----------------------------------------------------------------------
    # Scan
    # ----------------------------------------------------------------------

    jobs = manager.run(config)


    filtered_jobs = (
        FilterEngine
        .from_config(filter_config)
        .filter_jobs(jobs)
    )


    logger.info(
        "Filtering complete",
        extra={
            "found": len(jobs),
            "accepted": len(filtered_jobs),
        },
    )


    # ----------------------------------------------------------------------
    # Save jobs
    # ----------------------------------------------------------------------

    added = 0
    existing = 0


    try:

        with database.session_scope() as session:

            job_repository = JobRepository(
                session
            )

            for job in filtered_jobs:

                result = job_repository.save(
                    job
                )

                if result.is_new:
                    added += 1
                else:
                    existing += 1


            # Save scan history

            history_repository = ScanHistoryRepository(
                session
            )


            for company in config.companies:

                history_repository.add(
                    type(
                        "ScanHistory",
                        (),
                        {
                            "company": company.name,
                            "scanner": company.scanner,
                            "jobs_found": len(jobs),
                            "jobs_filtered": len(filtered_jobs),
                            "status": "completed",
                        },
                    )()
                )


    except RepositoryError as exc:

        logger.exception(
            "Database save failed"
        )

        return 1



    # ----------------------------------------------------------------------
    # Output summary
    # ----------------------------------------------------------------------

    print()
    print("============================")
    print("Career Monitor")
    print("============================")
    print(
        f"Companies scanned : {len(config.companies)}"
    )
    print(
        f"Jobs found        : {len(jobs)}"
    )
    print(
        f"Jobs accepted     : {len(filtered_jobs)}"
    )
    print(
        f"Jobs added        : {added}"
    )
    print(
        f"Jobs existing     : {existing}"
    )
    print()


    for job in filtered_jobs:

        print(job.title)

        if job.url:
            print(f"  {job.url}")

        print()


    logger.info(
        "Completed scan: companies=%s found=%s accepted=%s added=%s existing=%s",
        len(config.companies),
        len(jobs),
        len(filtered_jobs),
        added,
        existing,
    )


    return 0



if __name__ == "__main__":
    raise SystemExit(main())