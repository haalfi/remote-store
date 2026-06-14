"""Posture-gated concurrency conformance lane — async (BK-289).

The async axis of the BK-289 lane. As for the sync sibling, every assertion is
an **invariant** (no error, correct final state, no lost writes) — never an
interleaving, ordering, or timing assertion, and no ``sleep``-based
synchronisation.

Async axis nuance (research §4.1)
---------------------------------
* **Native ``AsyncBackend``s** (async Memory, async Azure, Graph) are
  coroutine-safe on a *single* loop and unsafe *across* loops (ASYNC-055). The
  ``asyncio.gather`` stress asserts the single-loop half over the async
  ``thread_safe`` set; ``test_cross_loop_reuse_is_not_silent_corruption``
  guards the cross-loop half.
* **Bridged ``single_connection`` backends** (SFTP, HTTP) reach async only
  through ``AsyncBackendSyncAdapter`` and carry their sync posture *into* the
  async lane. The registry has **no** async SFTP/HTTP fixture, so there is no
  ``single_connection`` async parametrize target here; that carve-out is
  exercised by the **sync** lane's ``TestSingleConnectionCarveOut`` and the
  pre-existing ``test_sync_adapter_conformance.py`` SFTP exclusion. An
  implementer who later adds an async SFTP fixture must keep it
  ``single_connection`` so it is not thread/loop-stressed on the shared paramiko
  socket.

``TestAsyncConcurrentLargeUploads`` is the async Tier-3 sibling of the sync
``TestConcurrentLargeUploads``: N parallel large/streamed ``write_atomic`` over
the async staged path (``aio/backends/_azure.py`` block staging), gated on
``large_write_distinct`` so it runs on ``azurite_async`` (Stage 2) and the live
async fixtures, not the in-process adapters.

Replay (cassette) fixtures are excluded by ``fixture_params_concurrent`` because
vcrpy matches requests sequentially — not a concurrency-safe substrate. The
Graph create-once-race contract is exercised against ``respx`` in
``tests/backends/graph/aio/test_concurrency.py``.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from tests.backends.conformance._helpers import (
    _fixture_record,
    _require,
    _skip_unless_large_write_distinct,
)
from tests.backends.fixtures import all_fixtures, fixture_params_concurrent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from remote_store.aio import AsyncBackend

# One loop, modest coroutine fan-out (research §4.3).
_N_ITEMS = 16
# Parallel large-upload probe: few but large (4 x 8 MiB), matching the sync lane.
_LARGE_N = 4
_LARGE_SIZE = 8 * 1024 * 1024


def _xfail_local_async_dir_race_on_windows(async_backend: Any, request: pytest.FixtureRequest) -> None:
    """xfail the ``local_async_adapted`` write-stress on Windows for BUG-220.

    The async Local fixture is the sync ``LocalBackend`` behind
    ``AsyncBackendSyncAdapter``; concurrent ``gather`` writes dispatch concurrent
    ``to_thread`` work that hits the same ``_resolve`` dir-creation race as the
    sync lane (BUG-220). Windows-only, ``strict=False``: POSIX runs it for real
    and a fixed backend xpasses.
    """
    if sys.platform == "win32" and _fixture_record(async_backend).name == "local_async_adapted":
        request.applymarker(
            pytest.mark.xfail(
                reason="BUG-220: LocalBackend._resolve races on concurrent intermediate-dir creation (Windows)",
                strict=False,
            )
        )


@pytest.mark.concurrency
@pytest.mark.spec("ASYNC-094")
@pytest.mark.parametrize(
    "async_backend",
    fixture_params_concurrent(Capability.WRITE, is_async=True, posture="thread_safe"),
    indirect=True,
)
class TestAsyncCoroutineSafe:
    """ASYNC-055 single-loop half — concurrent coroutines on ONE instance.

    Runs over the async ``thread_safe`` set (native async Memory/Azure/Graph and
    the in-process adapter-wrapped fixtures). Replay fixtures are excluded by the
    selector.
    """

    @pytest.mark.spec("ASYNC-055")
    async def test_concurrent_reads_consistent(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.WRITE)
        keys = {f"acc/read/{i}.txt": f"payload-{i}".encode() for i in range(_N_ITEMS)}
        for key, data in keys.items():
            await async_backend.write(key, data)
        got = await asyncio.gather(*(async_backend.read_bytes(key) for key in keys))
        assert list(got) == list(keys.values())

    @pytest.mark.spec("ASYNC-055")
    async def test_concurrent_distinct_key_writes_all_land(
        self, async_backend: AsyncBackend, request: pytest.FixtureRequest
    ) -> None:
        _require(async_backend, Capability.WRITE)
        _xfail_local_async_dir_race_on_windows(async_backend, request)
        keys = {f"acc/write/{i}.bin": f"w{i}".encode() for i in range(_N_ITEMS)}
        await asyncio.gather(*(async_backend.write(key, data) for key, data in keys.items()))
        for key, data in keys.items():
            assert await async_backend.read_bytes(key) == data

    @pytest.mark.spec("ASYNC-055")
    async def test_concurrent_read_after_write_consistent(
        self, async_backend: AsyncBackend, request: pytest.FixtureRequest
    ) -> None:
        _require(async_backend, Capability.WRITE)
        _xfail_local_async_dir_race_on_windows(async_backend, request)
        keys = {f"acc/raw/{i}.txt": f"raw-{i}".encode() for i in range(_N_ITEMS)}

        async def _raw(key: str, data: bytes) -> tuple[bytes, bytes]:
            await async_backend.write(key, data)
            return await async_backend.read_bytes(key), data

        results = await asyncio.gather(*(_raw(key, data) for key, data in keys.items()))
        assert all(got == expected for got, expected in results)


@pytest.mark.concurrency
@pytest.mark.spec("ASYNC-094")
@pytest.mark.parametrize(
    "async_backend",
    fixture_params_concurrent(Capability.WRITE, is_async=True, posture="thread_safe"),
    indirect=True,
)
class TestAsyncConcurrentLargeUploads:
    """Tier 3 — N parallel large/streamed uploads on the async staged write path.

    The async sibling of the sync ``TestConcurrentLargeUploads``. Gated on
    ``large_write_distinct`` so it runs only where the async multipart /
    block-staging / upload-session path is faithfully exercised — ``azurite_async``
    at Stage 2 (the async ``_azure.py`` block-staging path) and the live async
    fixtures (``azure_live_async`` / ``graph_live``) at Stage 3, whose params carry
    ``pytest.mark.live``. The in-process adapter fixtures carry
    ``large_write_distinct = False``, so the test is simply not parametrised onto
    them. Without this, concurrent large writes over the async staging path were
    covered nowhere (WR-001a writes a large payload, but never concurrently).
    """

    @pytest.mark.spec("ASYNC-055")
    async def test_concurrent_large_streamed_uploads(self, async_backend: AsyncBackend) -> None:
        _require(async_backend, Capability.ATOMIC_WRITE)
        _skip_unless_large_write_distinct(async_backend)
        chunk = b"\xab" * (1024 * 1024)
        n_chunks = _LARGE_SIZE // len(chunk)

        async def _upload(item: int) -> int:
            # Each coroutine gets its own single-use AsyncIterator — the async
            # large/streamed write path consumes content via ``async for`` (a sync
            # BytesIO is rejected), and a shared generator would be drained once.
            async def _stream() -> AsyncIterator[bytes]:
                for _ in range(n_chunks):
                    yield chunk

            key = f"acc/large/{item}.bin"
            await async_backend.write_atomic(key, _stream())
            info = await async_backend.get_file_info(key)
            return info.size

        sizes = await asyncio.gather(*(_upload(i) for i in range(_LARGE_N)))
        assert all(size == _LARGE_SIZE for size in sizes)


def _async_memory_record() -> Any:
    """Return the ``memory_async_native`` registry record (no concrete class name).

    Sourcing the backend through the registry keeps the TEST-010 boundary clean
    (no ``AsyncMemoryBackend`` import here) while letting the cross-loop guard
    drive ``asyncio.run`` itself rather than the pytest-managed loop.
    """
    return next(f for f in all_fixtures() if f.name == "memory_async_native")


@pytest.mark.concurrency
@pytest.mark.spec("ASYNC-055")
@pytest.mark.spec("ASYNC-094")
def test_cross_loop_reuse_is_not_silent_corruption() -> None:
    """ASYNC-055 cross-loop half — reuse across loops must not corrupt state.

    ASYNC-055: an ``AsyncBackend`` is safe for concurrent coroutines on **one**
    loop, and the supported pattern across loops is *one instance per loop*. The
    spec's hard guarantee is the absence of *silent corruption*. This guards
    that deterministically on the in-process memory substrate (which holds no
    loop-bound transport): the same instance driven by two sequential
    ``asyncio.run`` loops neither loses nor corrupts data written on the first.

    A backend whose transport binds to a loop (a network SDK client created
    lazily on first use) instead surfaces the cross-loop misuse as a *typed*
    error rather than corruption — that failure mode is exercised by the Graph
    and Azure live lanes, not reproducible on the loop-agnostic memory backend.
    """
    record = _async_memory_record()
    backend = record.factory()
    try:

        async def _roundtrip() -> bytes:
            await backend.write("cross-loop.txt", b"payload", overwrite=True)
            return await backend.read_bytes("cross-loop.txt")

        first = asyncio.run(_roundtrip())  # loop A: created and closed by asyncio.run
        second = asyncio.run(_roundtrip())  # loop B: a fresh loop reusing the same instance
        assert first == second == b"payload"
        # The write from loop A is still readable after loop B — no lost/corrupt state.
        assert asyncio.run(backend.read_bytes("cross-loop.txt")) == b"payload"
    finally:
        if record.aclose is not None:
            asyncio.run(record.aclose(backend))
        if record.cleanup is not None:
            record.cleanup(backend)
