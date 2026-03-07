"""Benchmark: PyArrow adapter read tiers -- Tier 1 (native) vs Tier 2/3.

Measures the overhead that Tier 1 (native FS delegation) eliminates.

Part 1 always runs: Local backend showing Tier 2 overhead vs native PyArrow FS.
Part 2 requires ``--s3`` and MinIO: actual Tier 1 vs Tier 2 A/B comparison.

Usage::

    python benchmarks/bench_pyarrow_tier1.py
    python benchmarks/bench_pyarrow_tier1.py --s3
    python benchmarks/bench_pyarrow_tier1.py --s3 --sizes 1024,65536 --rounds 200
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import pyarrow.fs as pafs  # type: ignore[import-untyped]

from remote_store import Store
from remote_store.backends._local import LocalBackend
from remote_store.ext.arrow import StoreFileSystemHandler, pyarrow_fs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_SIZES = [1024, 65_536, 1_048_576, 10_485_760]
_SEP = "-" * 110


def _human_size(n: int) -> str:
    if n >= 1_048_576:
        return f"{n // 1_048_576} MB"
    if n >= 1024:
        return f"{n // 1024} KB"
    return f"{n} B"


def _bench(fn: Any, rounds: int, warmup: int = 5) -> dict[str, float]:
    """Run *fn()* for *warmup* + *rounds* iterations, return timing stats in microseconds."""
    for _ in range(warmup):
        fn()

    times: list[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)

    return {
        "mean_us": statistics.mean(times) * 1e6,
        "median_us": statistics.median(times) * 1e6,
        "stdev_us": statistics.stdev(times) * 1e6 if len(times) > 1 else 0.0,
        "min_us": min(times) * 1e6,
        "max_us": max(times) * 1e6,
        "p95_us": sorted(times)[int(len(times) * 0.95)] * 1e6,
    }


def _print_header() -> None:
    print(f"{'Size':>10} | {'Method':^30} | {'Mean':>10} | {'Median':>10} | {'P95':>10} | {'Stdev':>10} | {'Min':>10}")
    print(_SEP)


def _print_row(size_label: str, method: str, s: dict[str, float]) -> None:
    print(
        f"{size_label:>10} | {method:<30} | {s['mean_us']:>8.1f}us | "
        f"{s['median_us']:>8.1f}us | {s['p95_us']:>8.1f}us | "
        f"{s['stdev_us']:>8.1f}us | {s['min_us']:>8.1f}us"
    )


def _print_speedup(label: str, fast_us: float, slow_us: float) -> None:
    if fast_us > 0:
        delta = slow_us - fast_us
        ratio = slow_us / fast_us
        print(f"{'':>10} | {label:<30} | {delta:>+7.1f}us ({ratio:.2f}x)")
    print(_SEP)


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Part 1: Local backend -- Tier 2 overhead baseline
# ---------------------------------------------------------------------------


def run_local_benchmark(sizes: list[int], rounds: int) -> None:
    """Compare PyArrow LocalFileSystem (Tier 1 equivalent) vs adapter Tier 2."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Write test files
        files: dict[int, str] = {}
        for size in sizes:
            name = f"test_{size}.bin"
            (root / name).write_bytes(b"X" * size)
            files[size] = name

        backend = LocalBackend(root=tmp)
        store = Store(backend=backend)
        local_fs = pafs.LocalFileSystem()
        adapter_fs = pyarrow_fs(store)

        probe = StoreFileSystemHandler(store)
        print(f"Tier 1 active for LocalBackend: {probe._native_fs is not None}")
        print("  (Expected: False -- Tier 1 activates for S3PyArrowBackend)")
        print()
        _print_header()

        for size in sizes:
            fname = files[size]
            native_path = str(root / fname)
            results: list[tuple[str, dict[str, float]]] = []

            def read_native(p: str = native_path) -> bytes:
                f = local_fs.open_input_file(p)
                data = f.read()
                f.close()
                return data

            results.append(("PA LocalFS (Tier 1 equiv)", _bench(read_native, rounds)))

            def read_adapter(n: str = fname) -> bytes:
                f = adapter_fs.open_input_file(n)
                data = f.read()
                f.close()
                return data

            results.append(("Adapter Tier 2", _bench(read_adapter, rounds)))

            def read_stream(n: str = fname) -> bytes:
                f = adapter_fs.open_input_stream(n)
                data = f.read()
                f.close()
                return data

            results.append(("Adapter open_input_stream", _bench(read_stream, rounds)))

            def read_store(n: str = fname) -> bytes:
                return store.read_bytes(n)

            results.append(("Store.read_bytes (raw)", _bench(read_store, rounds)))

            label = _human_size(size)
            for i, (method, s) in enumerate(results):
                _print_row(label if i == 0 else "", method, s)

            _print_speedup(
                ">> Tier2/Tier1 overhead:",
                results[0][1]["mean_us"],
                results[1][1]["mean_us"],
            )

        print()
        print("Interpretation:")
        print("  'PA LocalFS' = what Tier 1 achieves for native backends")
        print("  'Adapter Tier 2' = get_file_info() + read_bytes() + BufferReader")
        print("  Overhead = per-read cost that Tier 1 eliminates")


