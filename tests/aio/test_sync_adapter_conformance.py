"""Conformance tests for ``SyncBackendAdapter`` wrapping real sync backends.

The existing ``tests/aio/test_sync_adapter.py`` covers the adapter wrapping
``MemoryBackend`` only. MemoryBackend has no filesystem I/O, no real resource
handles, and no streaming — so bugs in the adapter's ``asyncio.to_thread``
bridges (stream chunking, resource cleanup, executor-boundary error passthrough)
can hide behind its trivial behaviour.

This file adds the same conformance checks wrapping ``LocalBackend``, which
has a real filesystem, real file handles, and multi-chunk streaming reads.
The ``adapted_backend`` fixture is parametrised across both wrapped backends
so a regression in the adapter is caught regardless of which substrate it
wraps, and any divergence between them fails a single test.

Spec: ASYNC-030 through ASYNC-035 (``sdd/specs/029-async-store-backend-api.md``).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import AlreadyExists, NotFound
from remote_store.aio._sync_adapter import SyncBackendAdapter
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture(params=["memory", "local"], ids=["adapter-memory", "adapter-local"])
def adapted_backend(request: pytest.FixtureRequest, tmp_path: Path) -> SyncBackendAdapter:
    """``SyncBackendAdapter`` wrapping either ``MemoryBackend`` or ``LocalBackend``."""
    if request.param == "memory":
        return SyncBackendAdapter(MemoryBackend())
    return SyncBackendAdapter(LocalBackend(root=str(tmp_path)))


# ---------------------------------------------------------------------------
# Streaming read -- the 64 KiB loop at _sync_adapter.py:137-147
# ---------------------------------------------------------------------------


class TestAdapterStreamingRead:
    """``read()`` bridges a sync ``BinaryIO`` into an ``AsyncIterator[bytes]``."""

    @pytest.mark.spec("ASYNC-033")
    async def test_large_file_full_content(self, adapted_backend: SyncBackendAdapter) -> None:
        # 250 KiB exceeds the 64 KiB chunk size -- exercises the multi-chunk loop.
        data = b"x" * (250 * 1024)
        await adapted_backend.write("big.bin", data)
        chunks = [c async for c in adapted_backend.read("big.bin")]
        assert b"".join(chunks) == data
        assert all(len(c) > 0 for c in chunks)

    @pytest.mark.spec("ASYNC-033")
    async def test_read_closes_stream_on_early_break(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("big.bin", b"y" * (250 * 1024))
        async for _ in adapted_backend.read("big.bin"):
            break  # finally-block in adapter.read must close the sync stream
        # Backend is reusable after early-break -- delete proves no lingering handle
        await adapted_backend.delete("big.bin")
        assert await adapted_backend.exists("big.bin") is False

    async def test_read_not_found_propagates(self, adapted_backend: SyncBackendAdapter) -> None:
        with pytest.raises(NotFound, match="not found"):
            async for _ in adapted_backend.read("missing.bin"):
                pass

    async def test_read_bytes_not_found_propagates(self, adapted_backend: SyncBackendAdapter) -> None:
        with pytest.raises(NotFound, match="not found"):
            await adapted_backend.read_bytes("missing.bin")


# ---------------------------------------------------------------------------
# Write materialisation -- _materialize() at _sync_adapter.py:27-38
# ---------------------------------------------------------------------------


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


class TestAdapterWriteMaterialisation:
    """``write`` / ``write_atomic`` drain an async iterator before the sync call."""

    async def test_write_async_iterator(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("f.txt", _chunks(b"part-1-", b"part-2"))
        assert await adapted_backend.read_bytes("f.txt") == b"part-1-part-2"

    async def test_write_atomic_async_iterator(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write_atomic("f.txt", _chunks(b"a", b"bc"))
        assert await adapted_backend.read_bytes("f.txt") == b"abc"

    async def test_write_bytes_direct(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("f.txt", b"direct")
        assert await adapted_backend.read_bytes("f.txt") == b"direct"

    async def test_overwrite_false_raises_already_exists(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("f.txt", b"first")
        with pytest.raises(AlreadyExists, match="already exists"):
            await adapted_backend.write("f.txt", b"second")

    async def test_overwrite_true_replaces_content(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("f.txt", b"old")
        await adapted_backend.write("f.txt", b"new", overwrite=True)
        assert await adapted_backend.read_bytes("f.txt") == b"new"


# ---------------------------------------------------------------------------
# Iterator methods -- list_files / list_folders / iter_children
# ---------------------------------------------------------------------------


class TestAdapterListing:
    """Iterator adapters collect the sync iterator then re-yield asynchronously."""

    async def test_list_files_yields_every_item(self, adapted_backend: SyncBackendAdapter) -> None:
        for i in range(20):
            await adapted_backend.write(f"f{i:02d}.txt", str(i).encode())
        files = [f async for f in adapted_backend.list_files("")]
        assert {f.name for f in files} == {f"f{i:02d}.txt" for i in range(20)}

    async def test_list_files_recursive(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("a.txt", b"a")
        await adapted_backend.write("sub/b.txt", b"b")
        files = [f async for f in adapted_backend.list_files("", recursive=True)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}

    async def test_list_folders(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("sub1/a.txt", b"a")
        await adapted_backend.write("sub2/b.txt", b"b")
        folders = [f async for f in adapted_backend.list_folders("")]
        assert {f.name for f in folders} == {"sub1", "sub2"}

    async def test_iter_children_yields_files_and_folders(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("file.txt", b"x")
        await adapted_backend.write("sub/nested.txt", b"y")
        children = [c async for c in adapted_backend.iter_children("")]
        names = {c.name for c in children}
        assert names == {"file.txt", "sub"}


# ---------------------------------------------------------------------------
# Move / copy / delete
# ---------------------------------------------------------------------------


class TestAdapterMoveCopyDelete:
    async def test_move(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("src.txt", b"data")
        await adapted_backend.move("src.txt", "dst.txt")
        assert await adapted_backend.exists("src.txt") is False
        assert await adapted_backend.read_bytes("dst.txt") == b"data"

    async def test_copy(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("src.txt", b"data")
        await adapted_backend.copy("src.txt", "dst.txt")
        assert await adapted_backend.read_bytes("src.txt") == b"data"
        assert await adapted_backend.read_bytes("dst.txt") == b"data"

    async def test_move_dst_exists_raises_already_exists(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("src.txt", b"a")
        await adapted_backend.write("dst.txt", b"b")
        with pytest.raises(AlreadyExists, match="already exists"):
            await adapted_backend.move("src.txt", "dst.txt")

    async def test_delete(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("f.txt", b"x")
        await adapted_backend.delete("f.txt")
        assert await adapted_backend.exists("f.txt") is False

    async def test_delete_folder_recursive(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("dir/a.txt", b"a")
        await adapted_backend.write("dir/b.txt", b"b")
        await adapted_backend.delete_folder("dir", recursive=True)
        assert await adapted_backend.exists("dir") is False


# ---------------------------------------------------------------------------
# Concurrency -- thread-pool offload must not deadlock
# ---------------------------------------------------------------------------


class TestAdapterConcurrency:
    """``asyncio.to_thread`` dispatch under concurrent operations."""

    async def test_concurrent_writes(self, adapted_backend: SyncBackendAdapter) -> None:
        await asyncio.gather(*[adapted_backend.write(f"f{i}.txt", f"c{i}".encode()) for i in range(10)])
        for i in range(10):
            assert await adapted_backend.read_bytes(f"f{i}.txt") == f"c{i}".encode()

    async def test_concurrent_reads_return_identical_content(self, adapted_backend: SyncBackendAdapter) -> None:
        await adapted_backend.write("shared.txt", b"shared-content")
        results = await asyncio.gather(*[adapted_backend.read_bytes("shared.txt") for _ in range(10)])
        assert all(r == b"shared-content" for r in results)

    async def test_concurrent_mixed_ops(self, adapted_backend: SyncBackendAdapter) -> None:
        # Write then mix writes + reads + listings. Must all complete.
        await adapted_backend.write("seed.txt", b"seed")
        ops = [adapted_backend.write(f"new{i}.txt", f"n{i}".encode()) for i in range(5)] + [
            adapted_backend.read_bytes("seed.txt") for _ in range(3)
        ]
        results = await asyncio.gather(*ops)
        # Three read results must all equal the seed content
        read_results = [r for r in results if isinstance(r, bytes)]
        assert read_results == [b"seed"] * 3
