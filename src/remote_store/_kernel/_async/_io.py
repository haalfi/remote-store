"""Where the async runtime differs in kind, not by ``await``: stream and content shapes.

Hand-written in both runtimes; ``_sync/_io.py`` is its counterpart, with the
same names, which the generated modules import in place of these. Neither
imports the driver module, which imports them.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Protocol, cast

_log = logging.getLogger("remote_store._kernel")

#: What ``get`` returns: the async driver streams chunks.
ReadStream = AsyncIterator[bytes]
#: What ``put`` and ``write_atomic`` accept.
Content = bytes | AsyncIterator[bytes]


class _Writable(Protocol):
    """The part of a driver's write handle ``feed`` uses."""

    async def write(self, data: bytes) -> None: ...


async def drain(stream: ReadStream) -> bytes:
    """Drain *stream* into one ``bytes``; closing it is the caller's, who knows whether a failure condemned it."""
    return b"".join([chunk async for chunk in stream])


async def close_stream(stream: object) -> None:
    """Close a stream the kernel opened, if it can be closed."""
    aclose = getattr(stream, "aclose", None)
    if aclose is not None:
        await aclose()


_FROM_CONTENT = "_remote_store_from_content"


def from_content(exc: BaseException) -> bool:
    """Whether *exc* was raised by the caller's own content, not by the wire."""
    return bool(exc.__dict__.get(_FROM_CONTENT, False))


def _mark(exc: BaseException) -> None:
    # Into the instance dict, which every exception has: a class whose own
    # __setattr__ refuses new attributes is marked too.
    exc.__dict__[_FROM_CONTENT] = True


class _Marked:
    """The caller's iterator, its errors marked, each chunk checked; ``aclose`` closes the caller's.

    The kernel takes the caller's iterator with its first chunk. One it never
    started is left untouched, the caller's to retry with, since closing it
    would turn a retry into an empty write and protects nothing: an unstarted
    generator has no suspended frame to finalise.
    """

    __slots__ = ("_chunks", "_ended", "_iterator")

    def __init__(self, chunks: AsyncIterator[bytes]) -> None:
        self._chunks = chunks
        self._iterator: AsyncIterator[bytes] | None = None
        self._ended = False

    def __aiter__(self) -> _Marked:
        return self

    async def __anext__(self) -> bytes:
        if self._ended:
            raise StopAsyncIteration
        if self._iterator is None:
            try:
                self._iterator = self._chunks.__aiter__()
            except Exception as exc:
                _mark(exc)
                raise
        try:
            chunk: object = await self._iterator.__anext__()
        except StopAsyncIteration:
            self._ended = True
            raise
        except Exception as exc:
            _mark(exc)
            raise
        if isinstance(chunk, bytearray | memoryview):
            try:
                return bytes(chunk)
            except Exception as exc:  # a buffer that cannot be read, such as a released memoryview
                _mark(exc)
                raise
        if not isinstance(chunk, bytes):
            # Not binary: the caller's error, passed through verbatim, never one about the target.
            err = TypeError(f"content iterator yielded {type(chunk).__name__}, not bytes")
            _mark(err)
            raise err
        return chunk

    async def aclose(self) -> None:
        """Close the caller's iterator if the kernel started and did not exhaust it, and it has ``aclose``."""
        if self._ended or self._iterator is None:
            return
        self._ended = True
        aclose = getattr(self._iterator, "aclose", None)
        if aclose is not None:
            await aclose()


def take_content(content: object) -> Content:
    """*content* as the kernel passes it on, converted or refused after the metadata gate and before any I/O.

    A ``bytearray`` or ``memoryview`` becomes a copy as ``bytes`` here, so a
    buffer that cannot be read fails at the same rank as content that is
    neither a buffer nor an async iterator, which is a ``TypeError``.
    """
    if isinstance(content, bytes):
        return content
    if isinstance(content, bytearray | memoryview):
        return bytes(content)
    if callable(getattr(content, "__aiter__", None)):
        return cast("AsyncIterator[bytes]", content)
    msg = f"content must be bytes or an async iterator of bytes, not {type(content).__name__}"
    raise TypeError(msg)


def guard_content(content: Content) -> Content:
    """*content* with the caller's iterator marked: what it raises is the caller's.

    The choke point passes a marked error through verbatim: a failing source
    the caller handed in is not a wire error to classify. Each chunk it yields
    is checked too: a buffer becomes ``bytes``, and a chunk that is not binary
    (``None`` included) is a caller-marked ``TypeError``. A buffer, or anything
    without ``__aiter__``, is returned as it is: ``take_content`` converts or
    refuses it, at its own rank.
    """
    if isinstance(content, bytes | bytearray | memoryview) or not callable(getattr(content, "__aiter__", None)):
        return content
    return _Marked(content)


async def release_content(content: Content) -> None:
    """Close the caller's iterator behind *content* if the kernel did not exhaust it.

    Called on every exit of a write route, so a refused chunk, a failed write
    or a cancel never leaves the caller's iterator suspended for GC to
    finalise on whatever loop is then current. What its ``aclose`` raises is
    logged, never raised: it must not replace the error the write raised.
    """
    if not isinstance(content, _Marked):
        return
    try:
        await content.aclose()
    except Exception as exc:  # noqa: BLE001 - logged; the write's own outcome stands
        _log.warning("cleanup failed: closing the caller's content iterator raised %r", exc)


async def feed(handle: _Writable, content: Content) -> None:
    """Write all of *content* into an open write handle."""
    if isinstance(content, bytes):
        await handle.write(content)
        return
    async for chunk in content:
        await handle.write(chunk)
