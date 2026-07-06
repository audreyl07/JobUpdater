"""YAML configuration loader and validator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.config.exceptions import ConfigurationError
from app.config.models import ApplicationConfig, CompanyConfig


class ConfigLoader:
    """Load and validate YAML configuration files."""

    def load(self, path: str | Path) -> ApplicationConfig:
        """Load configuration from a YAML file."""
        config_path = Path(path)

        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        try:
            raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML in {config_path}") from exc

        if not isinstance(raw_data, dict):
            raise ConfigurationError("Configuration root must be a mapping")

        companies = raw_data.get("companies")
        if not isinstance(companies, list) or not companies:
            raise ConfigurationError("'companies' must be a non-empty list")

        parsed_companies: list[CompanyConfig] = []
        for index, item in enumerate(companies):
            parsed_companies.append(self._parse_company(item, index))

        return ApplicationConfig(companies=tuple(parsed_companies))

    def _parse_company(self, item: Any, index: int) -> CompanyConfig:
        """Parse and validate a single company entry."""
        if not isinstance(item, dict):
            raise ConfigurationError(f"Company entry at index {index} must be a mapping")

        name = item.get("name")
        scanner = item.get("scanner")
        url = item.get("url")

        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(f"Company entry at index {index} requires a valid 'name'")
        if not isinstance(scanner, str) or not scanner.strip():
            raise ConfigurationError(f"Company entry at index {index} requires a valid 'scanner'")
        if not isinstance(url, str) or not url.strip():
            raise ConfigurationError(f"Company entry at index {index} requires a valid 'url'")

        return CompanyConfig(
            name=name.strip(),
            scanner=scanner.strip().lower(),
            url=url.strip(),
        )