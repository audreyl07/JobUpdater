"""Filtering models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FilterRules:
    """Validated filtering rules loaded from YAML."""

    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    intern_keywords: tuple[str, ...] = ()
    new_grad_keywords: tuple[str, ...] = ()
    junior_keywords: tuple[str, ...] = ()
    remote: bool | None = None