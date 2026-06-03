"""Reusable guard: a write path must stream its input to the SDK, not materialize it.

A backend wrapping a streaming SDK can collapse an ``AsyncIterator[bytes]`` /
``BinaryIO`` into one ``bytes`` before the SDK call without any signature change
(``upload_blob(b"".join(...))`` type-checks like ``upload_blob(src)``), silently
breaking the bounded-memory promise (SIO-003 / ASYNC-021).

The discriminator is *chunk-boundary preservation at the SDK boundary*: a
faithful stream forwards N chunks as N chunks, while any materialization
collapses N>1 chunks into one. The helpers here stand in for the backend's SDK
call (Azure ``upload_blob`` / ``append_data``), record the chunks it observed,
and let a test assert that sequence matches what the caller supplied — a check
only possible at the SDK boundary, since a black-box write cannot see chunk
boundaries. A new SDK-streaming backend reuses them by pointing its mocked SDK
call at the same collectors.

Regression context: BUG-165, BUG-181, BUG-194.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from unittest.mock import Mock

# Distinct, multi-byte chunks. Distinctness makes a reordering visible; >1 chunk
# is what lets a collapse-to-one-chunk materialization be detected at all.
MULTI_CHUNK: tuple[bytes, ...] = (b"BK240-alpha", b"BK240-bravo", b"BK240-charlie")
"""Canonical multi-chunk caller payload for the guard."""

FULL_PAYLOAD: bytes = b"".join(MULTI_CHUNK)
"""The same payload as a single ``bytes`` (for BinaryIO-input paths)."""


async def async_chunks(chunks: tuple[bytes, ...] = MULTI_CHUNK) -> AsyncIterator[bytes]:
    """A faithful caller: yield ``chunks`` one at a time as an async iterator."""
    for chunk in chunks:
        yield chunk


def assert_streamed_not_materialized(observed: list[bytes], supplied: tuple[bytes, ...] = MULTI_CHUNK) -> None:
    """Assert the SDK observed ``supplied``'s chunk sequence unchanged.

    ``observed`` is the chunk list the (mocked) SDK pulled from whatever object
    the backend forwarded. A bounded-memory stream preserves chunk boundaries;
    any materialization collapses ``len(supplied)`` chunks into one.
    """
    assert len(supplied) > 1, "guard payload must have >1 chunk to detect a collapse"
    assert observed == list(supplied), (
        f"write path materialized its input: the SDK observed {len(observed)} "
        f"chunk(s) ({observed!r}) but the caller supplied {len(supplied)} "
        f"({list(supplied)!r}). Bounded-memory streaming forwards the same "
        "chunk boundaries (SIO-003 / ASYNC-021); joining to bytes (BUG-165) or "
        "re-emitting the join as one chunk (BUG-194) collapses them."
    )


async def collect_async_upload(data: Any) -> list[bytes]:
    """``upload_blob`` async side-effect: consume the forwarded payload.

    Rejects a materialized ``bytes`` payload (no ``__aiter__``) with a clear
    failure rather than letting ``async for`` raise an opaque ``TypeError``,
    then returns the observed chunk list for ``assert_streamed_not_materialized``.
    """
    if not hasattr(data, "__aiter__"):
        raise AssertionError(
            f"upload_blob received {type(data).__name__}, not an async iterable: "
            "the write path materialized its input to bytes (BUG-165), breaking "
            "the bounded-memory streaming promise (SIO-003 / ASYNC-021)."
        )
    return [chunk async for chunk in data]


def collect_sync_upload(data: Any, block: int = 4) -> list[bytes]:
    """``upload_blob`` sync side-effect: read the forwarded stream in ``block``-sized reads.

    The sync write path forwards a *readable stream* (the ``_ByteCountingIO``
    wrapper) and lets the SDK choose its read sizes, so for this path the
    discriminator is "stream, not bytes" rather than caller-chosen boundaries.
    Rejects a materialized ``bytes`` payload with a clear failure, then returns
    the chunks the SDK read (``>1`` for a payload larger than ``block``).
    """
    if isinstance(data, (bytes, bytearray)) or not hasattr(data, "read"):
        raise AssertionError(
            f"upload_blob received {type(data).__name__}, not a readable stream: "
            "the write path materialized its BinaryIO input to bytes, breaking "
            "the streaming promise (SIO-003)."
        )
    observed: list[bytes] = []
    while True:
        chunk = data.read(block)
        if not chunk:
            break
        observed.append(chunk)
    return observed


def chunks_from_append_calls(append_mock: Mock) -> list[bytes]:
    """Extract the per-call payloads from an ``append_data`` mock's call list.

    The DFS append path (HNS, sync and async) issues one ``append_data`` call
    per chunk, so the call list *is* the chunk sequence the SDK observed.
    """
    chunks: list[bytes] = []
    for call in append_mock.call_args_list:
        chunk = call.args[0] if call.args else call.kwargs.get("data")
        chunks.append(chunk)
    return chunks
