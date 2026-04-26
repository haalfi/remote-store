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

A separate ``live_adapted_backend`` fixture runs the same suite against
``S3Backend`` (moto), ``SFTPBackend`` (in-process server), and ``AzureBackend``
(Azurite). These exercise the blocking patterns through ``asyncio.to_thread``
that Memory/Local cannot reach: real network I/O, connection pools, SDK-level
retries, and pagination. The live classes are marked ``integration`` so they
do not inflate the default test run.

Spec: ASYNC-030 through ASYNC-035 (``sdd/specs/029-async-store-backend-api.md``).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import AlreadyExists, NotFound
from remote_store.aio._sync_adapter import SyncBackendAdapter
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend
from tests.conftest import _azure_available, _azurite_reachable, _s3_available, _sftp_available

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path


@pytest.fixture(
    params=[
        "memory",
        pytest.param("local", marks=pytest.mark.os_sensitive),
    ],
    ids=["adapter-memory", "adapter-local"],
)
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
        # ``async for`` does not call ``aclose`` on ``break`` -- use
        # ``contextlib.aclosing`` for deterministic cleanup. Without it,
        # the sync file handle stays open until GC, which on Windows
        # blocks the subsequent ``delete`` with PermissionError.
        async with contextlib.aclosing(adapted_backend.read("big.bin")) as stream:
            async for _ in stream:
                break  # finally-block in adapter.read must close the sync stream
        # Backend is reusable after early-break -- delete proves no lingering handle
        await adapted_backend.delete("big.bin")
        assert await adapted_backend.exists("big.bin") is False

    @pytest.mark.spec("ASYNC-033")
    async def test_read_not_found_propagates(self, adapted_backend: SyncBackendAdapter) -> None:
        # NotFound is raised during the initial ``asyncio.to_thread(sync.read, ...)``
        # call (before the first ``yield``), not inside the loop body. The
        # ``pass`` below is never reached for the not-found case.
        with pytest.raises(NotFound, match="not found"):
            async for _ in adapted_backend.read("missing.bin"):
                pass

    @pytest.mark.spec("ASYNC-031")
    async def test_read_bytes_not_found_propagates(self, adapted_backend: SyncBackendAdapter) -> None:
        # read_bytes is a single-shot ``await asyncio.to_thread(...)`` (thread
        # delegation, ASYNC-031) -- not the chunked streaming-read bridge of
        # ASYNC-033.
        with pytest.raises(NotFound, match="not found"):
            await adapted_backend.read_bytes("missing.bin")


# ---------------------------------------------------------------------------
# Write materialisation -- _materialize() at _sync_adapter.py:27-38
# ---------------------------------------------------------------------------


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


@pytest.mark.spec("ASYNC-036")
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


@pytest.mark.spec("ASYNC-032")
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


@pytest.mark.spec("ASYNC-031")
class TestAdapterMoveCopyDelete:
    """Blocking calls delegated to ``asyncio.to_thread`` (move/copy/delete)."""

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


@pytest.mark.spec("ASYNC-031", "ASYNC-055")
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


