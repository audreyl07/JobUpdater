"""Eager validation for DATABASE_URL, and the config surface for it.

I don't have your actual `models.py` (with `ApplicationConfig` /
`CompanyConfig`) in this conversation, so I can't safely patch it in place
without risking clobbering fields I can't see. Instead:

  1. This file owns the validation logic and is safe to drop in as-is.
  2. `app/db/engine.py` (your existing file) should import
     `get_validated_database_url` from here instead of reading
     `os.environ["DATABASE_URL"]` directly, so validation always
     happens through one path — this is also what `alembic/env.py`
     (file 3b) imports.
  3. Merge the `DatabaseConfig` dataclass into your existing config
     module by adding one field to `ApplicationConfig`:

        from app.core.database_config import DatabaseConfig

        @dataclass
        class ApplicationConfig:
            ...  # your existing fields
            database: DatabaseConfig = field(default_factory=DatabaseConfig.from_env)

     If `ApplicationConfig` already loads from env/YAML elsewhere, tell me
     the actual loading pattern and I'll adjust step 3 to match instead of
     guessing at `from_env`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from os import environ

_VALID_PREFIX = "postgresql+psycopg://"


class DatabaseConfigError(Exception):
    """Raised when DATABASE_URL is missing or malformed."""


def _redact(url: str) -> str:
    """Strip credentials from a DB URL before it appears in any log/error."""
    return re.sub(r"(postgresql\+psycopg://)[^@/]+@", r"\1***:***@", url)


def validate_database_url(url: str | None) -> str:
    """Eagerly validate a DATABASE_URL string.

    Raises DatabaseConfigError if:
      - url is None or empty
      - url does not start with "postgresql+psycopg://"

    Returns the validated URL unchanged (never redacted — redaction is
    only for display/logging, callers still need the real credentials
    to connect).
    """
    if not url:
        raise DatabaseConfigError(
            "DATABASE_URL is not set. Expected a value starting with "
            f"'{_VALID_PREFIX}'."
        )
    if not url.startswith(_VALID_PREFIX):
        raise DatabaseConfigError(
            f"DATABASE_URL must start with '{_VALID_PREFIX}' "
            f"(got: {_redact(url)})"
        )
    return url


def get_validated_database_url() -> str:
    """Read and validate DATABASE_URL from the environment.

    This is the single entry point app/db/engine.py and alembic/env.py
    should both call, so app startup and migrations can never disagree
    about what counts as a valid connection string.
    """
    return validate_database_url(environ.get("DATABASE_URL"))


@dataclass(frozen=True)
class DatabaseConfig:
    """Persistence-related config, merged into ApplicationConfig."""

    url: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Build a validated DatabaseConfig from the environment.

        Raises DatabaseConfigError at startup (not at first query time)
        if DATABASE_URL is missing or malformed, per the "validate
        eagerly at startup" requirement.
        """
        return cls(url=get_validated_database_url())

    def redacted(self) -> str:
        """Safe-to-log representation with credentials stripped."""
        return _redact(self.url)