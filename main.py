from __future__ import annotations

import argparse
from pathlib import Path

from app.config.loader import ConfigLoader
from app.filters.engine import FilterEngine
from app.filters.loader import FilterConfigLoader
from app.scanners.manager import ScannerManager
from app.scanners.workday import WorkdayScanner
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

    # Load the configuration
    loader = ConfigLoader()
    config = loader.load(args.config)

    filter_config = FilterConfigLoader().load(args.filters)

    # Register scanner factories
    scanner_factories = {
        "workday": lambda company: WorkdayScanner(
            company_name=company.name,
            base_url=company.url,
            page_size=args.page_size,
            timeout=args.timeout,
        )
    }

    # Create the manager
    manager = ScannerManager(scanner_factories)

    # Scan every configured company
    jobs = manager.run(config)

    filtered_jobs = FilterEngine.from_config(filter_config).filter_jobs(jobs)

    print("\n============================")
    print("Career Monitor")
    print("============================")
    print(f"Companies scanned : {len(config.companies)}")
    print(f"Jobs found        : {len(jobs)}")
    print(f"Jobs accepted     : {len(filtered_jobs)}")
    print()

    for job in filtered_jobs:
        print(f"{job.title}")
        print(f"  {job.url}")
        print()

    logger.info(
        "Completed scan: %s companies, %s jobs, %s accepted",
        len(config.companies),
        len(jobs),
        len(filtered_jobs),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())