"""Where the async runtime differs in kind, not by ``await``: stream and content shapes.

Hand-written in both runtimes; ``_sync/_io.py`` is its counterpart, with the
same names, which the generated modules import in place of these. Neither
imports the driver module, which imports them.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Protocol

#: What ``get`` returns: the async driver streams chunks.
ReadStream = AsyncIterator[bytes]
#: What ``put`` and ``write_atomic`` accept.
Content = bytes | AsyncIterator[bytes]


class _Writable(Protocol):
    """The part of a driver's write handle ``feed`` uses."""

    async def write(self, data: bytes) -> None: ...


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


_FROM_CONTENT = "_remote_store_from_content"


def from_content(exc: BaseException) -> bool:
    """Whether *exc* was raised by the caller's own content, not by the wire."""
    return bool(getattr(exc, _FROM_CONTENT, False))


def _mark(exc: BaseException) -> None:
    # An exception class that refuses new attributes stays unmarked, and is mapped.
    with contextlib.suppress(AttributeError):
        setattr(exc, _FROM_CONTENT, True)


async def _marked(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    iterator = chunks.__aiter__()
    while True:
        try:
            chunk = await iterator.__anext__()
        except StopAsyncIteration:
            return
        except Exception as exc:
            _mark(exc)
            raise
        yield chunk


def guard_content(content: Content) -> Content:
    """*content* with whatever the caller's iterator raises marked as the caller's.

    The choke point passes a marked error through verbatim: a failing source
    the caller handed in is not a wire error to classify.
    """
    if isinstance(content, bytes | bytearray | memoryview):
        return content
    return _marked(content)


async def feed(handle: _Writable, content: Content) -> None:
    """Write all of *content* into an open write handle."""
    if isinstance(content, bytes | bytearray | memoryview):
        await handle.write(bytes(content))
        return
    async for chunk in content:
        await handle.write(chunk)
