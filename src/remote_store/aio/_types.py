"""Type aliases for async remote_store operations."""

from __future__ import annotations

from collections.abc import AsyncIterator

AsyncWritableContent = bytes | AsyncIterator[bytes]
