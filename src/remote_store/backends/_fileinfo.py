"""Shared helpers for constructing FileInfo from backend-native metadata."""

from __future__ import annotations

from datetime import UTC, datetime

from remote_store._models import _UNKNOWN_MODIFIED_AT


def _name_from_path(path: str) -> str:
    """Extract the file or folder name from a slash-delimited path."""
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _normalize_modified(value: str | datetime | None) -> datetime:
    """Parse, make timezone-aware, or fall back to the unknown-time sentinel."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value or _UNKNOWN_MODIFIED_AT


def _clean_etag(raw: str | None) -> str | None:
    """Strip double-quotes and lowercase an ETag string."""
    return raw.strip('"').lower() if isinstance(raw, str) else None
