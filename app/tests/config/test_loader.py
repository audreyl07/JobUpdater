"""Tests for the YAML configuration loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from career_monitor.config.exceptions import ConfigurationError
from career_monitor.config.loader import ConfigLoader


def test_load_valid_config(tmp_path: Path) -> None:
    config_file = tmp_path / "companies.yaml"
    config_file.write_text(
        """
companies:
  - name: Nokia
    scanner: workday
    url: https://example.com/nokia
""".strip(),
        encoding="utf-8",
    )

    config = ConfigLoader().load(config_file)

    assert config.company_count == 1
    assert config.companies[0].name == "Nokia"
    assert config.companies[0].scanner == "workday"


def test_missing_file_raises_error() -> None:
    with pytest.raises(ConfigurationError):
        ConfigLoader().load("does-not-exist.yaml")


def test_invalid_root_raises_error(tmp_path: Path) -> None:
    config_file = tmp_path / "companies.yaml"
    config_file.write_text("- not-a-mapping", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Configuration root must be a mapping"):
        ConfigLoader().load(config_file)


def test_missing_companies_raises_error(tmp_path: Path) -> None:
    config_file = tmp_path / "companies.yaml"
    config_file.write_text("foo: bar", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="'companies' must be a non-empty list"):
        ConfigLoader().load(config_file)