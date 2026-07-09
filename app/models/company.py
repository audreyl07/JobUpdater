from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.scan_history import ScanHistory


class Company(Base, TimestampMixin):
    """Persisted career site company configuration."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    scanner_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    careers_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    jobs: Mapped[list[Job]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    scan_history: Mapped[list[ScanHistory]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"Company(id={self.id!r}, name={self.name!r}, scanner_type={self.scanner_type!r})"