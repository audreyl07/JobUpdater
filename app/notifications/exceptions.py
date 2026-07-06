"""Notification exceptions."""

from __future__ import annotations


class NotificationError(Exception):
    """Raised when notification delivery fails."""


class DiscordNotificationError(NotificationError):
    """Raised when a Discord notification cannot be sent."""