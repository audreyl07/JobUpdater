"""Notification models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class NotificationField:
    """An extra field shown in a notification."""

    name: str
    value: str
    inline: bool = False


@dataclass(frozen=True, slots=True)
class Notification:
    """A provider-agnostic notification payload."""

    title: str
    message: str
    url: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)