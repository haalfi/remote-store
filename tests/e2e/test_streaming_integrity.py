"""End-to-end streaming integrity test.

Proves three properties of the remote-store streaming contract:

1. **Data integrity** (hard fail) -- a randomly-sized file (7--14 MiB) survives
   a full round-robin transfer across all available read/write backends (in
   random order) with identical SHA-256 at each hop.
2. **Chunked streaming** (hard fail) -- ``transfer()`` reads data in multiple
   chunks, never as a single ``read()`` of the full file.  Verified via the
   ``on_progress`` callback which fires per chunk.  Non-lazy destinations
   (SQL BLOB) are exempt because they must materialize the full stream.
3. **Memory discipline** (hard fail) -- two memory measurements per hop, both
   filtered to ``remote_store`` source files only (dependencies excluded):

   - **Pipe cost**: allocations from the transfer layer
     (``ext/transfer.py``, ``ext/streams.py``, ``_stream.py``).  Note:
     ``_stream.py`` wraps backend streams, so held references may inflate
     pipe cost depending on the backend.
   - **Total cost**: allocations from all ``remote_store`` code including
     backends -- expected to vary by backend type.  Non-lazy backends
     (Memory, SQL) legitimately buffer; lazy backends should stay lean.

``tracemalloc`` is intentionally the right tool: it captures Python-level
allocations (what **remote-store** costs), not native buffers from ``boto3``,
``paramiko``, or ``azure-sdk``.  Snapshots are sampled per chunk via
``on_progress`` so the high-water mark during streaming is captured, not
just post-cleanup state.

Requires: ``docker compose -f benchmarks/infra/docker-compose.yml up -d``
Run with: ``pytest -m integration tests/e2e/test_streaming_integrity.py -s``
"""

from __future__ import annotations

import gc
import hashlib
import random
import tracemalloc
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from remote_store import Capability
from remote_store.ext.streams import ChecksumReader
from remote_store.ext.transfer import transfer
from tests.e2e.conftest import _azurite_available

if TYPE_CHECKING:
    from typing import BinaryIO

    from remote_store import Store

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

FILE_SIZE_MIN = 7 * 1_048_576  # 7 MiB
FILE_SIZE_MAX = 14 * 1_048_576  # 14 MiB
DRAIN_CHUNK = 1_048_576  # 1 MiB read chunks for checksum verification

# Pipe cost: transfer layer overhead (transfer.py + streams.py + _stream.py).
# Most backends read in _COPY_BUFSIZE (256 KiB) chunks; when Azure is the
# write destination, the Azure SDK's staged-block uploader issues 1 MiB
# reads and keeps the *previous* chunk alive until the next stage_block
# ack returns — so at sample time two 1 MiB buffers are live simultaneously
# (current + previously-staged).  Sources wrapped in io.BufferedReader
# (SFTP, sync Azure) attribute both chunks to the innermost Python frame
# above the C-level read (ProgressReader.read in ext/streams.py), which
# lands in this filter.  Azure-bridged hops use AsyncBackendSyncAdapter's
# _ChunkPullReader (RawIOBase, not wrapped in BufferedReader), so their
# reads are attributed to _async_to_sync_adapter and fall outside the pipe
# filter — observed at ~0.13 MiB in practice.  Threshold is an independent
# test-layer budget (not coupled to the backend's block size): if the SDK
# starts holding more than two chunks, or if the backend tunes its block
# size such that the pipe cost exceeds this ceiling, this test *should*
# fail loudly rather than silently track the new value.  See BUG-174.
PIPE_THRESHOLD = 2304 * 1024  # 2.25 MiB

