"""Configuration models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CompanyConfig:
    """Validated company scanner configuration."""

    name: str
    scanner: str 
    url: str


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Validated application configuration."""

    companies: tuple[CompanyConfig, ...]

    @property
    def company_count(self) -> int:
        """Return the number of configured companies."""
        return len(self.companies)

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the config."""
        return {
            "companies": [
                {"name": c.name, "scanner": c.scanner, "url": c.url}
                for c in self.companies
            ]
        }