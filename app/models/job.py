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
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Company


class JobStatus:
    """Canonical persisted job status values."""

    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"
    EXPIRED = "EXPIRED"


@dataclass(slots=True)
class Job:
    """Standardized job record returned by scanners."""

    job_id: str
    title: str
    company: str
    location: str
    department: str | None = None
   #  employment_type: EmploymentType = EmploymentType.UNKNOWN
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


class Job(Base):
    """Persisted normalized job posting."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("company_id", "external_job_id", name="uq_jobs_company_external_job_id"),
        Index("ix_jobs_company_id_status", "company_id", "status"),
        Index("ix_jobs_last_seen", "last_seen"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remote: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    salary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JobStatus.ACTIVE,
        server_default=JobStatus.ACTIVE,
        index=False,
    )

    company: Mapped[Company] = relationship(back_populates="jobs")
    hash_record: Mapped[JobHash | None] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        uselist=False,
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            "Job(id={!r}, company_id={!r}, external_job_id={!r}, title={!r}, status={!r})"
        ).format(self.id, self.company_id, self.external_job_id, self.title, self.status)


class JobHash(Base):
    """Stored content hash for change detection."""

    __tablename__ = "job_hashes"

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    job: Mapped[Job] = relationship(back_populates="hash_record")

    def __repr__(self) -> str:
        return f"JobHash(job_id={self.job_id!r}, content_hash={self.content_hash!r})"

