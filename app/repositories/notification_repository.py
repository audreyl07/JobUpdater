from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.notification import Notification


class DuplicateNotificationError(RuntimeError):
    """Raised when a duplicate notification would be created."""


@dataclass(slots=True)
class NotificationRepository:
    """Repository for notification persistence and duplicate prevention."""

    session: Session

    def exists(self, *, job_id: int, notification_type: str) -> bool:
        stmt = select(Notification.id).where(
            Notification.job_id == job_id,
            Notification.notification_type == notification_type,
        )
        return self.session.scalar(stmt) is not None

    def get(self, notification_id: int) -> Notification | None:
        return self.session.get(Notification, notification_id)

    def create(self, *, job_id: int, notification_type: str) -> Notification:
        notification = Notification(job_id=job_id, notification_type=notification_type)
        self.session.add(notification)

        try:
            self.session.flush()
        except IntegrityError as exc:
            raise DuplicateNotificationError(
                "Notification already exists for this job and notification type."
            ) from exc

        return notification

    def create_if_missing(self, *, job_id: int, notification_type: str) -> Notification | None:
        if self.exists(job_id=job_id, notification_type=notification_type):
            return None
        return self.create(job_id=job_id, notification_type=notification_type)