"""
Structured logging setup.

We centralize logger configuration here so every module does
`from app.utils.logger import get_logger` and gets consistent,
structured output - instead of each file calling
`logging.basicConfig()` differently (or not at all).

Why structured (key=value) fields instead of pure prose:
  The spec's example log lines ("Found 254 jobs", "New jobs: 3") are
  fine for a human tailing a terminal, but this app is meant to run
  under a scheduler eventually. Structured fields (`event=`, `company=`,
  `count=`) make these lines greppable/parseable by log aggregators
  (e.g. CloudWatch, Datadog) without a human reading every line.
  We still keep a human-readable message as the first part of the line.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def _configure_root() -> None:
    """Configure the root handler exactly once per process.

    Guarded by a module-level flag rather than relying on
    `logging.basicConfig`'s own "no-op if handlers exist" behavior,
    so behavior is explicit and not dependent on import order.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger.

    Usage: `logger = get_logger(__name__)` at the top of a module.
    """
    _configure_root()
    return logging.getLogger(name)


def kv(**fields) -> str:
    """Format keyword args as `key=value key2=value2` for structured logs.

    Example:
        logger.info("Scan complete " + kv(company="IBM", found=254, new=3))
        -> "Scan complete company=IBM found=254 new=3"

    Values containing whitespace are quoted so the line stays
    machine-parsable on whitespace splitting.
    """
    parts = []
    for key, value in fields.items():
        text = str(value)
        if " " in text:
            text = f'"{text}"'
        parts.append(f"{key}={text}")
    return " ".join(parts)
