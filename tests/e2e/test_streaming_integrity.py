"""End-to-end streaming integrity test.

Proves three properties of the remote-store streaming contract:

1. **Data integrity** (hard fail) -- a 10 MiB file survives a full round-robin
   transfer across every read/write backend with identical SHA-256 at each hop.
2. **Chunked streaming** (warning) -- ``transfer()`` reads data in multiple
   chunks, never as a single ``read()`` of the full file.  Verified via the
   ``on_progress`` callback which fires per chunk.
3. **Memory discipline** (warning) -- two memory measurements per hop, both
   filtered to ``remote_store`` source files only (dependencies excluded):

   - **Pipe cost**: allocations from the transfer layer
     (``ext/transfer.py``, ``ext/streams.py``, ``_stream.py``) -- should
     always be tiny regardless of backends.
   - **Total cost**: allocations from all ``remote_store`` code including
     backends -- expected to vary by backend type.  Non-lazy backends
     (Memory, SQL) legitimately buffer; lazy backends should stay lean.

``tracemalloc`` is intentionally the right tool: it captures Python-level
allocations (what **remote-store** costs), not native buffers from ``boto3``,
``paramiko``, or ``azure-sdk``.  Snapshots are sampled per chunk via
``on_progress`` so the high-water mark during streaming is captured, not
just post-cleanup state.

Requires: ``docker compose -f benchmarks/infra/docker-compose.yml up -d``
"""

from __future__ import annotations

import gc
import hashlib
import random
import tracemalloc
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from remote_store.ext.streams import ChecksumReader
from remote_store.ext.transfer import transfer
from tests.e2e.conftest import (
    _azurite_available,
    _minio_available,
    _s3_pyarrow_available,
    _sftp_available,
)

if TYPE_CHECKING:
    from typing import BinaryIO

    from remote_store import Store

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

FILE_SIZE = 10 * 1_048_576  # 10 MiB
DRAIN_CHUNK = 1_048_576  # 1 MiB read chunks for checksum verification

# Pipe cost: transfer layer should be tiny regardless of backends.
PIPE_THRESHOLD = 1 * 1_048_576  # 1 MiB -- transfer.py + streams.py + _stream.py

# Total cost thresholds (as multipliers of FILE_SIZE).
LAZY_THRESHOLD_FACTOR = 0.5  # lazy backends: peak < 5 MiB for a 10 MiB file
NON_LAZY_THRESHOLD_FACTOR = 2.0  # non-lazy backends buffer the file; allow headroom

# Backends that buffer entire files in Python memory by design.
_NON_LAZY_BACKENDS = frozenset({"memory", "sql-blob"})

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
# Custom warning
# ---------------------------------------------------------------------------


class StreamingMemoryWarning(UserWarning):
    """Emitted when a transfer hop exceeds a memory threshold."""


# ---------------------------------------------------------------------------
# Measurement result
# ---------------------------------------------------------------------------


@dataclass
class HopResult:
    """Measurements collected for a single transfer hop."""

    hop: str
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
        return self.chunk_count > 1 and self.max_chunk < FILE_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload() -> tuple[bytes, str]:
    """Generate a deterministic pseudo-random 10 MiB payload and its SHA-256."""
    rng = random.Random(42)  # noqa: S311 -- deterministic, not security
    data = rng.randbytes(FILE_SIZE)
    digest = hashlib.sha256(data).hexdigest()
    return data, digest


def _verify_checksum(store: Store, path: str, expected: str) -> None:
    """Read *path* from *store* through ChecksumReader, assert SHA-256."""
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


def _is_lazy(store: Store) -> bool:
    """Return True if the backend streams lazily (does not buffer full file)."""
    return store._backend.name not in _NON_LAZY_BACKENDS


def _snapshot_filtered(filters: list[tracemalloc.Filter]) -> int:
    """Return total bytes currently allocated matching *filters*."""
    snapshot = tracemalloc.take_snapshot()
    stats = snapshot.filter_traces(filters).statistics("filename")
    return sum(stat.size for stat in stats)


