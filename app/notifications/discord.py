"""Discord notification provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from logging import Logger, getLogger
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.notifications.exceptions import DiscordNotificationError
from app.notifications.interfaces import NotificationProvider
from app.notifications.models import Notification


Transport = Callable[[str, bytes, float], int]


@dataclass(slots=True)
class DiscordProvider(NotificationProvider):
    """Send notifications to a Discord webhook."""

    webhook_url: str
    username: str = "Career Monitor"
    avatar_url: str | None = None
    timeout: float = 10.0
    logger: Logger | None = None
    transport: Transport | None = None

    def __post_init__(self) -> None:
        """Initialize defaults."""
        if self.logger is None:
            self.logger = getLogger(__name__)
        if self.transport is None:
            self.transport = self._default_transport

    def send(self, notification: Notification) -> None:
        """Send a notification to Discord."""
        payload = self._build_payload(notification)
        body = json.dumps(payload).encode("utf-8")

        try:
            status_code = self.transport(self.webhook_url, body, self.timeout)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception(
                "notification_error",
                extra={"provider": "discord", "title": notification.title},
            )
            raise DiscordNotificationError("Failed to send Discord notification") from exc

        if status_code < 200 or status_code >= 300:
            self.logger.error(
                "notification_error",
                extra={
                    "provider": "discord",
                    "title": notification.title,
                    "status_code": status_code,
                },
            )
            raise DiscordNotificationError(
                f"Discord webhook returned unexpected status code: {status_code}"
            )

        self.logger.info(
            "notification_sent",
            extra={"provider": "discord", "title": notification.title},
        )

    def _build_payload(self, notification: Notification) -> dict[str, Any]:
        """Build a Discord webhook payload."""
        embed: dict[str, Any] = {
            "title": notification.title,
            "description": notification.message,
        }

        if notification.url:
            embed["url"] = notification.url

        if notification.metadata:
            embed["fields"] = [
                {"name": key, "value": value, "inline": False}
                for key, value in notification.metadata.items()
            ]

        payload: dict[str, Any] = {
            "username": self.username,
            "embeds": [embed],
        }

        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        return payload

    def _default_transport(self, url: str, body: bytes, timeout: float) -> int:
        """Send the webhook using urllib."""
        request = urllib_request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                return int(getattr(response, "status", response.getcode()))
        except urllib_error.HTTPError as exc:
            return int(exc.code)