"""Filtering engine for job objects."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.filters.models import FilterConfig
from app.filters.rules import BaseRule, build_default_rules


class FilterEngine:
    """Apply a sequence of rules to jobs and keep accepted results."""

    def __init__(
        self,
        rules: Sequence[BaseRule] | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._rules = tuple(rules or ())
        self._logger = logger or logging.getLogger(__name__)

    @classmethod
    def from_config(
        cls,
        config: FilterConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> "FilterEngine":
        """Build a filter engine from typed configuration."""
        return cls(build_default_rules(config), logger=logger)

    def filter_jobs(self, jobs: Sequence[Any]) -> list[Any]:
        """Return only jobs that pass all configured rules."""
        received = len(jobs)
        accepted_jobs: list[Any] = []
        rejected_count = 0
        rule_failures: dict[str, int] = {}

        for job in jobs:
            if self._job_passes(job, rule_failures):
                accepted_jobs.append(job)
            else:
                rejected_count += 1

        accepted_count = len(accepted_jobs)

        self._logger.info("Received: %s jobs", received)
        self._logger.info("Accepted: %s", accepted_count)
        self._logger.info("Rejected: %s", rejected_count)
        self._logger.info(
            "Summary: received=%s accepted=%s rejected=%s",
            received,
            accepted_count,
            rejected_count,
        )

        for rule_name, count in sorted(rule_failures.items()):
            self._logger.info("Rule failures: %s=%s", rule_name, count)

        return accepted_jobs

    def _job_passes(self, job: Any, rule_failures: dict[str, int]) -> bool:
        for rule in self._rules:
            if rule.matches(job):
                continue

            rule_name = rule.__class__.__name__
            rule_failures[rule_name] = rule_failures.get(rule_name, 0) + 1
            self._logger.debug("Rejected job by %s", rule_name)
            return False

        return True