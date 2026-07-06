"""Database exceptions."""

from __future__ import annotations


class DatabaseError(Exception):
    """Raised when database operations fail."""


class RepositoryError(DatabaseError):
    """Raised when a repository operation cannot be completed."""