# Total cost thresholds (as multipliers of file_size).
# Lazy-lazy hops carry a ~4 MiB floor from s3fs multipart upload staging
# (observed even with no PyArrow backend involved).  With 7 MiB minimum
# file size the factor must be > 4/7 ≈ 0.57.
LAZY_THRESHOLD_FACTOR = 0.65  # lazy backends: peak < 65% of file_size
NON_LAZY_THRESHOLD_FACTOR = 2.2  # non-lazy backends buffer the file; peak < 220%
# 2.0× base (source + destination copy) + ~0.2× headroom for Python bytearray
# growth over-allocation (~12.5%) and tracemalloc measurement noise.

# Bridged-Azure: AsyncAzureBackend wrapped in AsyncBackendSyncAdapter.
# ASYNC-084 preserves LAZY_READ so the adapter is classified lazy, but each
# chunk crosses a thread boundary (ASYNC-080) which adds per-chunk overhead.
# Threshold is wider than LAZY_THRESHOLD_FACTOR to absorb that overhead.
BRIDGED_AZURE_THRESHOLD_FACTOR = 0.80  # bridged-lazy: peak < 80% of file_size

PATH = "streaming-integrity-test.bin"

# tracemalloc filters -- transfer layer vs. all remote_store code.
# Anchored to remote_store paths to avoid matching dependency internals.
_PIPE_FILTERS = [
    tracemalloc.Filter(True, "*remote_store*transfer*"),
    tracemalloc.Filter(True, "*remote_store*streams*"),
    tracemalloc.Filter(True, "*remote_store*_stream*"),
]
_TOTAL_FILTER = [tracemalloc.Filter(True, "*remote_store*")]


# ---------------------------------------------------------------------------
# Measurement result
# ---------------------------------------------------------------------------


@dataclass
class HopResult:
    """Measurements collected for a single transfer hop."""

    hop: str
    file_size: int
    # Chunk behavior
    chunk_count: int = 0
    max_chunk: int = 0
    # Memory (bytes)
    pipe_peak: int = 0
    total_peak: int = 0
    # Classification
    src_lazy: bool = True
    dst_lazy: bool = True
    # Derived thresholds
    pipe_threshold: int = PIPE_THRESHOLD
    total_threshold: int = 0

    @property
    def both_lazy(self) -> bool:
        return self.src_lazy and self.dst_lazy

    @property
    def pipe_ok(self) -> bool:
        return self.pipe_peak < self.pipe_threshold

    @property
    def total_ok(self) -> bool:
        return self.total_peak < self.total_threshold

    @property
    def chunks_ok(self) -> bool:
        return self.chunk_count > 1 and self.max_chunk < self.file_size


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload(size: int) -> tuple[bytes, str]:
    """Generate a deterministic pseudo-random payload of *size* bytes with SHA-256."""
    rng = random.Random(42)  # noqa: S311 -- deterministic, not security
    data = rng.randbytes(size)
    digest = hashlib.sha256(data).hexdigest()
    return data, digest


def _verify_checksum(store: Store, path: str, expected: str) -> str:
    """Read *path* from *store* through ChecksumReader, assert SHA-256.

    Returns the computed hex digest for use in direct assertions.
    """
    raw: BinaryIO = store.read(path)
    stream = ChecksumReader(raw, algorithm="sha256")
    try:
        while stream.read(DRAIN_CHUNK):
            pass
        actual = stream.hexdigest()
    finally:
        stream.close()
    assert actual == expected, (
        f"Checksum mismatch after transfer to {store!r}: expected {expected[:16]}..., got {actual[:16]}..."
    )
    return actual


def _snapshot_filtered(filters: list[tracemalloc.Filter]) -> int:
    """Return total bytes currently allocated matching *filters*."""
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.filter_traces(filters).statistics("filename")
    return sum(stat.size for stat in stats)


