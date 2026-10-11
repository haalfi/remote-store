"""Where the sync runtime differs in kind, not by ``await``: stream and content shapes.

Hand-written in both runtimes; ``_async/_io.py`` is its counterpart, with the
same names. The generated modules beside this one import these.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from remote_store._kernel._sync.driver import WriteHandle

#: What ``get`` returns: the sync driver hands back a binary stream.
ReadStream = BinaryIO
#: What ``put`` and ``write_atomic`` accept.
Content = BinaryIO | bytes

_CHUNK = 256 * 1024


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


def feed(handle: WriteHandle, content: Content) -> None:
    """Write all of *content* into an open write handle."""
    if isinstance(content, bytes | bytearray | memoryview):
        handle.write(bytes(content))
        return
    while chunk := content.read(_CHUNK):
        handle.write(chunk)
