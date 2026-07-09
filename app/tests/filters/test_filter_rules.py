"""Tests for filtering rules."""

from __future__ import annotations

from dataclasses import dataclass

from app.filters.models import CompanyFilterConfig
from app.filters.rules import (
    CompanyRule,
    EmploymentTypeRule,
    KeywordExcludeRule,
    KeywordIncludeRule,
    LocationRule,
)


@dataclass(slots=True)
class JobStub:
    """Simple job double for rule tests."""

    title: str = ""
    description: str = ""
    department: str = ""
    location: str = ""
    employment_type: str = ""
    company: str = ""


def test_keyword_include_rule_matches_case_insensitively_and_with_punctuation() -> None:
    """Keyword include matching should ignore case and punctuation."""

    rule = KeywordIncludeRule(("backend engineer",))
    job = JobStub(title="Senior,  BACKEND---Engineer!")

    assert rule.matches(job) is True


def test_keyword_include_rule_misses_when_no_keyword_is_present() -> None:
    """Keyword include matching should reject jobs without a matching keyword."""

    rule = KeywordIncludeRule(("python",))
    job = JobStub(title="Data Scientist")

    assert rule.matches(job) is False


def test_keyword_include_rule_matches_across_title_description_and_department() -> None:
    """Keyword include matching should search all configured text fields."""

    rule = KeywordIncludeRule(("firmware",))
    job = JobStub(description="Exciting role in firmware development")

    assert rule.matches(job) is True


def test_keyword_include_rule_returns_true_for_empty_keyword_list() -> None:
    """An empty include keyword list should not filter anything out."""

    rule = KeywordIncludeRule(())
    job = JobStub(title="Any Job")

    assert rule.matches(job) is True


def test_keyword_include_rule_matches_any_of_multiple_keywords() -> None:
    """A job should pass when at least one include keyword matches."""

    rule = KeywordIncludeRule(("python", "embedded"))
    job = JobStub(title="Embedded Systems Engineer")

    assert rule.matches(job) is True


def test_keyword_exclude_rule_rejects_when_any_keyword_matches() -> None:
    """A job should be rejected when any exclude keyword matches."""

    rule = KeywordExcludeRule(("manager", "principal"))
    job = JobStub(title="Principal Engineer")

    assert rule.matches(job) is False


def test_keyword_exclude_rule_returns_true_for_empty_keyword_list() -> None:
    """An empty exclude keyword list should not reject any jobs."""

    rule = KeywordExcludeRule(())
    job = JobStub(title="Any Job")

    assert rule.matches(job) is True


def test_location_rule_matches_case_insensitively() -> None:
    """Location matching should ignore case."""

    rule = LocationRule(("Ottawa", "Toronto"))
    job = JobStub(location="oTtAwA")

    assert rule.matches(job) is True


def test_location_rule_rejects_unknown_location() -> None:
    """A job should be rejected when its location is not allowed."""

    rule = LocationRule(("Ottawa", "Toronto"))
    job = JobStub(location="Montreal")

    assert rule.matches(job) is False


def test_location_rule_returns_true_for_empty_location_list() -> None:
    """An empty location list should not filter anything out."""

    rule = LocationRule(())
    job = JobStub(location="Montreal")

    assert rule.matches(job) is True


def test_employment_type_rule_matches_case_insensitively() -> None:
    """Employment type matching should ignore case."""

    rule = EmploymentTypeRule(("Full Time", "Intern"))
    job = JobStub(employment_type="full time")

    assert rule.matches(job) is True


def test_employment_type_rule_rejects_unknown_type() -> None:
    """A job should be rejected when its employment type is not allowed."""

    rule = EmploymentTypeRule(("Full Time", "Intern"))
    job = JobStub(employment_type="Contract")

    assert rule.matches(job) is False


def test_employment_type_rule_returns_true_for_empty_type_list() -> None:
    """An empty employment type list should not filter anything out."""

    rule = EmploymentTypeRule(())
    job = JobStub(employment_type="Contract")

    assert rule.matches(job) is True


def test_company_rule_matches_case_insensitively() -> None:
    """Company matching should ignore case."""

    rule = CompanyRule(CompanyFilterConfig(include=("Nokia", "Ciena")))
    job = JobStub(company="nOkIa")

    assert rule.matches(job) is True


def test_company_rule_rejects_unknown_company() -> None:
    """A job should be rejected when its company is not allowed."""

    rule = CompanyRule(CompanyFilterConfig(include=("Nokia", "Ciena")))
    job = JobStub(company="Acme")

    assert rule.matches(job) is False


def test_company_rule_returns_true_for_empty_company_list() -> None:
    """An empty company list should not filter anything out."""

    rule = CompanyRule(CompanyFilterConfig(include=()))
    job = JobStub(company="Acme")

    assert rule.matches(job) is True