"""Notification provider interface."""

from __future__ import annotations

from typing import Protocol

from app.notifications.models import Notification


class NotificationProvider(Protocol):
    """Protocol for notification providers."""

    def send(self, notification: Notification) -> None:
        """Send a notification."""