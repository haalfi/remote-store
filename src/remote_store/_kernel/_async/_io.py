"""Where the async runtime differs in kind, not by ``await``: stream and content shapes.

Hand-written in both runtimes; ``_sync/_io.py`` is its counterpart, with the
same names, which the generated modules import in place of these.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remote_store._kernel._async.driver import AsyncWriteHandle

#: What ``get`` returns: the async driver streams chunks.
ReadStream = AsyncIterator[bytes]
#: What ``put`` and ``write_atomic`` accept.
Content = bytes | AsyncIterator[bytes]


async def read_all(stream: ReadStream) -> bytes:
    """Drain *stream* into one ``bytes`` and close it."""
    try:
        return b"".join([chunk async for chunk in stream])
    finally:
        await close_stream(stream)


async def close_stream(stream: object) -> None:
    """Close a stream the kernel opened, if it can be closed."""
    aclose = getattr(stream, "aclose", None)
    if aclose is not None:
        await aclose()


async def feed(handle: AsyncWriteHandle, content: Content) -> None:
    """Write all of *content* into an open write handle."""
    if isinstance(content, bytes | bytearray | memoryview):
        await handle.write(bytes(content))
        return
    async for chunk in content:
        await handle.write(chunk)
