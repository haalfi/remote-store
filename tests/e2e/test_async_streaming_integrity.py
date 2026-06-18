"""End-to-end async streaming integrity test.

Proves two properties of the async streaming contract:

1. **Data integrity** -- a randomly-sized file (7--14 MiB) survives each hop
   of the async chain with identical SHA-256 at every step.
2. **Chunked streaming** -- hops with a lazy-read source yield multiple chunks
   (count > 1, max_chunk < file_size).  ``AsyncMemoryBackend`` is exempt from
   the chunk assertion because it yields a single chunk by design, despite
   declaring ``LAZY_READ`` (capability declaration vs. observed behavior diverge).

Chain (Azurite reachable):
    AsyncMemory(seed) -> AsyncAzure -> AsyncMemory(mid) ->
    SyncWrapped(Local) -> AsyncMemory(sink)

Fallback (no Azurite):
    AsyncMemory(seed) -> SyncWrapped(Local) -> AsyncMemory(sink)

A live Microsoft Graph hop is inserted before the Local hop when the
``graph_live`` two-layer gate (``RS_TEST_LIVE_GRAPH=1`` + credentials) is
satisfied; it is skipped cleanly otherwise.  GR-015 SharePoint range-fallback
exempts the Graph read from the lazy-chunking assertion (correct bytes, one
chunk).

No ``ext.transfer``.  Transfer is a manual ``async for chunk in store.read()``
loop fed into ``store.write()``.

``SyncBackendAdapter.write()`` materializes by design (sync backends cannot
accept ``AsyncIterator[bytes]``) -- write-side chunk assertions are not made.
Memory measurement (tracemalloc) deferred to a follow-up item.

Requires: ``docker compose -f infra/docker-compose.yml up -d``
Run with: ``pytest -m integration tests/e2e/test_async_streaming_integrity.py -s``
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import tempfile
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from remote_store import Capability
from remote_store.aio._async_store import AsyncStore
from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._local import LocalBackend
from tests.e2e.conftest import (
    AZURITE_CONN_STR,
    AZURITE_HOST,
    AZURITE_PORT,
    _graph_live_available,
    _port_open,
    build_graph_live_store,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.os_sensitive

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

FILE_SIZE_MIN = 7 * 1_048_576  # 7 MiB
FILE_SIZE_MAX = 14 * 1_048_576  # 14 MiB

PATH = "async-streaming-integrity-test.bin"


def _async_azure_available() -> bool:
    """Return True when ``AsyncAzureBackend`` can be used against Azurite.

    ``AsyncAzureBackend`` depends on ``azure.storage.blob.aio``, not
    ``azure.storage.filedatalake``.  This check probes the correct package so
    the Azure hop is not silently skipped in environments that have
    ``azure-storage-blob`` installed but not ``azure-datalake-storage``.
    """
    try:
        import azure.storage.blob.aio  # noqa: F401
    except ImportError:
        return False
    return _port_open(AZURITE_HOST, AZURITE_PORT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload(size: int) -> tuple[bytes, str]:
    """Generate a deterministic pseudo-random payload of *size* bytes with SHA-256."""
    rng = random.Random(42)  # noqa: S311 -- deterministic, not security-sensitive
    data = rng.randbytes(size)
    return data, hashlib.sha256(data).hexdigest()


async def _async_hop(
    src: AsyncStore,
    dst: AsyncStore,
    path: str,
) -> tuple[list[int], str]:
    """Transfer *path* from *src* to *dst* via a manual async-for loop.

    Tracks chunk sizes and SHA-256 on the **read side** only.

    Returns:
        ``(chunk_sizes, sha256_hex)`` measured while reading from *src*.
    """
    chunks: list[int] = []
    hasher = hashlib.sha256()

    async def _track() -> AsyncIterator[bytes]:
        async for chunk in src.read(path):
            chunks.append(len(chunk))
            hasher.update(chunk)
            yield chunk

    await dst.write(path, _track(), overwrite=True)
    return chunks, hasher.hexdigest()


async def _verify_hash(store: AsyncStore, path: str, expected: str) -> None:
    """Re-read *path* from *store* and hard-fail on SHA-256 mismatch."""
    h = hashlib.sha256()
    async for chunk in store.read(path):
        h.update(chunk)
    actual = h.hexdigest()
    assert actual == expected, f"Checksum mismatch at {store!r}: expected {expected[:16]}..., got {actual[:16]}..."


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class HopResult:
    """Chunk-level measurements collected for one transfer hop."""

    label: str
    file_size: int
    chunk_count: int
    max_chunk: int
    src_lazy: bool


def _emit_report(results: list[HopResult]) -> list[str]:
    """Print hop summary and return failure messages for contract violations."""
    print(  # noqa: T201
        "\n--- Async streaming integrity report ---\n"
        f"  {'Hop':44s}  {'Chunks':>6s}  {'MaxChunk':>10s}  {'Src':8s}  Status"
    )
    failures: list[str] = []
    for r in results:
        src_tag = "lazy" if r.src_lazy else "non-lazy"
        if r.src_lazy:
            chunked_ok = r.chunk_count > 1 and r.max_chunk < r.file_size
            status = "OK" if chunked_ok else "FAIL(chunks)"
        else:
            chunked_ok = True
            status = "OK(exempt)"
        print(  # noqa: T201
            f"  {r.label:44s}  {r.chunk_count:6d}  {r.max_chunk / 1_048_576:7.2f} MiB  {src_tag:8s}  {status}"
        )
        if r.src_lazy and not chunked_ok:
            failures.append(
                f"{r.label}: not chunked "
                f"(count={r.chunk_count}, max={r.max_chunk / 1_048_576:.2f} MiB, "
                f"file={r.file_size / 1_048_576:.2f} MiB)"
            )
    return failures


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _test_rng() -> random.Random:
    """Create a seeded RNG for reproducible test randomness.

    The seed is derived from ``PYTHONHASHSEED`` when set (deterministic CI),
    otherwise from system entropy.  The seed is printed so failures can be
    reproduced by setting ``PYTHONHASHSEED`` to the logged value.
    """
    import os

    env_seed = os.environ.get("PYTHONHASHSEED")
    seed = int(env_seed) if env_seed and env_seed.isdigit() else random.randrange(2**32)  # noqa: S311
    print(f"  Async streaming test seed: {seed} (reproduce with PYTHONHASHSEED={seed})")  # noqa: T201
    return random.Random(seed)  # noqa: S311


@pytest.fixture(scope="module")
def seeded_payload() -> tuple[bytes, str, int]:
    """Random-sized (7--14 MiB) payload with its SHA-256 hex digest."""
    rng = _test_rng()
    size = rng.randint(FILE_SIZE_MIN, FILE_SIZE_MAX)
    data, digest = _make_payload(size)
    print(f"\n  Async streaming: file_size={size / 1_048_576:.1f} MiB")  # noqa: T201
    return data, digest, size


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ID-138")
class TestAsyncStreamingIntegrity:
    """Async chain: SHA-256 integrity + lazy-read chunking contract."""

    async def test_chain_checksum_and_chunking(
        self,
        seeded_payload: tuple[bytes, str, int],
        record_property: Any,
    ) -> None:
        """Transfer a file through the async chain, verifying SHA-256 and chunking.

        Full chain (Azurite reachable):
            AsyncMemory(seed) -> AsyncAzure -> AsyncMemory(mid) ->
            SyncWrapped(Local) -> AsyncMemory(sink)

        Fallback (no Azurite):
            AsyncMemory(seed) -> SyncWrapped(Local) -> AsyncMemory(sink)

        Hops where the source has ``LAZY_READ`` must stream in multiple chunks
        (count > 1, max_chunk < file_size).  ``AsyncMemoryBackend`` sources are
        exempt -- they yield the full file as a single chunk by design.

        Hash mismatches fail immediately (data integrity is non-negotiable).
        ``SyncBackendAdapter.write()`` materializes by design -- no write-side
        chunk assertions are made.
        """
        payload, expected_sha, file_size = seeded_payload

        seed_store = AsyncStore(backend=AsyncMemoryBackend())
        sink_store = AsyncStore(backend=AsyncMemoryBackend())
        azure_store: AsyncStore | None = None
        mid_store: AsyncStore | None = None
        azure_service = None
        azure_container: str | None = None
        graph_store: AsyncStore | None = None
        graph_scratch: str | None = None
        local_store: AsyncStore | None = None
        tmp: tempfile.TemporaryDirectory[str] | None = None

        try:
            if _async_azure_available():
                from azure.storage.blob import BlobServiceClient

                from remote_store.aio.backends._azure import AsyncAzureBackend

                tag = uuid.uuid4().hex[:8]
                azure_container = f"e2e-async-stream-{tag}"
                azure_service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
                await asyncio.to_thread(azure_service.create_container, azure_container)
                azure_store = AsyncStore(
                    backend=AsyncAzureBackend(
                        container=azure_container,
                        hns=False,
                        connection_string=AZURITE_CONN_STR,
                    )
                )
                mid_store = AsyncStore(backend=AsyncMemoryBackend())

            if azure_store is None:
                record_property("azure_skipped", "AsyncAzureBackend unavailable — running 2-hop fallback chain")

            # Optional live Microsoft Graph hop (device-code / consumer OneDrive).
            # Gated by the same two-layer gate as the graph_live fixture; skips
            # cleanly without RS_TEST_LIVE_GRAPH=1 + credentials.
            if _graph_live_available():
                graph_scratch = f"e2e-async-stream-{uuid.uuid4().hex[:8]}"
                graph_store = build_graph_live_store(graph_scratch)
            else:
                record_property("graph_skipped", "GraphBackend live gate unmet — Graph hop skipped")

            tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
            # LocalBackend is sync; AsyncStore auto-wraps it via SyncBackendAdapter.
            local_store = AsyncStore(backend=LocalBackend(root=tmp.name))

            # Build ordered chain: seed, [azure, mid,] [graph,] local, sink.
            # A live Graph store joins as both a write target (from its
            # predecessor) and a lazy-read source (to its successor).
            chain: list[tuple[str, AsyncStore]] = [("async-memory(seed)", seed_store)]
            if azure_store is not None and mid_store is not None:
                chain.append(("async-azure", azure_store))
                chain.append(("async-memory(mid)", mid_store))
            if graph_store is not None:
                chain.append(("graph", graph_store))
            chain.append(("sync-wrapped(local)", local_store))
            chain.append(("async-memory(sink)", sink_store))

            # Backends that must stream in multiple chunks on read: all LAZY_READ
            # declarers except AsyncMemoryBackend, which declares LAZY_READ but
            # yields the full file as a single chunk (capability vs. behavior diverge).
            lazy_read_ids = {
                id(s)
                for _, s in chain
                if s.supports(Capability.LAZY_READ) and not isinstance(s._backend, AsyncMemoryBackend)
            }

            order = " -> ".join(name for name, _ in chain)
            record_property("chain", order)
            print(f"  Chain: {order}")  # noqa: T201

            # Seed the file into the first store and verify its integrity.
            await seed_store.write(PATH, payload, overwrite=True)
            await _verify_hash(seed_store, PATH, expected_sha)

            results: list[HopResult] = []

            for i in range(len(chain) - 1):
                src_name, src_store = chain[i]
                dst_name, dst_store = chain[i + 1]

                chunk_sizes, hop_sha = await _async_hop(src_store, dst_store, PATH)

                # Hard-fail on data corruption at any hop.
                assert hop_sha == expected_sha, (
                    f"Hash mismatch on hop {src_name} -> {dst_name}: "
                    f"expected {expected_sha[:16]}..., got {hop_sha[:16]}..."
                )
                await _verify_hash(dst_store, PATH, expected_sha)

                src_lazy = id(src_store) in lazy_read_ids
                # GR-015: a SharePoint-backed Graph drive that ignores Range
                # collapses the read to a single full re-fetch — correct bytes,
                # but one chunk. FileInfo.extra flags it; exempt that hop from
                # the chunking assertion so it does not flap.
                if graph_store is not None and src_store is graph_store and src_lazy:
                    info = await src_store.get_file_info(PATH)
                    if info.extra.get("graph.read.range_fallback"):
                        record_property(
                            "graph_range_fallback", "GR-015 fired — Graph hop exempt from chunking assertion"
                        )
                        src_lazy = False

                results.append(
                    HopResult(
                        label=f"{src_name} -> {dst_name}",
                        file_size=file_size,
                        chunk_count=len(chunk_sizes),
                        max_chunk=max(chunk_sizes) if chunk_sizes else 0,
                        src_lazy=src_lazy,
                    )
                )

                # Remove from source once the destination has the data.
                if src_store is not dst_store:
                    await src_store.delete(PATH)

            # Final integrity check on the last destination.
            await _verify_hash(sink_store, PATH, expected_sha)

            failures = _emit_report(results)
            assert not failures, "Async streaming contract violations:\n" + "\n".join(failures)

        finally:
            await seed_store.aclose()
            await sink_store.aclose()
            if azure_store is not None:
                await azure_store.aclose()
            if mid_store is not None:
                await mid_store.aclose()
            if local_store is not None:
                await local_store.aclose()
            if graph_store is not None:
                await graph_store.aclose()
            if graph_scratch is not None:
                # Best-effort: drop the scratch folder from the real drive.
                # Cleanup must never fail the test.
                try:
                    cleanup_store = build_graph_live_store("")
                    try:
                        await cleanup_store.delete_folder(graph_scratch, recursive=True)
                    finally:
                        await cleanup_store.aclose()
                except Exception:  # noqa: BLE001 -- teardown best-effort
                    pass
            if azure_service is not None and azure_container is not None:
                await asyncio.to_thread(azure_service.delete_container, azure_container)
                await asyncio.to_thread(azure_service.close)
            if tmp is not None:
                tmp.cleanup()
