"""Exceptions for the filtering subsystem."""

from __future__ import annotations


class FilterError(Exception):
    """Base class for filter-related errors."""


class FilterConfigError(FilterError):
    """Raised when filter configuration is invalid."""


class FilterConfigLoadError(FilterConfigError):
    """Raised when filter configuration cannot be loaded."""


class FilterConfigValidationError(FilterConfigError):
    """Raised when filter configuration fails validation."""