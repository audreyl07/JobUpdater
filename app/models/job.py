"""
Normalized Job model.

Every scanner in this application (IBM, Cisco, Nokia, ...) must return a
list of `Job` objects. Scanners are FORBIDDEN from leaking raw,
company-specific API/HTML shapes past their own `normalize()` method.
This is what makes the rest of the system (filters, database, scheduler,
notifications) company-agnostic.

Design notes:
- We use a `dataclass` rather than plain dicts so that:
    * Every required field is documented in one place.
    * Typos in field names become import-time/attribute errors, not
      silent `None`s discovered in production.
    * IDEs and type checkers (mypy) can catch mistakes in scanners.
- Every field from the spec is present. Fields that a given company does
  not expose MUST be set to `None` explicitly - never omitted - so that
  downstream code (filters, DB writes) can rely on the attribute always
  existing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EmploymentType(str, Enum):
    """Normalized employment type values."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERN = "intern"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Job:
    """Standardized job record returned by scanners."""

    job_id: str
    title: str
    company: str
    location: str
    department: str | None = None
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    posted_date: datetime | None = None
    url: str = ""
    description: str | None = None

    # Populated by the repository layer on insert; not set by scanners.
    # first_seen_at: Optional[datetime] = field(default=None, compare=False)

    def dedupe_key(self) -> tuple[str, str]:
        """The (company, job_id) tuple used everywhere for identity/duplicate checks."""
        return (self.company, self.job_id)

    def to_dict(self) -> dict:
        """Serialize to a plain dict (e.g. for logging or JSON APIs).

        Kept explicit rather than `dataclasses.asdict()` so enum/datetime
        fields are serialized to JSON-safe primitives in one place.
        """
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "department": self.department,
            "employment_type": self.employment_type.value,
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "url": self.url,
            "description": self.description,
        }

