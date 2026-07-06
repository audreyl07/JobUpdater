"""Tests for the Discord notification provider."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app.notifications.discord import DiscordProvider
from app.notifications.exceptions import DiscordNotificationError
from app.notifications.models import Notification


@dataclass
class TransportCapture:
    """Capture outbound webhook calls without using the network."""

    status_code: int = 204
    should_fail: bool = False
    url: str | None = None
    body: bytes | None = None
    timeout: float | None = None

    def __call__(self, url: str, body: bytes, timeout: float) -> int:
        self.url = url
        self.body = body
        self.timeout = timeout
        if self.should_fail:
            raise RuntimeError("network down")
        return self.status_code


def test_send_builds_expected_payload() -> None:
    transport = TransportCapture()
    provider = DiscordProvider(
        webhook_url="https://discord.com/api/webhooks/test",
        transport=transport,
    )

    provider.send(
        Notification(
            title="New job found",
            message="Python Backend Engineer",
            url="https://example.com/job/123",
            metadata={"company": "Nokia", "location": "Toronto"},
        )
    )

    assert transport.url == "https://discord.com/api/webhooks/test"
    assert transport.timeout == 10.0
    assert transport.body is not None

    payload = json.loads(transport.body.decode("utf-8"))
    assert payload["username"] == "Career Monitor"
    assert payload["embeds"][0]["title"] == "New job found"
    assert payload["embeds"][0]["description"] == "Python Backend Engineer"
    assert payload["embeds"][0]["url"] == "https://example.com/job/123"
    assert len(payload["embeds"][0]["fields"]) == 2


def test_send_raises_on_transport_error() -> None:
    provider = DiscordProvider(
        webhook_url="https://discord.com/api/webhooks/test",
        transport=TransportCapture(should_fail=True),
    )

    with pytest.raises(DiscordNotificationError, match="Failed to send Discord notification"):
        provider.send(Notification(title="New job found", message="Python Backend Engineer"))


def test_send_raises_on_non_2xx_status() -> None:
    provider = DiscordProvider(
        webhook_url="https://discord.com/api/webhooks/test",
        transport=TransportCapture(status_code=500),
    )

    with pytest.raises(DiscordNotificationError, match="unexpected status code: 500"):
        provider.send(Notification(title="New job found", message="Python Backend Engineer"))