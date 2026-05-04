"""Shared helpers used across graph nodes and workers (DRY refactor)."""

from app.core.state import is_cancelled


def check_cancelled(session_id: str) -> None:
    """Raise RuntimeError if the session has been cancelled by user."""
    if is_cancelled(session_id):
        raise RuntimeError("Task cancelled by user")
