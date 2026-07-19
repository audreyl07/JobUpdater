"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""

    pass


class Company(Base):
    """Company being monitored for job postings."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    careers_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    scanner: Mapped[str] = mapped_column(String(100), nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    jobs: Mapped[list["JobRecord"]] = relationship(back_populates="company")
    scan_history: Mapped[list["ScanHistoryRecord"]] = relationship(back_populates="company")


class JobRecord(Base):
    """Stored job posting record."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    job_id: Mapped[str] = mapped_column(
        "external_job_id",  # Python attr is job_id; actual DB column is external_job_id
        String(255),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)

    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    department: Mapped[str | None] = mapped_column(String(255), nullable=True)

    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    remote: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    salary: Mapped[str | None] = mapped_column(String(255), nullable=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    posted_at: Mapped[datetime | None] = mapped_column(
        "posted_date",  # Python attr is posted_at; actual DB column is posted_date
        DateTime(timezone=True),
        nullable=True,
    )

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    company: Mapped["Company"] = relationship(back_populates="jobs")


class ScanHistoryRecord(Base):
    """Tracks scanner execution history."""

    __tablename__ = "scan_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    jobs_found: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    jobs_added: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    jobs_updated: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    jobs_removed: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="scan_history")