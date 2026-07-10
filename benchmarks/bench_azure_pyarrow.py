"""Benchmark: Azure PyArrow read paths — full materialization vs range reader.

Compares the two read strategies for Parquet column pruning on Azure:

- **Tier 2 (master):** ``store.read_bytes()`` -> ``pa.BufferReader`` -> full file.
- **Tier 3 (read_seekable):** ``store.read_seekable()`` -> ``_AzureRangeReader``
  -> HTTP Range requests, wrapped in ``pa.PythonFile``.

Sweeps four dimensions:
- **File size:** 1 MB, 10 MB, 100 MB (row count scales with column count fixed)
- **Column selectivity:** 3/50, 10/50, 25/50, 50/50
- **Latency:** 0, 10, 30, 50 ms (via Toxiproxy)
- **File count:** 1, 5, 10 (batch reads of identically-shaped files)

Phase 3 adds a ``pyarrow.dataset`` scan comparison: ``ds.dataset()`` via the
``pyarrow_fs()`` adapter vs manual ``pq.read_table`` loop, testing whether
PyArrow's dataset I/O scheduling works correctly with the range reader.

Usage::

    docker compose -f infra/docker-compose.yml up -d
    hatch run python benchmarks/bench_azure_pyarrow.py
    docker compose -f infra/docker-compose.yml down -v
"""

from __future__ import annotations

import io
import statistics
import time
import uuid
from dataclasses import dataclass
from typing import Any

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from benchmarks._toxiproxy import (
    AZURITE_CONN_STR,
    set_latency,
)
from benchmarks._toxiproxy import (
    TOXIPROXY_AZURITE_CONN_STR as TOXIPROXY_CONN_STR,
)
from remote_store import Store
from remote_store.backends._azure import AzureBackend
from remote_store.ext.arrow import pyarrow_fs

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NUM_COLUMNS = 50
LATENCIES_MS = [0, 10, 30, 50]
SELECTIVITIES = [3, 10, 25, 50]  # columns to select out of 50
FILE_COUNTS = [1, 5, 10]
ITERATIONS = 3

# Target file sizes (approximate, actual depends on Parquet encoding).
# Each row is 50 int64 columns = 400 bytes raw; Parquet compresses ~2:1.
SIZE_CONFIGS = [
    ("~1 MB", 5_000),
    ("~10 MB", 50_000),
    ("~100 MB", 500_000),
]


# ---------------------------------------------------------------------------
# Read strategies
# ---------------------------------------------------------------------------


def read_tier2(store: Store, path: str, cols: list[str]) -> pa.Table:
    """Full-file materialization (master behavior)."""
    data = store.read_bytes(path)
    return pq.read_table(pa.BufferReader(pa.py_buffer(data)), columns=cols)


def read_tier3(store: Store, path: str, cols: list[str]) -> pa.Table:
    """Range reader via read_seekable()."""
    stream = store.read_seekable(path)
    try:
        return pq.read_table(pa.PythonFile(stream, mode="r"), columns=cols)
    finally:
        stream.close()


def count_range_requests(store: Store, path: str, cols: list[str]) -> int:
    """Read once and return number of readinto() calls."""
    from remote_store.backends._azure import _AzureRangeReader

    stream = store.read_seekable(path)
    counter = 0
    inner = getattr(stream, "_inner", None)
    if isinstance(inner, _AzureRangeReader):
        orig = inner.readinto

        def counting(b: bytearray | memoryview) -> int:
            nonlocal counter
            counter += 1
            return orig(b)

        inner.readinto = counting  # type: ignore[assignment]
    try:
        pq.read_table(pa.PythonFile(stream, mode="r"), columns=cols)
    finally:
        stream.close()
    return counter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class Result:
    label: str
    file_size: int
    num_cols_selected: int
    latency_ms: int
    file_count: int
    t2_median_ms: float
    t3_median_ms: float
    range_requests: int

    @property
    def speedup(self) -> float:
        return self.t2_median_ms / self.t3_median_ms if self.t3_median_ms > 0 else 0.0


def time_fn(fn, *args, iterations: int = ITERATIONS) -> float:
    """Return median duration in ms."""
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn(*args)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def make_parquet(num_rows: int) -> bytes:
    """Create a 50-column int64 Parquet file in memory."""
    cols = {f"col_{i}": pa.array(range(num_rows), type=pa.int64()) for i in range(NUM_COLUMNS)}
    buf = io.BytesIO()
    pq.write_table(pa.table(cols), buf)
    return buf.getvalue()


