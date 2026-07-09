"""Reusable filtering rules for jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import re
from typing import Any

from app.filters.models import CompanyFilterConfig, FilterConfig


_NON_WORD_RE = re.compile(r"[^a-zA-Z0-9]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


class BaseRule(ABC):
    """Base class for all filtering rules."""

    @abstractmethod
    def matches(self, job: Any) -> bool:
        """Return True when the job passes the rule."""


class TextRule(BaseRule):
    """Base class for rules that inspect job text fields."""

    def _normalize(self, value: object | None) -> str:
        if value is None:
            text = ""
        elif isinstance(value, Enum):
            text = str(value.value)
        else:
            text = str(value)
        text = text.strip().lower()
        text = _NON_WORD_RE.sub(" ", text)
        text = _WHITESPACE_RE.sub(" ", text)
        return text.strip()

    def _job_text(self, job: Any, fields: tuple[str, ...]) -> str:
        parts: list[str] = []
        for field in fields:
            value = getattr(job, field, "")
            normalized = self._normalize(value)
            if normalized:
                parts.append(normalized)
        return " ".join(parts)

    def _contains_keyword(self, text: str, keyword: str) -> bool:
        normalized_keyword = self._normalize(keyword)
        if not normalized_keyword:
            return False
        return normalized_keyword in text


class KeywordIncludeRule(TextRule):
    """Keep jobs that match at least one include keyword."""

    def __init__(self, keywords: tuple[str, ...]) -> None:
        self._keywords = keywords

    def matches(self, job: Any) -> bool:
        if not self._keywords:
            return True

        text = self._job_text(job, ("title", "description", "department"))
        return any(self._contains_keyword(text, keyword) for keyword in self._keywords)


class KeywordExcludeRule(TextRule):
    """Reject jobs that match any exclude keyword."""

    def __init__(self, keywords: tuple[str, ...]) -> None:
        self._keywords = keywords

    def matches(self, job: Any) -> bool:
        if not self._keywords:
            return True

        text = self._job_text(job, ("title", "description", "department"))
        return not any(self._contains_keyword(text, keyword) for keyword in self._keywords)


class LocationRule(TextRule):
    """Keep jobs whose location contains one of the allowed locations."""

    def __init__(self, locations: tuple[str, ...]) -> None:
        self._locations = locations

    def matches(self, job: Any) -> bool:
        if not self._locations:
            return True

        location = self._job_text(job, ("location",))
        if not location:
            return False

        return any(self._contains_keyword(location, item) for item in self._locations)


class EmploymentTypeRule(TextRule):
    """Keep jobs whose employment type contains one of the allowed types."""

    def __init__(self, employment_types: tuple[str, ...]) -> None:
        self._employment_types = employment_types

    def matches(self, job: Any) -> bool:
        if not self._employment_types:
            return True

        employment_type = self._job_text(job, ("employment_type",))
        if not employment_type:
            return False

        return any(
            self._contains_keyword(employment_type, item) for item in self._employment_types
        )


class CompanyRule(TextRule):
    """Keep jobs whose company matches one of the allowed companies."""

    def __init__(self, companies: CompanyFilterConfig) -> None:
        self._companies = companies

    def matches(self, job: Any) -> bool:
        if not self._companies.include:
            return True

        company_name = self._normalize(getattr(job, "company", ""))
        if not company_name:
            return False

        allowed_companies = tuple(self._normalize(item) for item in self._companies.include)
        return company_name in allowed_companies


class ExperienceLevelRule(TextRule):
    """Keep jobs that match at least one configured experience-level
    keyword list (intern, new grad, junior). If none of the three lists
    are configured, every job passes."""

    def __init__(
        self,
        intern_keywords: tuple[str, ...],
        new_grad_keywords: tuple[str, ...],
        junior_keywords: tuple[str, ...],
    ) -> None:
        self._level_lists = tuple(
            kws for kws in (intern_keywords, new_grad_keywords, junior_keywords) if kws
        )

    def matches(self, job: Any) -> bool:
        if not self._level_lists:
            return True

        text = self._job_text(job, ("title", "description", "department"))
        return any(
            any(self._contains_keyword(text, keyword) for keyword in keywords)
            for keywords in self._level_lists
        )


class RemoteRule(TextRule):
    """Keep jobs identifiable as remote, when remote filtering is enabled."""

    _REMOTE_KEYWORD = "remote"

    def __init__(self, remote: bool) -> None:
        self._remote = remote

    def matches(self, job: Any) -> bool:
        if not self._remote:
            return True

        text = self._job_text(job, ("location", "title", "description"))
        return self._contains_keyword(text, self._REMOTE_KEYWORD)


def build_default_rules(config: FilterConfig) -> tuple[BaseRule, ...]:
    """Build the default rule sequence in the recommended order."""

    return (
        CompanyRule(config.companies),
        LocationRule(config.locations),
        EmploymentTypeRule(config.employment_types),
        KeywordIncludeRule(config.include_keywords),
        KeywordExcludeRule(config.exclude_keywords),
        ExperienceLevelRule(
            config.intern_keywords,
            config.new_grad_keywords,
            config.junior_keywords,
        ),
        RemoteRule(config.remote),
    )