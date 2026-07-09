"""Tests for filter configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.filters.exceptions import (
    FilterConfigLoadError,
    FilterConfigValidationError,
)
from app.filters.loader import FilterConfigLoader
from app.filters.models import CompanyFilterConfig, FilterConfig


def test_empty_configuration_returns_defaults(tmp_path: Path) -> None:
    """An empty file should produce the default typed configuration."""

    path = tmp_path / "filters.yaml"
    path.write_text("", encoding="utf-8")

    config = FilterConfigLoader().load(path)

    assert config == FilterConfig()
    assert config.companies == CompanyFilterConfig()


def test_valid_yaml_is_loaded_as_typed_config(tmp_path: Path) -> None:
    """Valid YAML should be converted into typed configuration objects."""

    path = tmp_path / "filters.yaml"
    path.write_text(
        """
filters:
  include_keywords:
    - software
    - python
  exclude_keywords:
    - manager
  locations:
    - Ottawa
    - Remote
  employment_types:
    - Full Time
  companies:
    include:
      - Nokia
      - Kinaxis
""".strip(),
        encoding="utf-8",
    )

    config = FilterConfigLoader().load(path)

    assert config.include_keywords == ("software", "python")
    assert config.exclude_keywords == ("manager",)
    assert config.locations == ("Ottawa", "Remote")
    assert config.employment_types == ("Full Time",)
    assert config.companies == CompanyFilterConfig(include=("Nokia", "Kinaxis"))


def test_invalid_yaml_raises_load_error(tmp_path: Path) -> None:
    """Malformed YAML should raise a load error."""

    path = tmp_path / "filters.yaml"
    path.write_text(
        """
filters:
  include_keywords:
    - software
    - python
  locations: [
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(FilterConfigLoadError, match="Invalid YAML"):
        FilterConfigLoader().load(path)


def test_unknown_root_key_raises_validation_error(tmp_path: Path) -> None:
    """Unexpected keys should fail schema validation."""

    path = tmp_path / "filters.yaml"
    path.write_text("unknown: true\n", encoding="utf-8")

    with pytest.raises(FilterConfigValidationError, match="Unknown key"):
        FilterConfigLoader().load(path)


def test_filters_section_must_be_a_mapping(tmp_path: Path) -> None:
    """The filters section should be validated as a mapping."""

    path = tmp_path / "filters.yaml"
    path.write_text(
        """
filters: [1, 2, 3]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(FilterConfigValidationError, match="'filters' section must be a mapping"):
        FilterConfigLoader().load(path)