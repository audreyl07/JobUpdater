from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.job import Job


class Notification(Base):
    """Persisted notification record used to prevent duplicate alerts."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "notification_type",
            name="uq_notifications_job_id_notification_type",
        ),
        Index("ix_notifications_job_id", "job_id"),
        Index("ix_notifications_sent_at", "sent_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    job: Mapped[Job] = relationship()

    def __repr__(self) -> str:
        return (
            "Notification(id={!r}, job_id={!r}, notification_type={!r}, sent_at={!r})"
        ).format(self.id, self.job_id, self.notification_type, self.sent_at)