def col_names(n: int) -> list[str]:
    return [f"col_{i}" for i in range(n)]


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark() -> None:
    from azure.storage.blob import BlobServiceClient

    tag = uuid.uuid4().hex[:8]
    container = f"bench-pa-{tag}"

    service = BlobServiceClient.from_connection_string(AZURITE_CONN_STR)
    service.create_container(container)

    try:
        _run_all(container)
    finally:
        set_latency(0)
        service.delete_container(container)
        service.close()


def _run_all(container: str) -> None:
    setup = AzureBackend(container=container, connection_string=AZURITE_CONN_STR, hns=False)
    setup_store = Store(backend=setup)
    results: list[Result] = []

    # ---------------------------------------------------------------
    # Phase 1: File size x selectivity x latency (single file)
    # ---------------------------------------------------------------
    print("=" * 78)
    print("Phase 1: File size x selectivity x latency (single file)")
    print("=" * 78)

    for size_label, num_rows in SIZE_CONFIGS:
        data = make_parquet(num_rows)
        file_size = len(data)
        path = f"wide_{num_rows}.parquet"
        setup_store.write(path, data, overwrite=True)
        print(f"\n--- {size_label} ({file_size:,} bytes, {num_rows:,} rows) ---")

        hdr = f"{'Select':>8} {'Lat ms':>7} {'Reqs':>5}"
        hdr += f" {'T2 ms':>10} {'T3 ms':>10} {'Speedup':>8}"
        print(hdr)
        print("-" * 60)

        for n_cols in SELECTIVITIES:
            cols = col_names(n_cols)

            # Count requests once at 0ms latency
            direct = Store(
                backend=AzureBackend(
                    container=container,
                    connection_string=AZURITE_CONN_STR,
                    hns=False,
                )
            )
            reqs = count_range_requests(direct, path, cols)
            direct._backend.close()  # type: ignore[union-attr]

            for lat in LATENCIES_MS:
                set_latency(lat)
                backend = AzureBackend(
                    container=container,
                    connection_string=TOXIPROXY_CONN_STR,
                    hns=False,
                )
                store = Store(backend=backend)

                # Warm up
                read_tier2(store, path, cols)
                read_tier3(store, path, cols)

                t2 = time_fn(read_tier2, store, path, cols)
                t3 = time_fn(read_tier3, store, path, cols)

                r = Result(
                    size_label,
                    file_size,
                    n_cols,
                    lat,
                    1,
                    t2,
                    t3,
                    reqs,
                )
                results.append(r)

                marker = "<--" if r.speedup >= 1.0 else ""
                row = f"{n_cols:>5}/50 {lat:>7} {reqs:>5}"
                row += f" {t2:>10.1f} {t3:>10.1f}"
                row += f" {r.speedup:>7.2f}x {marker}"
                print(row)

                backend.close()

    # ---------------------------------------------------------------
    # Phase 2: Batch reads (multiple files, fixed selectivity)
    # ---------------------------------------------------------------
    print()
    print("=" * 78)
    print("Phase 2: Batch reads (file count x latency, 3/50 cols, ~10 MB)")
    print("=" * 78)

    batch_rows = 50_000
    batch_data = make_parquet(batch_rows)
    batch_size = len(batch_data)
    max_files = max(FILE_COUNTS)
    for i in range(max_files):
        setup_store.write(f"batch/file_{i:03d}.parquet", batch_data, overwrite=True)

    cols = col_names(3)
    print(f"\nFile size: {batch_size:,} bytes each")

    hdr = f"{'Files':>6} {'Lat ms':>7}"
    hdr += f" {'T2 ms':>10} {'T3 ms':>10} {'Speedup':>8}"
    print(hdr)
    print("-" * 50)

    for n_files in FILE_COUNTS:
        paths = [f"batch/file_{i:03d}.parquet" for i in range(n_files)]
        for lat in LATENCIES_MS:
            set_latency(lat)
            backend = AzureBackend(
                container=container,
                connection_string=TOXIPROXY_CONN_STR,
                hns=False,
            )
            store = Store(backend=backend)

            def batch_t2(_s: Store = store, _ps: list[str] = paths) -> None:
                for p in _ps:
                    read_tier2(_s, p, cols)

            def batch_t3(_s: Store = store, _ps: list[str] = paths) -> None:
                for p in _ps:
                    read_tier3(_s, p, cols)

            # Warm up
            batch_t2()
            batch_t3()

            t2 = time_fn(batch_t2)
            t3 = time_fn(batch_t3)
            speedup = t2 / t3 if t3 > 0 else 0.0

            marker = "<--" if speedup >= 1.0 else ""
            row = f"{n_files:>6} {lat:>7}"
            row += f" {t2:>10.1f} {t3:>10.1f}"
            row += f" {speedup:>7.2f}x {marker}"
            print(row)

            backend.close()

    # ---------------------------------------------------------------
    # Phase 3: Dataset scan (pyarrow.dataset via adapter)
    # ---------------------------------------------------------------
    print()
    print("=" * 78)
    print("Phase 3: Dataset scan (ds.dataset() via pyarrow_fs adapter)")
    print("=" * 78)

    # Write dataset files into a subdirectory for ds.dataset() discovery.
    ds_rows = 50_000
    ds_data = make_parquet(ds_rows)
    ds_size = len(ds_data)
    ds_file_counts = [1, 5, 10]
    max_ds_files = max(ds_file_counts)
    for i in range(max_ds_files):
        setup_store.write(f"dataset/file_{i:03d}.parquet", ds_data, overwrite=True)

    ds_cols = col_names(3)
    print(f"\nFile size: {ds_size:,} bytes each, selecting 3/50 columns")
    print("Compares: manual pq.read_table loop (Tier 3) vs ds.dataset() scan")

    hdr = f"{'Files':>6} {'Lat ms':>7}"
    hdr += f" {'Loop ms':>10} {'DS ms':>10} {'DS/Loop':>8}"
    print(hdr)
    print("-" * 50)

    for n_files in ds_file_counts:
        ds_paths = [f"dataset/file_{i:03d}.parquet" for i in range(n_files)]
        for lat in [0, 10, 30]:
            set_latency(lat)
            backend = AzureBackend(
                container=container,
                connection_string=TOXIPROXY_CONN_STR,
                hns=False,
            )
            store = Store(backend=backend)
            fs = pyarrow_fs(store, materialization_threshold=0)

            def loop_read(
                _s: Store = store,
                _ps: list[str] = ds_paths,
                _c: list[str] = ds_cols,
            ) -> None:
                for p in _ps:
                    read_tier3(_s, p, _c)

            def dataset_read(
                _fs: Any = fs,
                _c: list[str] = ds_cols,
            ) -> None:
                dataset = ds.dataset(
                    "dataset/",
                    format="parquet",
                    filesystem=_fs,
                )
                dataset.to_table(columns=_c)

            # Warm up
            loop_read()
            dataset_read()

            t_loop = time_fn(loop_read)
            t_ds = time_fn(dataset_read)
            ratio = t_ds / t_loop if t_loop > 0 else 0.0

            marker = "<--" if ratio <= 1.1 else ""
            row = f"{n_files:>6} {lat:>7}"
            row += f" {t_loop:>10.1f} {t_ds:>10.1f}"
            row += f" {ratio:>7.2f}x {marker}"
            print(row)

            backend.close()

    setup.close()

    # ---------------------------------------------------------------
    # Summary: crossover analysis
    # ---------------------------------------------------------------
    print()
    print("=" * 78)
    print("Summary: where range reader wins (speedup >= 1.0x)")
    print("=" * 78)
    wins = [r for r in results if r.speedup >= 1.0]
    losses = [r for r in results if r.speedup < 1.0]
    print(f"Wins:   {len(wins)} / {len(results)} scenarios")
    print(f"Losses: {len(losses)} / {len(results)} scenarios")
    if wins:
        print("\nWinning scenarios:")
        for r in wins:
            print(
                f"  {r.label:>8}, {r.num_cols_selected}/50 cols, "
                f"{r.latency_ms}ms lat: "
                f"T2={r.t2_median_ms:.0f}ms T3={r.t3_median_ms:.0f}ms "
                f"({r.speedup:.2f}x)"
            )


if __name__ == "__main__":
    run_benchmark()
