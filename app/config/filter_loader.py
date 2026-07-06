"""YAML loader for job filtering rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.filtering.exceptions import FilterConfigurationError
from app.filtering.models import FilterRules


class FilterConfigLoader:
    """Load and validate filter rules from YAML."""

    def load(self, path: str | Path) -> FilterRules:
        """Load filter rules from a YAML file."""
        config_path = Path(path)

        if not config_path.exists():
            raise FilterConfigurationError(f"Filter configuration file not found: {config_path}")

        try:
            raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise FilterConfigurationError(f"Invalid YAML in {config_path}") from exc

        if not isinstance(raw_data, dict):
            raise FilterConfigurationError("Filter configuration root must be a mapping")

        filters = raw_data.get("filters", raw_data)
        if not isinstance(filters, dict):
            raise FilterConfigurationError("'filters' must be a mapping")

        return FilterRules(
            include_keywords=self._parse_string_list(filters.get("include_keywords"), "include_keywords"),
            exclude_keywords=self._parse_string_list(filters.get("exclude_keywords"), "exclude_keywords"),
            locations=self._parse_string_list(filters.get("locations"), "locations"),
            employment_types=self._parse_string_list(filters.get("employment_types"), "employment_types"),
            intern_keywords=self._parse_string_list(filters.get("intern_keywords"), "intern_keywords"),
            new_grad_keywords=self._parse_string_list(filters.get("new_grad_keywords"), "new_grad_keywords"),
            junior_keywords=self._parse_string_list(filters.get("junior_keywords"), "junior_keywords"),
            remote=self._parse_optional_bool(filters.get("remote")),
        )

    def _parse_string_list(self, value: Any, field_name: str) -> tuple[str, ...]:
        """Validate a list of strings."""
        if value is None:
            return ()

        if not isinstance(value, list):
            raise FilterConfigurationError(f"'{field_name}' must be a list of strings")

        parsed: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise FilterConfigurationError(f"'{field_name}' must contain only non-empty strings")
            parsed.append(item.strip())

        return tuple(parsed)

    def _parse_optional_bool(self, value: Any) -> bool | None:
        """Validate an optional boolean field."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        raise FilterConfigurationError("'remote' must be a boolean if provided")