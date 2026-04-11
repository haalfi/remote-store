"""End-to-end streaming integrity test.

Proves three properties of the remote-store streaming contract:

1. **Data integrity** (hard fail) -- a 10 MiB file survives a full round-robin
   transfer across all available read/write backends with identical SHA-256 at
   each hop.
2. **Chunked streaming** (warning) -- ``transfer()`` reads data in multiple
   chunks, never as a single ``read()`` of the full file.  Verified via the
   ``on_progress`` callback which fires per chunk.
3. **Memory discipline** (warning) -- two memory measurements per hop, both
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
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
LAZY_THRESHOLD_FACTOR = 0.5  # lazy backends: peak < 50% of FILE_SIZE
NON_LAZY_THRESHOLD_FACTOR = 2.0  # non-lazy backends buffer the file; peak < 200%

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


def _backend_name(store: Store) -> str:
    """Return the backend's name string."""
    return store._backend.name


def _is_lazy_name(name: str) -> bool:
    """Return True if *name* is a lazy (streaming) backend."""
    return name not in _NON_LAZY_BACKENDS


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
) -> HopResult:
    """Transfer *path* from *src* to *dst*, collecting all measurements.

    Returns a ``HopResult`` with chunk behavior and two memory measurements
    (pipe layer and total remote_store), sampled per chunk during streaming.
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

    src_lazy = _is_lazy_name(src_name)
    dst_lazy = _is_lazy_name(dst_name)
    both_lazy = src_lazy and dst_lazy
    factor = LAZY_THRESHOLD_FACTOR if both_lazy else NON_LAZY_THRESHOLD_FACTOR

    return HopResult(
        hop=f"{src_name} -> {dst_name}",
        chunk_count=len(chunk_sizes),
        max_chunk=max(chunk_sizes) if chunk_sizes else 0,
        pipe_peak=pipe_peak,
        total_peak=total_peak,
        src_lazy=src_lazy,
        dst_lazy=dst_lazy,
        total_threshold=int(FILE_SIZE * factor),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded_payload() -> tuple[bytes, str]:
    """Deterministic 10 MiB payload with its SHA-256 hex digest."""
    return _make_payload()


# Store chain fixture -- builds stores directly using availability checks
# from conftest, so the test degrades its chain instead of being skipped.
# Tracks cleanup resources (boto3 clients, Azure services, SFTP paths)
# for proper teardown matching conftest patterns.


@dataclass
class _CleanupEntry:
    """Resources to clean up after test completes."""

    kind: str  # "s3", "sftp", "azure"
    extras: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def store_chain():  # -> Iterator[list[tuple[str, Store]]]
    """Yield a list of ``(name, store)`` pairs for all available backends.

    Always includes memory first.  Docker backends are only included when
    reachable.  SQL (SQLite in-memory) is always available.
    All infrastructure (buckets, containers, directories) is cleaned up
    after the test completes.
    """
    from remote_store import Store
    from remote_store.backends._memory import MemoryBackend

    stores: list[tuple[str, Store]] = []
    cleanups: list[_CleanupEntry] = []

    # Memory -- always available.
    mem = Store(backend=MemoryBackend())
    stores.append(("memory", mem))

    # S3 (s3fs)
    if _minio_available():
        import boto3

        from remote_store.backends._s3 import S3Backend
        from tests.e2e.conftest import (
            MINIO_ACCESS_KEY,
            MINIO_ENDPOINT,
            MINIO_SECRET_KEY,
        )

        tag = uuid.uuid4().hex[:8]
        bucket = f"e2e-stream-{tag}"
        client = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        stores.append(
            (
                "s3",
                Store(
                    backend=S3Backend(
                        bucket=bucket,
                        key=MINIO_ACCESS_KEY,
                        secret=MINIO_SECRET_KEY,
                        region_name="us-east-1",
                        endpoint_url=MINIO_ENDPOINT,
                    )
                ),
            )
        )
        cleanups.append(_CleanupEntry("s3", {"client": client, "bucket": bucket}))

    # SFTP
    if _sftp_available():
        import paramiko

        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
        from tests.e2e.conftest import SFTP_HOST, SFTP_PASS, SFTP_PORT, SFTP_USER

        tag = uuid.uuid4().hex[:8]
        base_path = f"/upload/e2e-stream-{tag}"
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        try:
            sftp.mkdir(base_path)
        finally:
            sftp.close()
            transport.close()
        stores.append(
            (
                "sftp",
                Store(
                    backend=SFTPBackend(
                        host=SFTP_HOST,
                        port=SFTP_PORT,
                        username=SFTP_USER,
                        password=SFTP_PASS,
                        base_path=base_path,
                        host_key_policy=HostKeyPolicy.AUTO_ADD,
                        connect_kwargs={"allow_agent": False, "look_for_keys": False},
                    )
                ),
            )
        )
        cleanups.append(_CleanupEntry("sftp", {"base_path": base_path}))

    # Azure (Azurite)
    if _azurite_available():
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend
        from tests.e2e.conftest import AZURITE_CONN_STR

        tag = uuid.uuid4().hex[:8]
        container = f"e2e-stream-{tag}"
        service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
        service.create_container(container)
        stores.append(
            (
                "azure",
                Store(backend=AzureBackend(container=container, connection_string=AZURITE_CONN_STR)),
            )
        )
        cleanups.append(_CleanupEntry("azure", {"service": service, "container": container}))

    # S3-PyArrow
    if _s3_pyarrow_available():
        import boto3

        from remote_store.backends._s3_pyarrow import S3PyArrowBackend
        from tests.e2e.conftest import (
            MINIO_ACCESS_KEY,
            MINIO_ENDPOINT,
            MINIO_SECRET_KEY,
        )

        tag = uuid.uuid4().hex[:8]
        bucket = f"e2e-stream-pa-{tag}"
        client = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            region_name="us-east-1",
        )
        client.create_bucket(Bucket=bucket)
        stores.append(
            (
                "s3-pyarrow",
                Store(
                    backend=S3PyArrowBackend(
                        bucket=bucket,
                        key=MINIO_ACCESS_KEY,
                        secret=MINIO_SECRET_KEY,
                        region_name="us-east-1",
                        endpoint_url=MINIO_ENDPOINT,
                    )
                ),
            )
        )
        cleanups.append(_CleanupEntry("s3", {"client": client, "bucket": bucket}))

    # SQL (SQLite in-memory) -- always available.
    try:
        from remote_store.backends._sqlalchemy import SQLBlobBackend

        stores.append(("sql-blob", Store(backend=SQLBlobBackend(url="sqlite://"))))
    except ImportError:
        pass

    yield stores

    # -- Teardown: close stores, then clean up infrastructure. -------------
    for _name, store in stores:
        store.close()

    for entry in cleanups:
        if entry.kind == "s3":
            from tests.e2e.conftest import _paginated_delete_s3

            _paginated_delete_s3(entry.extras["client"], entry.extras["bucket"])
            entry.extras["client"].delete_bucket(Bucket=entry.extras["bucket"])

        elif entry.kind == "sftp":
            from tests.e2e.conftest import SFTP_HOST, SFTP_PASS, SFTP_PORT, SFTP_USER, _sftp_cleanup

            _sftp_cleanup(SFTP_HOST, SFTP_PORT, SFTP_USER, entry.extras["base_path"], SFTP_PASS)

        elif entry.kind == "azure":
            entry.extras["service"].delete_container(entry.extras["container"])
            entry.extras["service"].close()


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
        store_chain: list[tuple[str, Store]],
        seeded_payload: tuple[bytes, str],
    ) -> None:
        """Transfer a 10 MiB file around all backends, verifying SHA-256
        and streaming behavior at every hop.

        Chain: Memory -> S3 -> SFTP -> Azure -> S3-PyArrow -> SQL -> Memory
        Unavailable backends are dropped from the chain.  The test requires
        at least one lazy (streaming) backend to be meaningful.

        Checksum mismatches **fail** the test (data integrity is non-negotiable).
        Memory and chunk behavior violations **warn** so the test surfaces
        regressions without blocking CI.
        """
        payload, expected_sha = seeded_payload

        # Close the loop: append memory again as final destination.
        chain = list(store_chain)
        memory_name, memory_store = chain[0]
        chain.append((memory_name, memory_store))

        # Require at least one lazy backend for the test to be meaningful.
        has_lazy = any(_is_lazy_name(name) for name, _ in chain)
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

            # Transfer with all measurements.
            result = _measure_transfer(src_store, src_name, dst_store, dst_name, PATH)
            results.append(result)

            # Verify integrity at destination (hard fail).
            _verify_checksum(dst_store, PATH, expected_sha)

            # Delete from source (unless source == destination).
            if src_store is not dst_store:
                src_store.delete(PATH)

        # -- Final direct checksum on the last destination. ----------------
        _final_name, final_store = chain[-1]
        final_digest = _verify_checksum(final_store, PATH, expected_sha)
        assert final_digest == expected_sha, "Round-robin checksum mismatch at final destination"

        # -- Report (visible with pytest -s, warnings always visible). -----
        _emit_report(results)