# ---------------------------------------------------------------------------
# Live backends: S3 (moto) / SFTP (in-process) / Azure (Azurite)
#
# Separate fixture so the fast Memory/Local path (<1 s) is unaffected.
# These exercise blocking patterns asyncio.to_thread must bridge: real
# network I/O, connection-pool reuse, SDK-level retries, S3 pagination.
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        pytest.param(
            "s3",
            marks=pytest.mark.skipif(not _s3_available(), reason="moto/s3fs not installed"),
        ),
        pytest.param(
            "sftp",
            marks=pytest.mark.skipif(not _sftp_available(), reason="paramiko not installed"),
        ),
        pytest.param(
            "azure",
            marks=[
                pytest.mark.requires_docker,
                pytest.mark.skipif(
                    not _azure_available() or not _azurite_reachable(),
                    reason="azure SDK not installed or Azurite not reachable",
                ),
            ],
        ),
    ],
    ids=["live-s3", "live-sftp", "live-azure"],
)
def live_adapted_backend(
    request: pytest.FixtureRequest,
    moto_server: str | None,
    sftp_server: tuple[int, str] | None,
    azurite_server: str | None,
) -> Iterator[SyncBackendAdapter]:
    """``SyncBackendAdapter`` over a live backend for integration conformance."""
    if request.param == "s3":
        import boto3

        from remote_store.backends._s3 import S3Backend

        assert moto_server is not None  # noqa: S101
        bucket = f"adapter-{uuid.uuid4().hex[:8]}"
        client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        b = S3Backend(
            bucket=bucket,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            endpoint_url=moto_server,
        )
        yield SyncBackendAdapter(b)
        b.close()
    elif request.param == "sftp":
        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        assert sftp_server is not None  # noqa: S101
        port, _host_key_entry = sftp_server
        base_path = f"/adapter_{uuid.uuid4().hex[:8]}"
        b = SFTPBackend(
            host="127.0.0.1",
            port=port,
            username="testuser",
            password="testpass",
            base_path=base_path,
            host_key_policy=HostKeyPolicy.AUTO_ADD,
            connect_kwargs={"allow_agent": False, "look_for_keys": False},
        )
        yield SyncBackendAdapter(b)
        b.close()
    elif request.param == "azure":
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        assert azurite_server is not None  # noqa: S101
        container = f"adapter-{uuid.uuid4().hex[:8]}"
        service = BlobServiceClient.from_connection_string(azurite_server)
        try:
            service.create_container(container)
        except Exception:  # noqa: BLE001
            service.close()
            raise
        b = AzureBackend(container=container, connection_string=azurite_server)
        try:
            yield SyncBackendAdapter(b)
        finally:
            b.close()
            service.delete_container(container)
            service.close()
    else:
        pytest.skip(f"Unknown live backend: {request.param}")


@pytest.fixture(
    params=[
        pytest.param(
            "s3",
            marks=pytest.mark.skipif(not _s3_available(), reason="moto/s3fs not installed"),
        ),
        pytest.param(
            "azure",
            marks=[
                pytest.mark.requires_docker,
                pytest.mark.skipif(
                    not _azure_available() or not _azurite_reachable(),
                    reason="azure SDK not installed or Azurite not reachable",
                ),
            ],
        ),
    ],
    ids=["live-s3", "live-azure"],
)
def live_adapted_backend_concurrent(
    request: pytest.FixtureRequest,
    moto_server: str | None,
    azurite_server: str | None,
) -> Iterator[SyncBackendAdapter]:
    """Like ``live_adapted_backend`` but excludes SFTP.

    Paramiko's SFTP client is not thread-safe: concurrent ``asyncio.to_thread``
    calls against a single ``SFTPBackend`` instance race on the shared socket,
    which causes hangs. S3 and Azure use connection pools that are safe for
    concurrent threaded access, making them suitable concurrency-test substrates.
    """
    if request.param == "s3":
        import boto3

        from remote_store.backends._s3 import S3Backend

        assert moto_server is not None  # noqa: S101
        bucket = f"adapter-conc-{uuid.uuid4().hex[:8]}"
        client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        b = S3Backend(
            bucket=bucket,
            key="testing",
            secret="testing",
            region_name="us-east-1",
            endpoint_url=moto_server,
        )
        yield SyncBackendAdapter(b)
        b.close()
    elif request.param == "azure":
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        assert azurite_server is not None  # noqa: S101
        container = f"adapter-conc-{uuid.uuid4().hex[:8]}"
        service = BlobServiceClient.from_connection_string(azurite_server)
        try:
            service.create_container(container)
        except Exception:  # noqa: BLE001
            service.close()
            raise
        b = AzureBackend(container=container, connection_string=azurite_server)
        try:
            yield SyncBackendAdapter(b)
        finally:
            b.close()
            service.delete_container(container)
            service.close()
    else:
        pytest.skip(f"Unknown concurrent backend: {request.param}")


