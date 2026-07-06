"""Tests for the filter configuration loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.filter_loader import FilterConfigLoader
from app.filtering.exceptions import FilterConfigurationError


def test_load_valid_filter_config(tmp_path: Path) -> None:
    config_file = tmp_path / "filters.yaml"
    config_file.write_text(
        """
filters:
  include_keywords:
    - python
  exclude_keywords:
    - intern
  locations:
    - Toronto
  remote: true
  employment_types:
    - full-time
""".strip(),
        encoding="utf-8",
    )

    rules = FilterConfigLoader().load(config_file)

    assert rules.include_keywords == ("python",)
    assert rules.exclude_keywords == ("intern",)
    assert rules.locations == ("Toronto",)
    assert rules.remote is True


def test_invalid_remote_type_raises_error(tmp_path: Path) -> None:
    config_file = tmp_path / "filters.yaml"
    config_file.write_text("filters:\n  remote: yes please", encoding="utf-8")

    with pytest.raises(FilterConfigurationError, match="'remote' must be a boolean"):
        FilterConfigLoader().load(config_file)