def _measure_transfer(
    src: Store,
    dst: Store,
    path: str,
) -> HopResult:
    """Transfer *path* from *src* to *dst*, collecting all measurements.

    Returns a ``HopResult`` with chunk behavior and two memory measurements
    (pipe layer and total remote_store), sampled per chunk during streaming.
    """
    src_name = src._backend.name
    dst_name = dst._backend.name

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

    both_lazy = _is_lazy(src) and _is_lazy(dst)
    factor = LAZY_THRESHOLD_FACTOR if both_lazy else NON_LAZY_THRESHOLD_FACTOR

    return HopResult(
        hop=f"{src_name} -> {dst_name}",
        chunk_count=len(chunk_sizes),
        max_chunk=max(chunk_sizes) if chunk_sizes else 0,
        pipe_peak=pipe_peak,
        total_peak=total_peak,
        src_lazy=_is_lazy(src),
        dst_lazy=_is_lazy(dst),
        total_threshold=int(FILE_SIZE * factor),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded_payload() -> tuple[bytes, str]:
    """Deterministic 10 MiB payload with its SHA-256 hex digest."""
    return _make_payload()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_HEADER = (
    "\n--- Streaming integrity report ---\n"
    f"  {'Hop':30s}  {'Chunks':>6s}  {'MaxChunk':>10s}  "
    f"{'Pipe':>10s}  {'Total':>10s}  {'Type':8s}  Status"
)


def _emit_report(results: list[HopResult]) -> None:
    """Print a summary table and emit warnings for threshold violations."""
    print(_HEADER)  # noqa: T201
    for r in results:
        lazy_tag = "lazy" if r.both_lazy else "non-lazy"
        issues: list[str] = []
        if not r.chunks_ok:
            issues.append("chunks")
        if not r.pipe_ok:
            issues.append("pipe")
        if not r.total_ok:
            issues.append("total")
        status = "OK" if not issues else f"WARN({','.join(issues)})"

        print(  # noqa: T201
            f"  {r.hop:30s}  {r.chunk_count:6d}  "
            f"{r.max_chunk / 1_048_576:7.2f} MiB  "
            f"{r.pipe_peak / 1_048_576:7.2f} MiB  "
            f"{r.total_peak / 1_048_576:7.2f} MiB  "
            f"{lazy_tag:8s}  {status}"
        )

        if not r.chunks_ok:
            warnings.warn(
                f"{r.hop}: not chunked (count={r.chunk_count}, max_chunk={r.max_chunk / 1_048_576:.2f} MiB)",
                StreamingMemoryWarning,
                stacklevel=2,
            )
        if not r.pipe_ok:
            warnings.warn(
                f"{r.hop}: pipe memory {r.pipe_peak / 1_048_576:.2f} MiB "
                f"> threshold {r.pipe_threshold / 1_048_576:.2f} MiB",
                StreamingMemoryWarning,
                stacklevel=2,
            )
        if not r.total_ok:
            warnings.warn(
                f"{r.hop} ({lazy_tag}): total memory {r.total_peak / 1_048_576:.2f} MiB "
                f"> threshold {r.total_threshold / 1_048_576:.2f} MiB",
                StreamingMemoryWarning,
                stacklevel=2,
            )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ID-050")
class TestStreamingIntegrity:
    """Round-robin transfer across all backends with checksum + memory checks."""

    def test_roundrobin_checksum_and_memory(
        self,
        memory_lake: Store,
        s3_lake: Store,
        sftp_lake: Store,
        azurite_lake: Store,
        s3_pyarrow_lake: Store,
        sql_lake: Store,
        seeded_payload: tuple[bytes, str],
    ) -> None:
        """Transfer a 10 MiB file around all backends, verifying SHA-256
        and streaming behavior at every hop.

        Chain: Memory -> S3 -> SFTP -> Azure -> S3-PyArrow -> SQL -> Memory
        Unavailable backends are dropped from the chain.  The test requires
        at least one non-Memory backend to be meaningful.

        Checksum mismatches **fail** the test (data integrity is non-negotiable).
        Streaming violations (chunk count, memory thresholds) **warn** so the
        test surfaces regressions without blocking CI.
        """
        payload, expected_sha = seeded_payload

        # -- Build the chain dynamically from available backends. -----------
        chain: list[tuple[str, Store]] = [("memory", memory_lake)]

        if _minio_available():
            chain.append(("s3", s3_lake))
        if _sftp_available():
            chain.append(("sftp", sftp_lake))
        if _azurite_available():
            chain.append(("azure", azurite_lake))
        if _s3_pyarrow_available():
            chain.append(("s3-pyarrow", s3_pyarrow_lake))
        # SQL is always available (SQLite in-memory).
        chain.append(("sql", sql_lake))
        # Return to memory to close the loop.
        chain.append(("memory", memory_lake))

        if len(chain) < 3:  # need at least memory -> X -> memory
            pytest.skip("No Docker backends available for round-robin")

        # -- Seed the file into the first store. ---------------------------
        memory_lake.write(PATH, payload, overwrite=True)
        _verify_checksum(memory_lake, PATH, expected_sha)

        # -- Round-robin with checksum + memory measurement. ---------------
        results: list[HopResult] = []

        for i in range(len(chain) - 1):
            _src_name, src_store = chain[i]
            _dst_name, dst_store = chain[i + 1]

            # Transfer with all measurements.
            result = _measure_transfer(src_store, dst_store, PATH)
            results.append(result)

            # Verify integrity at destination (hard fail).
            _verify_checksum(dst_store, PATH, expected_sha)

            # Delete from source (unless source == destination).
            if src_store is not dst_store:
                src_store.delete(PATH)

        # -- Report (visible with pytest -s, warnings always visible). -----
        _emit_report(results)
