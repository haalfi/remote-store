"""Shared test helpers."""

from __future__ import annotations

import io

# Re-export from infra._settings so MinIO credentials change in exactly
# one place (infra/.env). Names kept stable for existing callers.
from infra._settings import MINIO_ACCESS_KEY as MINIO_KEY
from infra._settings import MINIO_SECRET_KEY as MINIO_SECRET

__all__ = ["MINIO_KEY", "MINIO_SECRET", "FailingContentReader", "pyarrow_ge_24"]


class FailingContentReader(io.RawIOBase):
    """Content source that delivers ``fill`` NUL bytes then raises mid-stream.

    Models a content producer (socket, generator, upstream stream) that fails
    partway through a write. Used by the BUG-214 atomicity tests to assert that
    ``write`` / ``write_atomic`` do not commit a truncated object when the
    source raises. ``buffered()`` wraps it in a ``BufferedReader`` so callers
    that read in fixed chunks get the standard buffered interface.
    """

    def __init__(self, fill: int) -> None:
        super().__init__()
        self._remaining = fill

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        if self._remaining <= 0:
            raise ConnectionResetError("simulated mid-stream content failure")
        n = min(len(b), self._remaining)
        b[:n] = bytes(n)
        self._remaining -= n
        return n

    @classmethod
    def buffered(cls, fill: int) -> io.BufferedReader:
        """Return a ``BufferedReader`` wrapping a ``FailingContentReader``."""
        return io.BufferedReader(cls(fill))


def pyarrow_ge_24() -> bool:
    """Return True if pyarrow is installed and its major version is >= 24."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return int(version("pyarrow").split(".")[0]) >= 24
    except PackageNotFoundError:
        return False
