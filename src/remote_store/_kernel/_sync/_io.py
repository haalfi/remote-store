"""Where the sync runtime differs in kind, not by ``await``: stream and content shapes.

Hand-written in both runtimes; ``_async/_io.py`` is its counterpart, with the
same names. The generated modules beside this one import these. Neither
imports the driver module, which imports them.
"""

from __future__ import annotations

import contextlib
from typing import BinaryIO, Protocol, cast

#: What ``get`` returns: the sync driver hands back a binary stream.
ReadStream = BinaryIO
#: What ``put`` and ``write_atomic`` accept.
Content = BinaryIO | bytes

_CHUNK = 256 * 1024


class _Writable(Protocol):
    """The part of a driver's write handle ``feed`` uses."""

    def write(self, data: bytes) -> None: ...


def read_all(stream: ReadStream) -> bytes:
    """Drain *stream* into one ``bytes`` and close it."""
    try:
        return stream.read()
    finally:
        close_stream(stream)


def close_stream(stream: object) -> None:
    """Close a stream the kernel opened, if it can be closed."""
    close = getattr(stream, "close", None)
    if close is not None:
        close()


_FROM_CONTENT = "_remote_store_from_content"


def from_content(exc: BaseException) -> bool:
    """Whether *exc* was raised by the caller's own content, not by the wire."""
    return bool(getattr(exc, _FROM_CONTENT, False))


def _mark(exc: BaseException) -> None:
    # An exception class that refuses new attributes stays unmarked, and is mapped.
    with contextlib.suppress(AttributeError):
        setattr(exc, _FROM_CONTENT, True)


class _MarkedReader:
    """The caller's stream, with whatever its reads raise marked as the caller's.

    Every other attribute is the stream's own.
    """

    __slots__ = ("_stream",)

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def _call(self, name: str, *args: object) -> object:
        try:
            return getattr(self._stream, name)(*args)
        except Exception as exc:
            _mark(exc)
            raise

    def read(self, size: int = -1) -> bytes:
        return self._call("read", size)  # type: ignore[return-value]

    def read1(self, size: int = -1) -> bytes:
        return self._call("read1", size)  # type: ignore[return-value]

    def readinto(self, buffer: bytearray | memoryview) -> int:
        return self._call("readinto", buffer)  # type: ignore[return-value]

    def readline(self, size: int = -1) -> bytes:
        return self._call("readline", size)  # type: ignore[return-value]

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


def guard_content(content: Content) -> Content:
    """*content* with whatever the caller's stream raises marked as the caller's.

    The choke point passes a marked error through verbatim: a failing source
    the caller handed in is not a wire error to classify.
    """
    if isinstance(content, bytes | bytearray | memoryview):
        return content
    return cast("BinaryIO", _MarkedReader(content))


def feed(handle: _Writable, content: Content) -> None:
    """Write all of *content* into an open write handle."""
    if isinstance(content, bytes | bytearray | memoryview):
        handle.write(bytes(content))
        return
    while chunk := content.read(_CHUNK):
        handle.write(chunk)
