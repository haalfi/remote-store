"""Stream-level wrappers for progress tracking and checksum computation.

Composable ``BinaryIO`` wrappers that operate at the stream level, not the
Store level.  No proxy wrapping is needed — just wrap the stream returned
by ``store.read()`` or passed to ``store.write()``.

!!! example

    ```python
    from remote_store.ext.streams import ProgressReader, ChecksumReader

    stream = ChecksumReader(
        ProgressReader(store.read("file.bin"), callback=update_bar),
        algorithm="sha256",
    )
    data = stream.read()
    assert stream.hexdigest() == expected_hex
    ```
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import BinaryIO

    from typing_extensions import Self

    from remote_store._store import Store

__all__ = [
    "ChecksumReader",
    "ChecksumWriter",
    "ProgressReader",
    "ProgressWriter",
    "read_with_progress",
]


class _StreamWrapper:
    """Base for composable ``BinaryIO`` wrappers.

    Provides close, context-manager protocol, and attribute delegation.
    Subclasses override data-path methods (``read``, ``write``, etc.).
    """

    _inner: BinaryIO

    def close(self) -> None:
        self._inner.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        return getattr(self._inner, name)


class ProgressReader(_StreamWrapper):
    """Readable ``BinaryIO`` wrapper that fires a callback per ``read()``.

    The callback receives the number of bytes read (not cumulative).
    Empty reads do not fire the callback.

    Args:
        inner: Readable binary stream to wrap.
        callback: Called with ``len(data)`` after each non-empty ``read()``.
    """

    def __init__(self, inner: BinaryIO, callback: Callable[[int], None]) -> None:
        self._inner = inner
        self._callback = callback

    def read(self, size: int = -1) -> bytes:
        data = self._inner.read(size)
        if data:
            self._callback(len(data))
        return data


class ProgressWriter(_StreamWrapper):
    """Writable ``BinaryIO`` wrapper that fires a callback per ``write()``.

    The callback receives the number of bytes written (not cumulative).
    Empty writes do not fire the callback.

    Note:
        Assumes buffered I/O semantics — ``write()`` consumes all data or
        raises.  Wrapping a ``RawIOBase`` (partial-write) stream would cause
        the reported byte count to diverge from the bytes actually written.

    Args:
        inner: Writable binary stream to wrap.
        callback: Called with ``len(data)`` after each non-empty ``write()``.
    """

    def __init__(self, inner: BinaryIO, callback: Callable[[int], None]) -> None:
        self._inner = inner
        self._callback = callback

    def write(self, data: bytes | bytearray) -> int:
        result = self._inner.write(data)
        if data:
            self._callback(len(data))
        return result


class ChecksumReader(_StreamWrapper):
    """Readable ``BinaryIO`` wrapper that computes a rolling hash.

    Args:
        inner: Readable binary stream to wrap.
        algorithm: Hash algorithm name (default ``"sha256"``).
            Must be supported by ``hashlib``.
    """

    def __init__(self, inner: BinaryIO, algorithm: str = "sha256") -> None:
        self._inner = inner
        self._algorithm = algorithm.lower()
        self._hash = hashlib.new(self._algorithm)

    @property
    def algorithm(self) -> str:
        """Hash algorithm name (lowercase)."""
        return self._algorithm

    def read(self, size: int = -1) -> bytes:
        data = self._inner.read(size)
        if data:
            self._hash.update(data)
        return data

    def readline(self, size: int = -1) -> bytes:
        data = self._inner.readline(size)
        if data:
            self._hash.update(data)
        return data

    def readlines(self, hint: int = -1) -> list[bytes]:
        lines = self._inner.readlines(hint)
        for line in lines:
            self._hash.update(line)
        return lines

    def hexdigest(self) -> str:
        """Return the lowercase hex digest of all bytes read so far."""
        return self._hash.hexdigest()


class ChecksumWriter(_StreamWrapper):
    """Writable ``BinaryIO`` wrapper that computes a rolling hash.

    Note:
        Assumes buffered I/O semantics — ``write()`` consumes all data or
        raises.  Wrapping a ``RawIOBase`` (partial-write) stream would cause
        the hash to include bytes that were not actually written.

    Args:
        inner: Writable binary stream to wrap.
        algorithm: Hash algorithm name (default ``"sha256"``).
            Must be supported by ``hashlib``.
    """

    def __init__(self, inner: BinaryIO, algorithm: str = "sha256") -> None:
        self._inner = inner
        self._algorithm = algorithm.lower()
        self._hash = hashlib.new(self._algorithm)

    @property
    def algorithm(self) -> str:
        """Hash algorithm name (lowercase)."""
        return self._algorithm

    def write(self, data: bytes | bytearray) -> int:
        result = self._inner.write(data)
        if data:
            self._hash.update(data)
        return result

    def hexdigest(self) -> str:
        """Return the lowercase hex digest of all bytes written so far."""
        return self._hash.hexdigest()


def read_with_progress(
    store: Store,
    path: str,
    callback: Callable[[int], None],
) -> ProgressReader:
    """Read a file with progress tracking.

    Convenience wrapper around ``ProgressReader(store.read(path), callback)``.
    The caller is responsible for closing the returned stream.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        callback: Called with byte count after each non-empty ``read()``.

    Returns:
        A ``ProgressReader`` wrapping the store's read stream.
    """
    return ProgressReader(store.read(path), callback)
