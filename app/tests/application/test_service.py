"""Tests for the Career Monitor application service."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.application.service import CareerMonitorRunSummary, CareerMonitorService, ScanRunHistory
from app.config.filter_loader import FilterConfigLoader
from app.config.loader import ConfigLoader
from app.db.repositories import JobSaveResult
from app.db.session import DatabaseSessionManager
from app.filtering.models import FilterRules
from app.notifications.interfaces import NotificationProvider
from app.notifications.models import Notification
from app.scanners.manager import ScannerManager
from app.config.models import ApplicationConfig, CompanyConfig


@dataclass
class FakeJob:
    job_id: str
    company: str
    title: str
    location: str = "Toronto"
    url: str = "https://example.com/job/1"
    description: str = "Python role"
    employment_type: str = "full-time"
    remote: bool = True
    source: str = "workday"


@dataclass
class FakeRecord:
    job_id: str
    company: str
    title: str


class FakeConfigLoader(ConfigLoader):
    def __init__(self, config: ApplicationConfig) -> None:
        self._config = config
        self.loaded_path: str | Path | None = None

    def load(self, path: str | Path) -> ApplicationConfig:  # type: ignore[override]
        self.loaded_path = path
        return self._config


class FakeFilterLoader(FilterConfigLoader):
    def __init__(self, rules: FilterRules) -> None:
        self._rules = rules
        self.loaded_path: str | Path | None = None

    def load(self, path: str | Path) -> FilterRules:  # type: ignore[override]
        self.loaded_path = path
        return self._rules


class FakeFilterEngine:
    def __init__(self, rules: FilterRules, returned_jobs: list[object]) -> None:
        self.rules = rules
        self.returned_jobs = returned_jobs
        self.received_jobs: list[object] | None = None

    def filter_jobs(self, jobs: object) -> list[object]:
        self.received_jobs = list(jobs)
        return self.returned_jobs


class FakeScannerManager(ScannerManager):
    def __init__(self, jobs: list[object]) -> None:
        self.jobs = jobs
        self.received_config: ApplicationConfig | None = None

    def run(self, config: ApplicationConfig) -> list[object]:  # type: ignore[override]
        self.received_config = config
        return self.jobs


class FakeJobRepository:
    def __init__(self, session: object) -> None:
        self.saved_jobs: list[object] = []

    def save(self, job: object) -> JobSaveResult:
        self.saved_jobs.append(job)
        job_id = getattr(job, "job_id")
        is_new = job_id != "dup"
        record = FakeRecord(
            job_id=job_id,
            company=getattr(job, "company"),
            title=getattr(job, "title"),
        )
        return JobSaveResult(record=record, is_new=is_new)


class FakeScanHistoryRepository:
    def __init__(self, session: object) -> None:
        self.records: list[object] = []

    def add(self, record: object) -> object:
        self.records.append(record)
        return record


class FakeDatabaseSessionManager(DatabaseSessionManager):
    def __init__(self) -> None:
        self.engine = object()

    @contextmanager
    def session_scope(self) -> Iterator[object]:  # type: ignore[override]
        yield object()


class RecordingNotificationProvider(NotificationProvider):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        if self.fail:
            raise RuntimeError("notification failed")
        self.sent.append(notification)


def test_service_runs_end_to_end_and_notifies_new_jobs() -> None:
    config = ApplicationConfig(
        companies=(
            CompanyConfig(name="Nokia", scanner="workday", url="https://example.com/nokia"),
        )
    )
    rules = FilterRules(include_keywords=("python",))

    jobs = [
        FakeJob(job_id="1", company="Nokia", title="Python Engineer"),
        FakeJob(job_id="dup", company="Nokia", title="Python Engineer"),
    ]

    fake_config_loader = FakeConfigLoader(config)
    fake_filter_loader = FakeFilterLoader(rules)
    fake_scanner_manager = FakeScannerManager(jobs)
    fake_notifications = RecordingNotificationProvider()
    fake_db = FakeDatabaseSessionManager()

    captured_history: list[ScanRunHistory] = []

    def filter_engine_factory(loaded_rules: FilterRules) -> FakeFilterEngine:
        assert loaded_rules == rules
        return FakeFilterEngine(loaded_rules, returned_jobs=jobs)

    def job_repo_factory(session: object) -> FakeJobRepository:
        return FakeJobRepository(session)

    def history_repo_factory(session: object) -> FakeScanHistoryRepository:
        repo = FakeScanHistoryRepository(session)
        original_add = repo.add

        def add_and_capture(record: object) -> object:
            captured_history.append(record)  # type: ignore[arg-type]
            return original_add(record)

        repo.add = add_and_capture  # type: ignore[method-assign]
        return repo

    service = CareerMonitorService(
        config_loader=fake_config_loader,
        filter_loader=fake_filter_loader,
        scanner_manager=fake_scanner_manager,
        database_session_manager=fake_db,
        notification_provider=fake_notifications,
        filter_engine_factory=filter_engine_factory,
        job_repository_factory=job_repo_factory,
        scan_history_repository_factory=history_repo_factory,
    )

    summary = service.run("companies.yaml", "filters.yaml")

    assert isinstance(summary, CareerMonitorRunSummary)
    assert fake_config_loader.loaded_path == "companies.yaml"
    assert fake_filter_loader.loaded_path == "filters.yaml"
    assert fake_scanner_manager.received_config == config
    assert summary.jobs_found == 2
    assert summary.jobs_filtered == 2
    assert summary.new_jobs == 1
    assert summary.duplicates == 1
    assert summary.notifications_sent == 1
    assert summary.notification_failures == 0
    assert len(fake_notifications.sent) == 1
    assert fake_notifications.sent[0].title == "New job: Python Engineer"
    assert len(captured_history) == 1
    assert captured_history[0].status == "completed"


def test_notification_failure_is_logged_but_pipeline_continues() -> None:
    config = ApplicationConfig(
        companies=(
            CompanyConfig(name="Nokia", scanner="workday", url="https://example.com/nokia"),
        )
    )
    rules = FilterRules()
    jobs = [FakeJob(job_id="1", company="Nokia", title="Python Engineer")]

    service = CareerMonitorService(
        config_loader=FakeConfigLoader(config),
        filter_loader=FakeFilterLoader(rules),
        scanner_manager=FakeScannerManager(jobs),
        database_session_manager=FakeDatabaseSessionManager(),
        notification_provider=RecordingNotificationProvider(fail=True),
        filter_engine_factory=lambda loaded_rules: FakeFilterEngine(loaded_rules, returned_jobs=jobs),
        job_repository_factory=lambda session: FakeJobRepository(session),
        scan_history_repository_factory=lambda session: FakeScanHistoryRepository(session),
    )

    summary = service.run("companies.yaml", "filters.yaml")

    assert summary.new_jobs == 1
    assert summary.notifications_sent == 0
    assert summary.notification_failures == 1