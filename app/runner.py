from __future__ import annotations

from app.scanners.base import BaseScanner, ScanResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


def run_scanner(scanner: BaseScanner) -> ScanResult:
    """Run a scanner and return its normalized results."""
    logger.info("Running scanner company=%s", scanner.company_name)
    result = scanner.scan()
    logger.info(
        "Scanner finished company=%s jobs=%s raw_count=%s",
        result.company,
        len(result.jobs),
        result.raw_count,
    )
    return result