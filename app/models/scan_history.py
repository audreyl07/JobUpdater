from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class ScanHistory(Base):
    """Persisted audit record for one company scan."""

    __tablename__ = "scan_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    scanner_version: Mapped[str] = mapped_column(String(50), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped[Company] = relationship(back_populates="scan_history")

    def __repr__(self) -> str:
        return (
            "ScanHistory(id={!r}, company_id={!r}, started_at={!r}, success={!r})"
        ).format(self.id, self.company_id, self.started_at, self.success)