# ---------------------------------------------------------------------------
# Live: Streaming read
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterStreamingReadLive:
    """Same streaming-read checks as ``TestAdapterStreamingRead`` against live backends."""

    @pytest.mark.spec("ASYNC-033")
    async def test_large_file_full_content(self, live_adapted_backend: SyncBackendAdapter) -> None:
        data = b"x" * (250 * 1024)
        await live_adapted_backend.write("big.bin", data)
        chunks = [c async for c in live_adapted_backend.read("big.bin")]
        assert b"".join(chunks) == data
        assert all(len(c) > 0 for c in chunks)

    @pytest.mark.spec("ASYNC-033")
    async def test_read_closes_stream_on_early_break(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("big.bin", b"y" * (250 * 1024))
        async with contextlib.aclosing(live_adapted_backend.read("big.bin")) as stream:
            async for _ in stream:
                break
        await live_adapted_backend.delete("big.bin")
        assert await live_adapted_backend.exists("big.bin") is False

    @pytest.mark.spec("ASYNC-033")
    async def test_read_not_found_propagates(self, live_adapted_backend: SyncBackendAdapter) -> None:
        # Different backends capitalise the message differently; match on path.
        with pytest.raises(NotFound, match="missing.bin"):
            async for _ in live_adapted_backend.read("missing.bin"):
                pass

    @pytest.mark.spec("ASYNC-031")
    async def test_read_bytes_not_found_propagates(self, live_adapted_backend: SyncBackendAdapter) -> None:
        with pytest.raises(NotFound, match="missing.bin"):
            await live_adapted_backend.read_bytes("missing.bin")


# ---------------------------------------------------------------------------
# Live: Write materialisation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ASYNC-036")
class TestAdapterWriteMaterialisationLive:
    """Write / write_atomic materialisation against live backends."""

    async def test_write_async_iterator(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("f.txt", _chunks(b"part-1-", b"part-2"))
        assert await live_adapted_backend.read_bytes("f.txt") == b"part-1-part-2"

    async def test_write_atomic_async_iterator(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write_atomic("f.txt", _chunks(b"a", b"bc"))
        assert await live_adapted_backend.read_bytes("f.txt") == b"abc"

    async def test_write_bytes_direct(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("f.txt", b"direct")
        assert await live_adapted_backend.read_bytes("f.txt") == b"direct"

    async def test_overwrite_false_raises_already_exists(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("f.txt", b"first")
        with pytest.raises(AlreadyExists, match="already exists"):
            await live_adapted_backend.write("f.txt", b"second")

    async def test_overwrite_true_replaces_content(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("f.txt", b"old")
        await live_adapted_backend.write("f.txt", b"new", overwrite=True)
        assert await live_adapted_backend.read_bytes("f.txt") == b"new"


# ---------------------------------------------------------------------------
# Live: Listing -- exercises S3 pagination / Azure continuation tokens
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ASYNC-032")
class TestAdapterListingLive:
    """List_files / list_folders / iter_children against live backends."""

    async def test_list_files_yields_every_item(self, live_adapted_backend: SyncBackendAdapter) -> None:
        for i in range(20):
            await live_adapted_backend.write(f"f{i:02d}.txt", str(i).encode())
        files = [f async for f in live_adapted_backend.list_files("")]
        assert {f.name for f in files} == {f"f{i:02d}.txt" for i in range(20)}

    async def test_list_files_recursive(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("a.txt", b"a")
        await live_adapted_backend.write("sub/b.txt", b"b")
        files = [f async for f in live_adapted_backend.list_files("", recursive=True)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}

    async def test_list_folders(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("sub1/a.txt", b"a")
        await live_adapted_backend.write("sub2/b.txt", b"b")
        folders = [f async for f in live_adapted_backend.list_folders("")]
        assert {f.name for f in folders} == {"sub1", "sub2"}

    async def test_iter_children_yields_files_and_folders(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("file.txt", b"x")
        await live_adapted_backend.write("sub/nested.txt", b"y")
        children = [c async for c in live_adapted_backend.iter_children("")]
        names = {c.name for c in children}
        assert names == {"file.txt", "sub"}


# ---------------------------------------------------------------------------
# Live: Move / copy / delete
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ASYNC-031")
class TestAdapterMoveCopyDeleteLive:
    """Blocking move/copy/delete delegated to asyncio.to_thread against live backends."""

    async def test_move(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("src.txt", b"data")
        await live_adapted_backend.move("src.txt", "dst.txt")
        assert await live_adapted_backend.exists("src.txt") is False
        assert await live_adapted_backend.read_bytes("dst.txt") == b"data"

    async def test_copy(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("src.txt", b"data")
        await live_adapted_backend.copy("src.txt", "dst.txt")
        assert await live_adapted_backend.read_bytes("src.txt") == b"data"
        assert await live_adapted_backend.read_bytes("dst.txt") == b"data"

    async def test_move_dst_exists_raises_already_exists(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("src.txt", b"a")
        await live_adapted_backend.write("dst.txt", b"b")
        with pytest.raises(AlreadyExists, match="already exists"):
            await live_adapted_backend.move("src.txt", "dst.txt")

    async def test_delete(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("f.txt", b"x")
        await live_adapted_backend.delete("f.txt")
        assert await live_adapted_backend.exists("f.txt") is False

    async def test_delete_folder_recursive(self, live_adapted_backend: SyncBackendAdapter) -> None:
        await live_adapted_backend.write("dir/a.txt", b"a")
        await live_adapted_backend.write("dir/b.txt", b"b")
        await live_adapted_backend.delete_folder("dir", recursive=True)
        assert await live_adapted_backend.exists("dir") is False


# ---------------------------------------------------------------------------
# Live: Concurrency -- exercises real thread-pool dispatch under network I/O
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ASYNC-031", "ASYNC-055")
class TestAdapterConcurrencyLive:
    """asyncio.to_thread dispatch must not deadlock against live backends.

    Uses ``live_adapted_backend_concurrent`` (S3/Azure only). SFTP is excluded
    because paramiko's SFTP client is not thread-safe: concurrent
    ``asyncio.to_thread`` calls against a single ``SFTPBackend`` instance race
    on the shared socket. S3 and Azure use connection pools safe for concurrent
    threaded access.
    """

    async def test_concurrent_writes(self, live_adapted_backend_concurrent: SyncBackendAdapter) -> None:
        await asyncio.gather(*[live_adapted_backend_concurrent.write(f"f{i}.txt", f"c{i}".encode()) for i in range(10)])
        for i in range(10):
            assert await live_adapted_backend_concurrent.read_bytes(f"f{i}.txt") == f"c{i}".encode()

    async def test_concurrent_reads_return_identical_content(
        self, live_adapted_backend_concurrent: SyncBackendAdapter
    ) -> None:
        await live_adapted_backend_concurrent.write("shared.txt", b"shared-content")
        results = await asyncio.gather(*[live_adapted_backend_concurrent.read_bytes("shared.txt") for _ in range(10)])
        assert all(r == b"shared-content" for r in results)

    async def test_concurrent_mixed_ops(self, live_adapted_backend_concurrent: SyncBackendAdapter) -> None:
        await live_adapted_backend_concurrent.write("seed.txt", b"seed")
        ops = [live_adapted_backend_concurrent.write(f"new{i}.txt", f"n{i}".encode()) for i in range(5)] + [
            live_adapted_backend_concurrent.read_bytes("seed.txt") for _ in range(3)
        ]
        results = await asyncio.gather(*ops)
        read_results = [r for r in results if isinstance(r, bytes)]
        assert read_results == [b"seed"] * 3
