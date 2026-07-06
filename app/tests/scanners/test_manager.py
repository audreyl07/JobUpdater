"""Tests for scanner orchestration."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.config.models import ApplicationConfig, CompanyConfig
from app.scanners.manager import (
    ScannerExecutionError,
    ScannerManager,
    UnknownScannerError,
)


@dataclass
class FakeScanner:
    """Simple scanner double used in tests."""

    jobs: list[object]

    def scan(self) -> list[object]:
        return self.jobs


def test_run_all_scanners_combines_jobs() -> None:
    """ScannerManager should combine results from all configured scanners."""

    def factory(company: CompanyConfig) -> FakeScanner:
        return FakeScanner(jobs=[f"{company.name}-job-1", f"{company.name}-job-2"])

    manager = ScannerManager(scanner_factories={"workday": factory})
    config = ApplicationConfig(
        companies=(
            CompanyConfig(name="Nokia", scanner="workday", url="https://example.com/nokia"),
            CompanyConfig(name="Kinaxis", scanner="workday", url="https://example.com/kinaxis"),
        )
    )

    jobs = manager.run(config)

    assert jobs == [
        "Nokia-job-1",
        "Nokia-job-2",
        "Kinaxis-job-1",
        "Kinaxis-job-2",
    ]


def test_unknown_scanner_raises_error() -> None:
    """An unregistered scanner type should raise a meaningful error."""

    manager = ScannerManager(scanner_factories={})
    config = ApplicationConfig(
        companies=(
            CompanyConfig(name="Nokia", scanner="workday", url="https://example.com/nokia"),
        )
    )

    with pytest.raises(UnknownScannerError, match="Unknown scanner type: workday"):
        manager.run(config)


def test_scanner_failure_is_wrapped() -> None:
    """Scanner failures should be wrapped in a scanner manager exception."""

    def factory(company: CompanyConfig) -> FakeScanner:
        raise RuntimeError("boom")

    manager = ScannerManager(scanner_factories={"workday": factory})
    config = ApplicationConfig(
        companies=(
            CompanyConfig(name="Nokia", scanner="workday", url="https://example.com/nokia"),
        )
    )

    with pytest.raises(ScannerExecutionError, match="Failed to create scanner 'workday'"):
        manager.run(config)