def _measure_transfer(
    src: Store,
    src_name: str,
    dst: Store,
    dst_name: str,
    path: str,
    file_size: int,
    *,
    total_threshold_override: int | None = None,
) -> HopResult:
    """Transfer *path* from *src* to *dst*, collecting all measurements.

    Returns a ``HopResult`` with chunk behavior and two memory measurements
    (pipe layer and total remote_store), sampled per chunk during streaming.

    *total_threshold_override* lets callers supply a pre-computed threshold
    instead of the default factor-based one (used for bridged backends whose
    per-chunk thread crossing warrants a wider budget than pure-lazy hops).
    """
    gc.collect()
    chunks: list[int] = []
    pipe_peak = 0
    total_peak = 0

    def _sample(nbytes: int) -> None:
        nonlocal pipe_peak, total_peak
        chunks.append(nbytes)
        pipe_now = _snapshot_filtered(_PIPE_FILTERS)
        total_now = _snapshot_filtered(_TOTAL_FILTER)
        pipe_peak = max(pipe_peak, pipe_now)
        total_peak = max(total_peak, total_now)

    tracemalloc.start()
    try:
        transfer(src, path, dst, path, overwrite=True, on_progress=_sample)
        # Final sample after last write completes.
        _sample(0)
    finally:
        tracemalloc.stop()

    # Remove trailing zero from final _sample(0) for chunk stats.
    chunk_sizes = [c for c in chunks if c > 0]

    src_lazy = src.supports(Capability.LAZY_READ)
    dst_lazy = dst.supports(Capability.LAZY_READ)
    both_lazy = src_lazy and dst_lazy
    factor = LAZY_THRESHOLD_FACTOR if both_lazy else NON_LAZY_THRESHOLD_FACTOR
    total_threshold = total_threshold_override if total_threshold_override is not None else int(file_size * factor)

    return HopResult(
        hop=f"{src_name} -> {dst_name}",
        file_size=file_size,
        chunk_count=len(chunk_sizes),
        max_chunk=max(chunk_sizes) if chunk_sizes else 0,
        pipe_peak=pipe_peak,
        total_peak=total_peak,
        src_lazy=src_lazy,
        dst_lazy=dst_lazy,
        total_threshold=total_threshold,
    )


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
    print(f"  Streaming test seed: {seed} (reproduce with PYTHONHASHSEED={seed})")  # noqa: T201
    return random.Random(seed)  # noqa: S311


@pytest.fixture(scope="module")
def seeded_payload() -> tuple[bytes, str, int, random.Random]:
    """Random-sized (7--14 MiB) payload with its SHA-256 hex digest and RNG."""
    rng = _test_rng()
    size = rng.randint(FILE_SIZE_MIN, FILE_SIZE_MAX)
    data, digest = _make_payload(size)
    return data, digest, size, rng


@pytest.fixture
def store_chain():  # -> Iterator[list[tuple[str, Store]]]
    """Yield all available backends, including ``azure-bridged``.

    Extends the standard ``_build_store_chain()`` set (Memory, S3, SFTP,
    Azure, S3-PyArrow, SQLBlob) with an ``azure-bridged`` backend when
    Azurite is reachable.  The bridged backend wraps ``AsyncAzureBackend``
    in ``AsyncBackendSyncAdapter`` and validates the adapter end-to-end in
    the streaming integrity chain.  ASYNC-084 preserves ``LAZY_READ``, so
    the hop uses the wider ``BRIDGED_AZURE_THRESHOLD_FACTOR`` memory budget.
    """
    from remote_store import Store
    from tests.e2e.conftest import (
        AZURITE_CONN_STR,
        _build_store_chain,
        _CleanupEntry,
        _teardown_store_chain,
    )

    stores, cleanups = _build_store_chain()

    if _azurite_available():
        from azure.storage.blob import BlobServiceClient

        from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
        from remote_store.aio.backends._azure import AsyncAzureBackend

        bridged_tag = uuid.uuid4().hex[:8]
        bridged_container = f"e2e-stream-bridged-{bridged_tag}"
        bridged_service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        bridged_service.create_container(bridged_container)
        stores.append(
            (
                "azure-bridged",
                Store(
                    backend=AsyncBackendSyncAdapter(
                        AsyncAzureBackend(container=bridged_container, connection_string=AZURITE_CONN_STR)
                    )
                ),
            )
        )
        cleanups.append(_CleanupEntry("azure", {"service": bridged_service, "container": bridged_container}))

    yield stores
    _teardown_store_chain(stores, cleanups)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_HEADER = (
    "\n--- Streaming integrity report ---\n"
    f"  {'Hop':30s}  {'Chunks':>6s}  {'MaxChunk':>10s}  "
    f"{'Pipe':>10s}  {'Total':>10s}  {'Type':8s}  Status"
)