# ---------------------------------------------------------------------------
# Part 2: S3PyArrow via MinIO -- actual Tier 1 A/B comparison
# ---------------------------------------------------------------------------

_MINIO_ENDPOINT = "http://127.0.0.1:9000"
_MINIO_KEY = "minioadmin"
_MINIO_SECRET = "minioadmin"
_MINIO_REGION = "us-east-1"


def run_s3_pyarrow_benchmark(sizes: list[int], rounds: int) -> None:
    """A/B comparison: Tier 1 (native) vs Tier 2 (forced) on S3PyArrowBackend."""
    import boto3

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    client = boto3.client(
        "s3",
        endpoint_url=_MINIO_ENDPOINT,
        aws_access_key_id=_MINIO_KEY,
        aws_secret_access_key=_MINIO_SECRET,
        region_name=_MINIO_REGION,
    )

    bucket = "bench-tier1-test"
    with contextlib.suppress(client.exceptions.BucketAlreadyOwnedByYou):
        client.create_bucket(Bucket=bucket)

    try:
        backend = S3PyArrowBackend(
            bucket=bucket,
            key=_MINIO_KEY,
            secret=_MINIO_SECRET,
            region_name=_MINIO_REGION,
            endpoint_url=_MINIO_ENDPOINT,
        )
        store = Store(backend=backend)

        for size in sizes:
            backend.write(f"test_{size}.bin", b"X" * size, overwrite=True)

        # Tier 1 adapter (normal)
        adapter_fs = pyarrow_fs(store)

        # Tier 2 adapter (native FS forcibly disabled)
        handler_t2 = StoreFileSystemHandler(store)
        handler_t2._native_fs = None
        handler_t2._native_path_fn = None
        adapter_fs_t2 = pafs.PyFileSystem(handler_t2)

        probe = StoreFileSystemHandler(store)
        tier1_active = probe._native_fs is not None
        print(f"Tier 1 active for S3PyArrowBackend: {tier1_active}")
        if not tier1_active:
            print("  WARNING: Tier 1 not active -- results show Tier 2 vs Tier 2")
        print()
        _print_header()

        for size in sizes:
            fname = f"test_{size}.bin"
            results: list[tuple[str, dict[str, float]]] = []

            def read_tier1(n: str = fname) -> bytes:
                f = adapter_fs.open_input_file(n)
                data = f.read()
                f.close()
                return data

            results.append(("Adapter Tier 1 (native)", _bench(read_tier1, rounds)))

            def read_tier2(n: str = fname) -> bytes:
                f = adapter_fs_t2.open_input_file(n)
                data = f.read()
                f.close()
                return data

            results.append(("Adapter Tier 2 (forced)", _bench(read_tier2, rounds)))

            def read_store(n: str = fname) -> bytes:
                return store.read_bytes(n)

            results.append(("Store.read_bytes (raw)", _bench(read_store, rounds)))

            label = _human_size(size)
            for i, (method, s) in enumerate(results):
                _print_row(label if i == 0 else "", method, s)

            _print_speedup(
                ">> Tier1 vs Tier2:",
                results[0][1]["mean_us"],
                results[1][1]["mean_us"],
            )

        backend.close()
    finally:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=obj["Key"])
        with contextlib.suppress(Exception):
            client.delete_bucket(Bucket=bucket)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PyArrow adapter Tier 1 fast-path benchmark",
    )
    parser.add_argument(
        "--sizes",
        default=",".join(str(s) for s in _DEFAULT_SIZES),
        help="Comma-separated file sizes in bytes (default: 1KB,64KB,1MB,10MB)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=100,
        help="Iterations per benchmark (default: 100)",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        help="Run S3PyArrow benchmark (needs MinIO on :9000)",
    )
    args = parser.parse_args()

    sizes = [int(s.strip()) for s in args.sizes.split(",")]
    print("PyArrow Adapter Tier 1 Fast-Path Benchmark")
    print(f"Rounds: {args.rounds} | Sizes: {', '.join(_human_size(s) for s in sizes)}")
    print("=" * 110)

    print()
    print("=== Part 1: Local Backend (Tier 2 overhead baseline) ===")
    print()
    run_local_benchmark(sizes, args.rounds)

    if args.s3:
        if not _port_open("127.0.0.1", 9000):
            print()
            print("=== Part 2: SKIPPED (MinIO not reachable on :9000) ===")
            return
        print()
        print("=== Part 2: S3PyArrow via MinIO (Tier 1 vs Tier 2 A/B) ===")
        print()
        run_s3_pyarrow_benchmark(sizes, args.rounds)


if __name__ == "__main__":
    main()
