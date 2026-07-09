"""Scanner orchestration for running configured company scanners."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger, getLogger
from typing import Callable, Mapping, Protocol, Sequence

from app.config.models import ApplicationConfig, CompanyConfig


class ScannerManagerError(Exception):
    """Base exception for scanner manager failures."""


class UnknownScannerError(ScannerManagerError):
    """Raised when a scanner type is not registered."""


class ScannerExecutionError(ScannerManagerError):
    """Raised when a scanner fails during execution."""


class ScannerProtocol(Protocol):
    """Protocol for scanner implementations."""

    def scan(self) -> Sequence[object]:
        """Run the scanner and return discovered jobs."""


ScannerFactory = Callable[[CompanyConfig], ScannerProtocol]


@dataclass(slots=True)
class ScannerManager:
    """Run configured scanners and combine their results."""

    scanner_factories: Mapping[str, ScannerFactory]
    logger: Logger | None = None

    def __post_init__(self) -> None:
        """Initialize internal defaults."""
        if self.logger is None:
            self.logger = getLogger(__name__)

    def run(self, config: ApplicationConfig) -> list[object]:
        """Run all configured scanners and return combined job results."""
        combined_jobs: list[object] = []

        for company in config.companies:
            scanner = self._create_scanner(company)
            self.logger.info(
                "scanner_started",
                extra={"company": company.name, "scanner": company.scanner},
            )

            try:
                jobs = scanner.scan().jobs            
            except Exception as exc:  # noqa: BLE001
                self.logger.exception(
                    "scanner_error",
                    extra={"company": company.name, "scanner": company.scanner},
                )
                raise ScannerExecutionError(
                    f"Scanner failed for company '{company.name}' using '{company.scanner}'"
                ) from exc

            self.logger.info(
                "scanner_completed",
                extra={
                    "company": company.name,
                    "scanner": company.scanner,
                    "jobs_found": len(jobs),
                },
            )
            combined_jobs.extend(jobs)

        return combined_jobs

    def _create_scanner(self, company: CompanyConfig) -> ScannerProtocol:
        """Create the scanner for a company configuration."""
        factory = self.scanner_factories.get(company.scanner)
        if factory is None:
            raise UnknownScannerError(f"Unknown scanner type: {company.scanner}")

        try:
            return factory(company)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception(
                "scanner_creation_failed",
                extra={"company": company.name, "scanner": company.scanner},
            )
            raise ScannerExecutionError(
                f"Failed to create scanner '{company.scanner}' for company '{company.name}'"
            ) from exc