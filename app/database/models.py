"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""

    pass


class JobRecord(Base):
    """Stored job posting record."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    job_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    company: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    location: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    employment_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    remote: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )


class ScanHistoryRecord(Base):
    """Tracks scanner execution history."""

    __tablename__ = "scan_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    company: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    scanner: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    jobs_found: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    jobs_filtered: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="running",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )