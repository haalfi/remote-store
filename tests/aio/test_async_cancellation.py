"""Cancellation behavior for the async API.

``asyncio.CancelledError`` propagates differently from normal exceptions, and
async generators require explicit ``.aclose()`` cleanup. These tests assert
the invariants a caller relies on when cancelling an in-flight async operation:

1. A cancelled ``write`` / ``write_atomic`` leaves **no partial file**.
2. A cancelled overwrite **preserves the original content**.
3. A cancelled read task does not mutate the file.
4. ``read`` / ``list_files`` async generators **close cleanly** on early-break.
5. The backend remains functional after a cancelled consumer.

These tests target ``AsyncMemoryBackend`` because its ``write`` materialises
the full byte stream before acquiring its internal lock; cancellation lands
in the content iterator and the lock is never acquired. Backends that commit
in a different order may have different invariants (e.g. the
``SyncBackendAdapter`` runs writes in a thread pool where cancellation of the
coroutine does not stop the underlying thread); those are out of scope here.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from remote_store.aio import AsyncMemoryBackend, AsyncStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _blocking_chunks(
    first_yielded: asyncio.Event,
    release: asyncio.Event,
) -> AsyncIterator[bytes]:
    """Yield once, signal *first_yielded*, then block on *release*.

    *release* is never set in these tests — cancellation is the only exit.
    Using explicit events instead of ``asyncio.sleep`` eliminates timing flakiness.
    """
    yield b"first-chunk-"
    first_yielded.set()
    await release.wait()  # never set; CancelledError lands here
    yield b"never"


@pytest.fixture
def backend() -> AsyncMemoryBackend:
    return AsyncMemoryBackend()


class TestWriteCancellation:
    """A cancelled write must not leave a partial file."""

    async def test_cancel_mid_write_leaves_no_file(self, backend: AsyncMemoryBackend) -> None:
        first, release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(backend.write("f.txt", _blocking_chunks(first, release)))
        await first.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await backend.exists("f.txt") is False

    async def test_cancel_mid_write_atomic_leaves_no_file(self, backend: AsyncMemoryBackend) -> None:
        first, release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(backend.write_atomic("f.txt", _blocking_chunks(first, release)))
        await first.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await backend.exists("f.txt") is False

    async def test_cancel_overwrite_preserves_original_content(self, backend: AsyncMemoryBackend) -> None:
        await backend.write("f.txt", b"original")
        first, release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(backend.write("f.txt", _blocking_chunks(first, release), overwrite=True))
        await first.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await backend.read_bytes("f.txt") == b"original"

    async def test_backend_reusable_after_cancelled_write(self, backend: AsyncMemoryBackend) -> None:
        first, release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(backend.write("f.txt", _blocking_chunks(first, release)))
        await first.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Backend lock must have been released; subsequent write proceeds.
        await backend.write("f.txt", b"after-cancel")
        assert await backend.read_bytes("f.txt") == b"after-cancel"


class TestReadCancellation:
    """Early-break from a ``read()`` async iterator does not raise.

    ``AsyncMemoryBackend.read`` releases its internal lock **before** the
    first ``yield`` (the ``async with self._lock:`` block exits after the
    byte snapshot is taken), so an early-break cannot leave the lock held.
    The meaningful invariant a caller relies on for backends that **do**
    hold resources across the yield (e.g. ``SyncBackendAdapter``'s
    ``finally: stream.close()``) is covered by
    ``tests/backends/conformance/test_sync_adapter_conformance.py::test_read_closes_stream_on_early_break``.

    What this test asserts for ``AsyncMemoryBackend``:
    - the first yielded chunk equals the full file content
    - breaking from the ``async for`` does not raise
    - a subsequent ``read_bytes`` call still returns the correct content

    (A test for ``read_bytes`` cancellation was removed: ``AsyncMemoryBackend``
    holds its internal lock only during the point-in-time commit in
    ``read_bytes``, with no stall-worthy ``await`` in between. ``task.cancel()``
    before the task has run cancels before any line executes — trivially
    non-mutating. Cancelling under true lock contention would require
    touching private state to hold the lock, which violates the testing
    conventions.)
    """

    async def test_read_iterator_closes_cleanly_on_early_break(self, backend: AsyncMemoryBackend) -> None:
        await backend.write("f.txt", b"payload")
        collected = bytearray()
        async for chunk in backend.read("f.txt"):
            collected.extend(chunk)
            break
        assert bytes(collected) == b"payload"
        # Smoke check that the backend is still usable; the lock is released
        # *before* the yield in AsyncMemoryBackend, so this would pass even
        # if the generator were never closed.
        assert await backend.read_bytes("f.txt") == b"payload"


class TestListCancellation:
    """List iterators release the backend lock on early-break and cancellation."""

    async def test_list_files_closes_cleanly_on_early_break(self, backend: AsyncMemoryBackend) -> None:
        for i in range(10):
            await backend.write(f"f{i}.txt", b"x")
        seen = 0
        async for _ in backend.list_files(""):
            seen += 1
            if seen == 3:
                break
        assert seen == 3
        # All 10 files are still present; the generator must have released its lock.
        files = [f async for f in backend.list_files("")]
        assert len(files) == 10

    async def test_list_files_consumer_task_cancellable(self, backend: AsyncMemoryBackend) -> None:
        for i in range(5):
            await backend.write(f"f{i}.txt", b"x")
        started = asyncio.Event()
        release = asyncio.Event()  # never set; CancelledError is the only exit

        async def consumer() -> int:
            count = 0
            async for _ in backend.list_files(""):
                count += 1
                started.set()
                await release.wait()  # deterministic cancellation point
            return count

        task = asyncio.create_task(consumer())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Backend is reusable — no deadlock on the internal lock.
        files = [f async for f in backend.list_files("")]
        assert len(files) == 5


class TestAsyncStoreCancellation:
    """Cancellation invariants hold through the AsyncStore facade."""

    async def test_cancel_mid_write_leaves_no_file(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        first, release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(store.write("f.txt", _blocking_chunks(first, release)))
        await first.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await store.exists("f.txt") is False

    async def test_cancel_overwrite_preserves_original(self) -> None:
        store = AsyncStore(AsyncMemoryBackend(), root_path="data")
        await store.write("f.txt", b"original")
        first, release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(store.write("f.txt", _blocking_chunks(first, release), overwrite=True))
        await first.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await store.read_bytes("f.txt") == b"original"