def _emit_report(results: list[HopResult]) -> list[str]:
    """Print a summary table and return failure messages for violations.

    Streaming violations are hard failures, not warnings.  Non-lazy
    destinations (e.g. SQL BLOB) are exempt from ``chunks_ok`` and
    ``pipe_ok`` because they call ``source.read()`` without a size limit,
    reading the full stream in one call.  This inflates chunk count to 1
    and inflates pipe measurements because ``tracemalloc`` attributes the
    full ``bytes`` allocation to the calling Python frame in
    ``_ErrorMappingStream.read()`` / ``ProgressReader.read()`` (ID-136).
    The ``total_ok`` check still applies to non-lazy destinations.
    """
    failures: list[str] = []
    print(_HEADER)  # noqa: T201
    for r in results:
        lazy_tag = "lazy" if r.both_lazy else "non-lazy"
        issues: list[str] = []
        # Non-lazy destinations call source.read() without a size limit,
        # reading the full stream at once.  Non-lazy sources return a full
        # BytesIO held by _stream.py, attributing the whole file to pipe
        # filters.  Either case inflates chunk count and pipe measurements.
        if not r.dst_lazy or not r.src_lazy:
            pass  # exempt from chunks_ok and pipe_ok; total_ok still applies
        else:
            if not r.chunks_ok:
                issues.append("chunks")
            if not r.pipe_ok:
                issues.append("pipe")
        if not r.total_ok:
            issues.append("total")
        status = "OK" if not issues else f"FAIL({','.join(issues)})"

        print(  # noqa: T201
            f"  {r.hop:30s}  {r.chunk_count:6d}  "
            f"{r.max_chunk / 1_048_576:7.2f} MiB  "
            f"{r.pipe_peak / 1_048_576:7.2f} MiB  "
            f"{r.total_peak / 1_048_576:7.2f} MiB  "
            f"{lazy_tag:8s}  {status}"
        )

        for issue in issues:
            if issue == "chunks":
                failures.append(
                    f"{r.hop}: not chunked (count={r.chunk_count}, max_chunk={r.max_chunk / 1_048_576:.2f} MiB)"
                )
            elif issue == "pipe":
                failures.append(
                    f"{r.hop}: pipe memory {r.pipe_peak / 1_048_576:.2f} MiB "
                    f"> threshold {r.pipe_threshold / 1_048_576:.2f} MiB"
                )
            elif issue == "total":
                failures.append(
                    f"{r.hop} ({lazy_tag}): total memory "
                    f"{r.total_peak / 1_048_576:.2f} MiB "
                    f"> threshold {r.total_threshold / 1_048_576:.2f} MiB"
                )
    return failures


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ID-050")
class TestStreamingIntegrity:
    """Round-robin transfer across all backends with checksum + memory checks."""

    def test_roundrobin_checksum_and_memory(
        self,
        store_chain: list[tuple[str, Store]],
        seeded_payload: tuple[bytes, str, int, random.Random],
        record_property: Any,
    ) -> None:
        """Transfer a randomly-sized file (7--14 MiB) around all backends in
        random order, verifying SHA-256 and streaming behavior at every hop.

        The chain always starts and ends with Memory.  Other backends are
        shuffled randomly so ordering bugs cannot hide behind a fixed chain.
        Unavailable backends are dropped.  The test requires at least one
        lazy (streaming) backend to be meaningful.

        Checksum mismatches **fail** the test (data integrity is non-negotiable).
        Memory and chunk behavior violations **fail** the test -- streaming
        is a core promise and violations are defects (BUG-161, BUG-162).
        Non-lazy destinations (SQL) are exempt from chunk-count checks
        because they must materialize the full stream by design (ID-136).
        """
        payload, expected_sha, file_size, rng = seeded_payload

        # Build chain: memory first, shuffled middle, memory last.
        memory_name, memory_store = store_chain[0]
        middle = list(store_chain[1:])
        rng.shuffle(middle)
        chain = [(memory_name, memory_store), *middle, (memory_name, memory_store)]

        order = " -> ".join(name for name, _ in chain)
        all_names = [name for name, _ in store_chain]
        skipped = sorted(
            {"s3", "sftp", "azure", "azure-bridged", "s3-pyarrow", "sql-blob"} - set(all_names),
        )

        # Surface test context in CI output (JUnit XML + failure messages).
        record_property("file_size_mib", f"{file_size / 1_048_576:.1f}")
        record_property("chain", order)
        if skipped:
            record_property("skipped_backends", ", ".join(skipped))

        size_str = f"{file_size / 1_048_576:.1f} MiB"
        skip_str = f"  Skipped backends: {', '.join(skipped)}" if skipped else ""
        # Visible with pytest -s; also embedded in assertion messages below.
        print(f"\n  File size: {size_str}")  # noqa: T201
        print(f"  Chain: {order}")  # noqa: T201
        if skipped:
            print(f"  Skipped: {', '.join(skipped)}")  # noqa: T201

        # Require at least one lazy backend for the test to be meaningful.
        has_lazy = any(store.supports(Capability.LAZY_READ) for _, store in chain)
        if not has_lazy:
            pytest.skip("No streaming (lazy) backend available")

        # -- Seed the file into the first store. ---------------------------
        memory_store.write(PATH, payload, overwrite=True)
        _verify_checksum(memory_store, PATH, expected_sha)

        # -- Round-robin with checksum + memory measurement. ---------------
        results: list[HopResult] = []

        for i in range(len(chain) - 1):
            src_name, src_store = chain[i]
            dst_name, dst_store = chain[i + 1]

            # Bridged-Azure hops carry per-chunk thread-crossing overhead
            # (ASYNC-080); use a wider threshold, but only when both sides are
            # lazy.  When either side is non-lazy (e.g. sql-blob source),
            # NON_LAZY_THRESHOLD_FACTOR (2.2) already has enough headroom.
            is_bridged_hop = "azure-bridged" in (src_name, dst_name)
            _src_lazy = src_store.supports(Capability.LAZY_READ)
            _dst_lazy = dst_store.supports(Capability.LAZY_READ)
            threshold_override = (
                int(file_size * BRIDGED_AZURE_THRESHOLD_FACTOR) if is_bridged_hop and _src_lazy and _dst_lazy else None
            )

            # Transfer with all measurements.
            result = _measure_transfer(
                src_store,
                src_name,
                dst_store,
                dst_name,
                PATH,
                file_size,
                total_threshold_override=threshold_override,
            )
            results.append(result)

            # Verify integrity at destination (hard fail).
            _verify_checksum(dst_store, PATH, expected_sha)

            # Delete from source (unless source == destination).
            if src_store is not dst_store:
                src_store.delete(PATH)

        # -- Final checksum on the last destination. -----------------------
        _final_name, final_store = chain[-1]
        _verify_checksum(final_store, PATH, expected_sha)

        # -- Report + assert streaming contract. ----------------------------
        failures = _emit_report(results)
        # Context header for CI failure messages (visible without -s).
        ctx = f"File: {size_str} | Chain: {order}"
        if skip_str:
            ctx += f" | {skip_str.strip()}"
        assert results, f"No hops executed. {ctx}"
        assert not failures, f"Streaming contract violations ({ctx}):\n" + "\n".join(failures)
