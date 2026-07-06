from __future__ import annotations

import argparses

from app.runner import run_scanner
from app.scanners.workday import WorkdayScanner
from app.utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run a Workday job scan.")
    parser.add_argument(
        "company_name",
        help="Display name for the company being scanned.",
    )
    parser.add_argument(
        "base_url",
        help="Workday careers page or jobs API URL.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Number of jobs to request per page.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    """Run a single Workday scan."""
    args = parse_args()

    scanner = WorkdayScanner(
        company_name=args.company_name,
        base_url=args.base_url,
        timeout=args.timeout,
        page_size=args.page_size,
    )

    result = run_scanner(scanner)

    logger.info(
        "Completed scan company=%s jobs=%s",
        result.company,
        len(result.jobs),
    )
    print(f"{result.company}: {len(result.jobs)} jobs found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())