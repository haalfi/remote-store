"""Error-mapping stream wrapper for lazy reads."""

from __future__ import annotations

import contextlib
import io
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from remote_store._errors import RemoteStoreError


class _ErrorMappingStream(io.RawIOBase):
    """Wraps a BinaryIO stream and maps I/O exceptions through a classifier.

    When the caller reads from a stream returned by ``Backend.read()``, the
    backend's ``_errors()`` context manager has already exited.  Any native
    ``OSError`` raised during ``stream.read()`` would leak unmapped.  This
    wrapper intercepts I/O methods and passes ``OSError`` subclasses through
    the backend's error classifier so callers see ``RemoteStoreError`` subtypes.

    Programming errors (``TypeError``, ``ValueError``, ``AttributeError``, etc.)
    are **not** caught -- they propagate normally.

    :param inner: The underlying stream to wrap.
    :param mapper: ``(Exception, str) -> RemoteStoreError`` callable.
    :param path: The logical path, forwarded to *mapper* for diagnostics.
    """

    def __init__(
        self,
        inner: Any,
        mapper: Callable[[Exception, str], RemoteStoreError],
        path: str,
    ) -> None:
        self._inner = inner
        self._mapper = mapper
        self._path = path

    # -- RawIOBase required --

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        try:
            return self._inner.readinto(b)  # type: ignore[no-any-return]
        except OSError as exc:
            raise self._mapper(exc, self._path) from exc

    # -- Optional but expected --

    def read(self, size: int = -1) -> bytes | None:
        try:
            data = self._inner.read(size)
            return data  # type: ignore[no-any-return]
        except OSError as exc:
            raise self._mapper(exc, self._path) from exc

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        try:
            data = self._inner.readline(size)
            return data  # type: ignore[no-any-return]
        except OSError as exc:
            raise self._mapper(exc, self._path) from exc

    def seek(self, offset: int, whence: int = 0) -> int:
        try:
            return int(self._inner.seek(offset, whence))
        except OSError as exc:
            raise self._mapper(exc, self._path) from exc

    def seekable(self) -> bool:
        return bool(getattr(self._inner, "seekable", lambda: False)())

    def tell(self) -> int:
        try:
            return int(self._inner.tell())
        except OSError as exc:
            raise self._mapper(exc, self._path) from exc

    def close(self) -> None:
        if not self.closed:
            with contextlib.suppress(Exception):
                self._inner.close()
            super().close()

    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        try:
            line = self._inner.readline()
            if not line:
                raise StopIteration
            return line  # type: ignore[no-any-return]
        except StopIteration:
            raise
        except OSError as exc:
            raise self._mapper(exc, self._path) from exc
