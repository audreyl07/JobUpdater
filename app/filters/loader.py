"""YAML loader for filter configuration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from app.filters.exceptions import (
    FilterConfigLoadError,
    FilterConfigValidationError,
)
from app.filters.models import CompanyFilterConfig, FilterConfig


class FilterConfigLoader:
    """Load and validate filter configuration from YAML."""

    def load(self, path: str | Path) -> FilterConfig:
        """Load filter configuration from a YAML file."""

        file_path = Path(path)

        try:
            raw_text = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FilterConfigLoadError(
                f"Unable to read filter configuration from '{file_path}': {exc}"
            ) from exc

        try:
            parsed = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise FilterConfigLoadError(
                f"Invalid YAML in filter configuration '{file_path}': {exc}"
            ) from exc

        if parsed is None:
            return FilterConfig()

        if not isinstance(parsed, Mapping):
            raise FilterConfigValidationError(
                "Filter configuration root must be a mapping."
            )

        self._validate_unknown_keys(
            parsed,
            allowed={"filters"},
            context="root",
        )

        filters_section = parsed.get("filters", {})
        if filters_section is None:
            filters_section = {}

        if not isinstance(filters_section, Mapping):
            raise FilterConfigValidationError(
                "'filters' section must be a mapping."
            )

        self._validate_unknown_keys(
            filters_section,
            allowed={
                "include_keywords",
                "exclude_keywords",
                "locations",
                "employment_types",
                "companies",
                "remote",
                "intern_keywords",
                "new_grad_keywords",
                "junior_keywords",
            },
            context="filters",
        )

        include_keywords = self._read_string_sequence(
            filters_section.get("include_keywords"),
            context="filters.include_keywords",
        )
        exclude_keywords = self._read_string_sequence(
            filters_section.get("exclude_keywords"),
            context="filters.exclude_keywords",
        )
        locations = self._read_string_sequence(
            filters_section.get("locations"),
            context="filters.locations",
        )
        employment_types = self._read_string_sequence(
            filters_section.get("employment_types"),
            context="filters.employment_types",
        )

        intern_keywords = self._read_string_sequence(
            filters_section.get("intern_keywords"),
            context="filters.intern_keywords",
        )
        new_grad_keywords = self._read_string_sequence(
            filters_section.get("new_grad_keywords"),
            context="filters.new_grad_keywords",
        )
        junior_keywords = self._read_string_sequence(
            filters_section.get("junior_keywords"),
            context="filters.junior_keywords",
        )

        remote_value = filters_section.get("remote")
        if remote_value is not None and not isinstance(remote_value, bool):
            raise FilterConfigValidationError(
                "'filters.remote' must be a boolean (true/false)."
            )
        remote = bool(remote_value) if remote_value is not None else False

        companies_section = filters_section.get("companies", {})
        if companies_section is None:
            companies_section = {}

        if not isinstance(companies_section, Mapping):
            raise FilterConfigValidationError(
                "'filters.companies' must be a mapping."
            )

        self._validate_unknown_keys(
            companies_section,
            allowed={"include"},
            context="filters.companies",
        )

        company_config = CompanyFilterConfig(
            include=self._read_string_sequence(
                companies_section.get("include"),
                context="filters.companies.include",
            )
        )

        return FilterConfig(
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            locations=locations,
            employment_types=employment_types,
            companies=company_config,
            intern_keywords=intern_keywords,
            new_grad_keywords=new_grad_keywords,
            junior_keywords=junior_keywords,
            remote=remote,
        )

    def _read_string_sequence(self, value: Any, *, context: str) -> tuple[str, ...]:
        if value is None:
            return ()

        if isinstance(value, str):
            raise FilterConfigValidationError(
                f"'{context}' must be a list of strings, not a single string."
            )

        if not isinstance(value, Sequence):
            raise FilterConfigValidationError(
                f"'{context}' must be a list of strings."
            )

        items: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise FilterConfigValidationError(
                    f"'{context}[{index}]' must be a string."
                )

            normalized = item.strip()
            if normalized:
                items.append(normalized)

        return tuple(items)

    def _validate_unknown_keys(
        self,
        mapping: Mapping[str, Any],
        *,
        allowed: set[str],
        context: str,
    ) -> None:
        unknown = set(mapping.keys()) - allowed
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            raise FilterConfigValidationError(
                f"Unknown key(s) in '{context}': {unknown_list}"
            )