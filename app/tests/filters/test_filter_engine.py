"""Tests for the filtering engine."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.filters.engine import FilterEngine
from app.filters.models import CompanyFilterConfig, FilterConfig


@dataclass(slots=True)
class JobStub:
    """Simple job double for engine tests."""

    title: str = ""
    description: str = ""
    department: str = ""
    location: str = ""
    employment_type: str = ""
    company: str = ""


class RecordingRule:
    """Rule double that records match calls."""

    def __init__(self, result: bool) -> None:
        self.result = result
        self.calls = 0

    def matches(self, job: object) -> bool:
        self.calls += 1
        return self.result


def test_filter_jobs_short_circuits_on_first_failed_rule() -> None:
    """The engine should stop evaluating rules after the first failure."""

    first = RecordingRule(False)
    second = RecordingRule(True)
    engine = FilterEngine([first, second])

    result = engine.filter_jobs([JobStub(title="Any Job")])

    assert result == []
    assert first.calls == 1
    assert second.calls == 0


def test_filter_jobs_logs_summary(caplog: pytest.LogCaptureFixture) -> None:
    """The engine should log summary statistics for the run."""

    engine = FilterEngine([RecordingRule(True)])

    with caplog.at_level("INFO"):
        result = engine.filter_jobs([JobStub(title="Job 1"), JobStub(title="Job 2")])

    assert len(result) == 2
    assert "Received: 2 jobs" in caplog.text
    assert "Accepted: 2" in caplog.text
    assert "Rejected: 0" in caplog.text
    assert "Summary: received=2 accepted=2 rejected=0" in caplog.text


def test_filter_engine_from_config_applies_composed_rules() -> None:
    """The engine should build and apply the default rule set from config."""

    config = FilterConfig(
        include_keywords=("python",),
        exclude_keywords=("manager",),
        locations=("Ottawa",),
        employment_types=("Full Time",),
        companies=CompanyFilterConfig(include=("Nokia",)),
    )
    engine = FilterEngine.from_config(config)

    accepted = JobStub(
        title="Python Engineer",
        location="ottawa",
        employment_type="full time",
        company="nokia",
    )
    rejected_by_company = JobStub(
        title="Python Engineer",
        location="ottawa",
        employment_type="full time",
        company="Other",
    )
    rejected_by_keyword = JobStub(
        title="Manager",
        location="ottawa",
        employment_type="full time",
        company="nokia",
    )

    result = engine.filter_jobs([accepted, rejected_by_company, rejected_by_keyword])

    assert result == [accepted]