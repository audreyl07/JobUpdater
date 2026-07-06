"""Tests for the filtering engine."""

from __future__ import annotations

from dataclasses import dataclass

from app.filtering.engine import FilterEngine
from app.filtering.models import FilterRules


@dataclass
class FakeJob:
    """Test double for job objects."""

    title: str
    location: str = ""
    employment_type: str = ""
    description: str = ""
    company: str = ""
    remote: bool | None = None


def test_include_keywords_filter() -> None:
    engine = FilterEngine(FilterRules(include_keywords=("python",)))
    jobs = [FakeJob(title="Python Backend Engineer"), FakeJob(title="Java Developer")]

    filtered = engine.filter_jobs(jobs)

    assert len(filtered) == 1
    assert filtered[0].title == "Python Backend Engineer"


def test_exclude_keywords_filter() -> None:
    engine = FilterEngine(FilterRules(exclude_keywords=("intern",)))
    jobs = [FakeJob(title="Software Engineer"), FakeJob(title="Engineering Intern")]

    filtered = engine.filter_jobs(jobs)

    assert len(filtered) == 1
    assert filtered[0].title == "Software Engineer"


def test_location_filter() -> None:
    engine = FilterEngine(FilterRules(locations=("Toronto",)))
    jobs = [FakeJob(title="Engineer", location="Toronto, ON"), FakeJob(title="Engineer", location="London")]

    filtered = engine.filter_jobs(jobs)

    assert len(filtered) == 1
    assert filtered[0].location == "Toronto, ON"


def test_remote_filter_true() -> None:
    engine = FilterEngine(FilterRules(remote=True))
    jobs = [FakeJob(title="Remote Engineer", remote=True), FakeJob(title="Onsite Engineer", remote=False)]

    filtered = engine.filter_jobs(jobs)

    assert len(filtered) == 1
    assert filtered[0].remote is True


def test_employment_type_filter() -> None:
    engine = FilterEngine(FilterRules(employment_types=("full-time",)))
    jobs = [
        FakeJob(title="Engineer", employment_type="full-time"),
        FakeJob(title="Engineer", employment_type="contract"),
    ]

    filtered = engine.filter_jobs(jobs)

    assert len(filtered) == 1
    assert filtered[0].employment_type == "full-time"


def test_seniority_filters_match_any_group() -> None:
    engine = FilterEngine(
        FilterRules(
            intern_keywords=("intern",),
            new_grad_keywords=("new grad",),
            junior_keywords=("junior",),
        )
    )
    jobs = [
        FakeJob(title="Senior Engineer"),
        FakeJob(title="Junior Engineer"),
        FakeJob(title="New Grad Software Engineer"),
    ]

    filtered = engine.filter_jobs(jobs)

    assert [job.title for job in filtered] == ["Junior Engineer", "New Grad Software Engineer"]


def test_combined_filters_require_all_conditions() -> None:
    engine = FilterEngine(
        FilterRules(
            include_keywords=("python",),
            exclude_keywords=("intern",),
            locations=("Toronto",),
            remote=True,
            employment_types=("full-time",),
        )
    )
    jobs = [
        FakeJob(
            title="Python Engineer",
            location="Toronto",
            remote=True,
            employment_type="full-time",
        ),
        FakeJob(
            title="Python Intern",
            location="Toronto",
            remote=True,
            employment_type="full-time",
        ),
    ]

    filtered = engine.filter_jobs(jobs)

    assert len(filtered) == 1
    assert filtered[0].title == "Python Engineer"