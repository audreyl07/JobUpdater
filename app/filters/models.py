"""Typed models for job filtering configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CompanyFilterConfig:
    """Company-based filter configuration."""

    include: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FilterConfig:
    """Root filter configuration."""

    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    companies: CompanyFilterConfig = field(default_factory=CompanyFilterConfig)
    intern_keywords: tuple[str, ...] = ()
    new_grad_keywords: tuple[str, ...] = ()
    junior_keywords: tuple[str, ...] = ()
    remote: bool = False