"""Job filtering engine."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger, getLogger
from typing import Iterable, Sequence

from app.filtering.models import FilterRules


@dataclass(slots=True)
class FilterEngine:
    """Apply configured filter rules to jobs."""

    rules: FilterRules
    logger: Logger | None = None

    def __post_init__(self) -> None:
        """Initialize defaults."""
        if self.logger is None:
            self.logger = getLogger(__name__)

    def filter_jobs(self, jobs: Iterable[object]) -> list[object]:
        """Return only jobs that match all configured rules."""
        jobs_list = list(jobs)
        filtered_jobs = [job for job in jobs_list if self._matches(job)]

        self.logger.info(
            "jobs_filtered",
            extra={"jobs_in": len(jobs_list), "jobs_out": len(filtered_jobs)},
        )
        return filtered_jobs

    def _matches(self, job: object) -> bool:
        """Check whether a job matches all active filters."""
        haystack = self._job_haystack(job)

        if self.rules.include_keywords and not self._contains_any(haystack, self.rules.include_keywords):
            return False

        if self.rules.exclude_keywords and self._contains_any(haystack, self.rules.exclude_keywords):
            return False

        if self.rules.locations and not self._field_contains_any(job, "location", self.rules.locations):
            return False

        if self.rules.employment_types and not self._field_contains_any(
            job, "employment_type", self.rules.employment_types
        ):
            return False

        if self.rules.remote is not None and not self._matches_remote(job, self.rules.remote):
            return False

        seniority_groups: Sequence[tuple[str, tuple[str, ...]]] = (
            ("intern_keywords", self.rules.intern_keywords),
            ("new_grad_keywords", self.rules.new_grad_keywords),
            ("junior_keywords", self.rules.junior_keywords),
        )
        active_groups = [keywords for _, keywords in seniority_groups if keywords]
        if active_groups and not any(self._contains_any(haystack, keywords) for keywords in active_groups):
            return False

        return True

    def _job_haystack(self, job: object) -> str:
        """Build searchable text from available job fields."""
        parts = [
            self._get_text_field(job, "title"),
            self._get_text_field(job, "location"),
            self._get_text_field(job, "employment_type"),
            self._get_text_field(job, "description"),
            self._get_text_field(job, "company"),
        ]
        return " ".join(part for part in parts if part).lower()

    def _field_contains_any(self, job: object, field_name: str, keywords: tuple[str, ...]) -> bool:
        """Check whether a job field contains any keyword."""
        value = self._get_text_field(job, field_name).lower()
        return self._contains_any(value, keywords)

    def _matches_remote(self, job: object, expected: bool) -> bool:
        """Check whether the remote flag matches."""
        value = getattr(job, "remote", None)
        if isinstance(value, bool):
            return value is expected

        text = self._job_haystack(job)
        is_remote = "remote" in text
        return is_remote is expected

    def _contains_any(self, text: str, keywords: tuple[str, ...]) -> bool:
        """Return True if text contains any keyword."""
        normalized = text.lower()
        return any(keyword.strip().lower() in normalized for keyword in keywords if keyword.strip())

    def _get_text_field(self, job: object, field_name: str) -> str:
        """Safely read a string field from a job object."""
        value = getattr(job, field_name, "")
        return value if isinstance(value, str) else ""