"""Performance benchmarks for remote-store backends.

Run with:
    docker compose up -d          # start MinIO, Azurite, SFTP
    hatch run bench               # all backends, sorted by mean
    hatch run bench-save          # save results for later comparison
    hatch run bench-compare       # compare against last saved run

Key metrics reported per test:
    Mean / Median / StdDev  — pytest-benchmark default columns
    Ops/Sec                 — operations per second (1 / Mean)
    Throughput (MB/s)       — printed in summary table & saved in JSON extra_info
    Peak Memory (MB)        — for large-file tests (via tracemalloc)

Throughput = payload_bytes / mean_seconds / 1 048 576.
The conftest ``pytest_terminal_summary`` hook prints a throughput table after
the benchmark table.  JSON output (``--benchmark-autosave``) also includes
``throughput_MBps`` via the ``pytest_benchmark_update_json`` hook.

Environment variables (override docker-compose defaults):
    BENCH_MINIO_HOST, BENCH_MINIO_PORT, BENCH_MINIO_ACCESS_KEY, BENCH_MINIO_SECRET_KEY
    BENCH_AZURITE_HOST, BENCH_AZURITE_PORT
    BENCH_SFTP_HOST, BENCH_SFTP_PORT, BENCH_SFTP_USER, BENCH_SFTP_PASS
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


# ---------------------------------------------------------------------------
# TTFB — Time to First Byte (isolates protocol/auth overhead)
# ---------------------------------------------------------------------------


class TestTTFB:
    """Measure Time-to-First-Byte using a tiny (1 KB) file.

    High TTFB usually indicates slow authentication handshakes or protocol
    overhead — common in SFTP.  These tests deliberately use a 1 KB payload
    so the transfer time is negligible and what you measure is pure overhead.
    """

    _TTFB_PAYLOAD = b"T" * 1_024

    def test_ttfb_write(self, bench_backend: Backend, benchmark: Any) -> None:
        """First-byte latency for a write operation."""

        def _write() -> None:
            bench_backend.write(_unique("ttfb_w"), self._TTFB_PAYLOAD)

        benchmark.pedantic(_write, rounds=20, warmup_rounds=2)

    def test_ttfb_read(self, bench_backend: Backend, benchmark: Any) -> None:
        """First-byte latency for a read operation."""
        path = _unique("ttfb_r")
        bench_backend.write(path, self._TTFB_PAYLOAD)

        def _read() -> None:
            stream = bench_backend.read(path)
            stream.read(1)  # first byte only
            stream.close()

        benchmark.pedantic(_read, rounds=20, warmup_rounds=2)

    def test_ttfb_exists(self, bench_backend: Backend, benchmark: Any) -> None:
        """First-byte latency for an exists check (cheapest metadata call)."""
        path = _unique("ttfb_e")
        bench_backend.write(path, b"x")

        benchmark.pedantic(bench_backend.exists, args=(path,), rounds=20, warmup_rounds=2)


# ---------------------------------------------------------------------------
# Write benchmarks — with throughput
# ---------------------------------------------------------------------------


class TestWritePerformance:
    """Measure write throughput for bytes payloads of various sizes."""

    def test_write_bytes(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _write() -> None:
            bench_backend.write(_unique(), payload)

        benchmark(_write)
        benchmark.extra_info["payload_bytes"] = len(payload)

    def test_write_stream(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _write() -> None:
            bench_backend.write(_unique(), io.BytesIO(payload))

        benchmark(_write)
        benchmark.extra_info["payload_bytes"] = len(payload)


# ---------------------------------------------------------------------------
# Read benchmarks — with throughput
# ---------------------------------------------------------------------------


class TestReadPerformance:
    """Measure read latency and throughput."""

    def test_read_bytes(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        path = _unique("read")
        bench_backend.write(path, payload)

        def _read() -> None:
            bench_backend.read_bytes(path)

        benchmark(_read)
        benchmark.extra_info["payload_bytes"] = len(payload)

    def test_read_stream(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        path = _unique("readstream")
        bench_backend.write(path, payload)

        def _read() -> None:
            stream = bench_backend.read(path)
            while stream.read(65_536):
                pass
            stream.close()

        benchmark(_read)
        benchmark.extra_info["payload_bytes"] = len(payload)


# ---------------------------------------------------------------------------
# Metadata / exists benchmarks
# ---------------------------------------------------------------------------


class TestMetadataPerformance:
    """Measure metadata-query latency."""

    def test_exists_hit(self, bench_backend: Backend, benchmark: Any) -> None:
        path = _unique("exists")
        bench_backend.write(path, b"x")
        benchmark(bench_backend.exists, path)

    def test_exists_miss(self, bench_backend: Backend, benchmark: Any) -> None:
        benchmark(bench_backend.exists, "nonexistent/file.bin")

    def test_get_file_info(self, bench_backend: Backend, benchmark: Any) -> None:
        path = _unique("info")
        bench_backend.write(path, b"0" * 4096)
        benchmark(bench_backend.get_file_info, path)


# ---------------------------------------------------------------------------
# List benchmarks (small scale — 50 files)
# ---------------------------------------------------------------------------


class TestListPerformance:
    """Measure listing speed with a populated directory."""

    @pytest.fixture(autouse=True)
    def _populate(self, bench_backend: Backend) -> None:
        self._dir = f"listbench/{uuid.uuid4().hex[:8]}"
        for i in range(50):
            bench_backend.write(f"{self._dir}/file_{i:04d}.txt", b"x")

    def test_list_files(self, bench_backend: Backend, benchmark: Any) -> None:
        def _list() -> None:
            list(bench_backend.list_files(self._dir))

        benchmark(_list)

    def test_list_files_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        def _list() -> None:
            list(bench_backend.list_files(self._dir, recursive=True))

        benchmark(_list)


# ---------------------------------------------------------------------------
# Directory-scale operations (hundreds of files in folder hierarchies)
# ---------------------------------------------------------------------------


class TestDirectoryScalePerformance:
    """Measure directory operations at scale: listing, renaming, deletion
    across a multi-level folder hierarchy with hundreds of files.

    The hierarchy has 3 levels of nesting with 200 files total::

        scale/{tag}/lvl0_NN.txt            (20 files)
        scale/{tag}/sub_N/lvl1_NN.txt      (5 dirs x 20 files = 100 files)
        scale/{tag}/sub_N/deep/lvl2_NN.txt (5 dirs x 1 deep x 16 files = 80 files)

    Total: 200 files across 11 folders.
    """

    @pytest.fixture(autouse=True)
    def _populate_hierarchy(self, bench_backend: Backend) -> None:
        self._root = f"scale/{uuid.uuid4().hex[:8]}"
        # Level 0: 20 files in root
        for i in range(20):
            bench_backend.write(f"{self._root}/lvl0_{i:02d}.txt", b"x")
        # Level 1: 5 subdirectories x 20 files each
        for d in range(5):
            for i in range(20):
                bench_backend.write(f"{self._root}/sub_{d}/lvl1_{i:02d}.txt", b"x")
            # Level 2: 1 nested dir x 16 files
            for i in range(16):
                bench_backend.write(f"{self._root}/sub_{d}/deep/lvl2_{i:02d}.txt", b"x")

    def test_list_200_files_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        """List all 200 files recursively from root."""

        def _list() -> None:
            files = list(bench_backend.list_files(self._root, recursive=True))
            assert len(files) == 200

        benchmark(_list)

    def test_list_200_files_non_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        """List only top-level files (20 of 200)."""

        def _list() -> None:
            files = list(bench_backend.list_files(self._root))
            assert len(files) == 20

        benchmark(_list)

    def test_list_folders_at_root(self, bench_backend: Backend, benchmark: Any) -> None:
        """List the 5 immediate subdirectories."""

        def _list() -> None:
            folders = list(bench_backend.list_folders(self._root))
            assert len(folders) == 5

        benchmark(_list)

    def test_copy_across_subtrees(self, bench_backend: Backend, benchmark: Any) -> None:
        """Copy a file from one subtree to another."""
        src = f"{self._root}/sub_0/lvl1_00.txt"

        def _copy() -> None:
            bench_backend.copy(src, f"{self._root}/sub_4/{_unique('cp')}", overwrite=True)

        benchmark(_copy)

    def test_move_across_subtrees(self, bench_backend: Backend, benchmark: Any) -> None:
        """Move files from one subtree to another (pre-created pool)."""
        paths: list[str] = []
        for i in range(100):
            p = f"{self._root}/mvpool/f_{i:04d}.txt"
            bench_backend.write(p, b"m")
            paths.append(p)
        idx = iter(range(len(paths)))

        def _move() -> None:
            i = next(idx, None)
            if i is not None:
                bench_backend.move(paths[i], f"{self._root}/sub_3/{_unique('mv')}")

        benchmark(_move)

    def test_delete_folder_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        """Delete an entire subtree (36 files) recursively."""
        subtrees: list[str] = []
        for t in range(30):
            base = f"{self._root}/delfolder_{t}"
            for i in range(20):
                bench_backend.write(f"{base}/f_{i:02d}.txt", b"d")
            for i in range(16):
                bench_backend.write(f"{base}/nested/f_{i:02d}.txt", b"d")
            subtrees.append(base)
        idx = iter(range(len(subtrees)))

        def _delete() -> None:
            i = next(idx, None)
            if i is not None:
                bench_backend.delete_folder(subtrees[i], recursive=True)

        benchmark(_delete)

    def test_exists_deep_path(self, bench_backend: Backend, benchmark: Any) -> None:
        """Check existence of a file at the deepest nesting level."""
        path = f"{self._root}/sub_2/deep/lvl2_07.txt"
        benchmark(bench_backend.exists, path)

    def test_get_folder_info_large_dir(self, bench_backend: Backend, benchmark: Any) -> None:
        """get_folder_info on the root (aggregates all 200 files)."""
        benchmark(bench_backend.get_folder_info, self._root)


# ---------------------------------------------------------------------------
# Delete benchmarks
# ---------------------------------------------------------------------------


class TestDeletePerformance:
    """Measure delete latency."""

    def test_delete(self, bench_backend: Backend, benchmark: Any) -> None:
        paths: list[str] = []
        for _ in range(200):
            p = _unique("del")
            bench_backend.write(p, b"y")
            paths.append(p)
        idx = iter(range(len(paths)))

        def _delete() -> None:
            i = next(idx, None)
            if i is not None:
                bench_backend.delete(paths[i])

        benchmark(_delete)


# ---------------------------------------------------------------------------
# Copy / Move benchmarks
# ---------------------------------------------------------------------------


class TestCopyMovePerformance:
    """Measure copy and move latency with a small file."""

    def test_copy(self, bench_backend: Backend, benchmark: Any) -> None:
        src = _unique("cpsrc")
        bench_backend.write(src, b"Z" * 4096)

        def _copy() -> None:
            bench_backend.copy(src, _unique("cpdst"), overwrite=True)

        benchmark(_copy)

    def test_move(self, bench_backend: Backend, benchmark: Any) -> None:
        paths: list[str] = []
        for _ in range(200):
            p = _unique("mvsrc")
            bench_backend.write(p, b"Z" * 4096)
            paths.append(p)
        idx = iter(range(len(paths)))

        def _move() -> None:
            i = next(idx, None)
            if i is not None:
                bench_backend.move(paths[i], _unique("mvdst"))

        benchmark(_move)


# ---------------------------------------------------------------------------
# Write + read round-trip — with throughput
# ---------------------------------------------------------------------------


class TestRoundtripPerformance:
    """Measure full write-then-read round-trip."""

    def test_roundtrip(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _roundtrip() -> None:
            path = _unique("rt")
            bench_backend.write(path, payload)
            bench_backend.read_bytes(path)

        benchmark(_roundtrip)
        # Round-trip moves 2x the payload (write + read)
        benchmark.extra_info["payload_bytes"] = len(payload) * 2


# ---------------------------------------------------------------------------
# Memory-aware large-file benchmarks
# ---------------------------------------------------------------------------


class TestLargeFilePerformance:
    """Throughput and memory behaviour with 10 MB files.

    These tests use ``benchmark.pedantic()`` with fewer rounds so the
    suite completes in reasonable time even against network backends.

    Memory is tracked via ``tracemalloc`` and reported in ``extra_info``:
      - ``peak_memory_MB``: peak RSS delta during the benchmarked operation.

    For files larger than 500 MB you should monitor process RSS externally
    (e.g. ``/usr/bin/time -v``) since ``tracemalloc`` only tracks Python
    allocations and misses mmap / native-library buffers.
    """

    _LARGE_SIZE = 10 * 1_048_576  # 10 MB

    @pytest.fixture()
    def large_payload(self) -> bytes:
        return b"L" * self._LARGE_SIZE

    def test_write_large(self, bench_backend: Backend, large_payload: bytes, benchmark: Any) -> None:
        import tracemalloc

        peak: float = 0

        def _write() -> None:
            nonlocal peak
            tracemalloc.start()
            bench_backend.write(_unique("lg_w"), large_payload)
            _, p = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak = max(peak, p)

        benchmark.pedantic(_write, rounds=5, warmup_rounds=1)
        benchmark.extra_info["payload_bytes"] = len(large_payload)
        benchmark.extra_info["peak_memory_MB"] = round(peak / 1_048_576, 2)

    def test_read_large(self, bench_backend: Backend, large_payload: bytes, benchmark: Any) -> None:
        import tracemalloc

        path = _unique("lg_r")
        bench_backend.write(path, large_payload)
        peak: float = 0

        def _read() -> None:
            nonlocal peak
            tracemalloc.start()
            bench_backend.read_bytes(path)
            _, p = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak = max(peak, p)

        benchmark.pedantic(_read, rounds=5, warmup_rounds=1)
        benchmark.extra_info["payload_bytes"] = len(large_payload)
        benchmark.extra_info["peak_memory_MB"] = round(peak / 1_048_576, 2)

    def test_stream_read_large(self, bench_backend: Backend, large_payload: bytes, benchmark: Any) -> None:
        """Streaming read — memory should stay low regardless of file size."""
        import tracemalloc

        path = _unique("lg_sr")
        bench_backend.write(path, large_payload)
        peak: float = 0

        def _stream() -> None:
            nonlocal peak
            tracemalloc.start()
            stream = bench_backend.read(path)
            while stream.read(65_536):
                pass
            stream.close()
            _, p = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak = max(peak, p)

        benchmark.pedantic(_stream, rounds=5, warmup_rounds=1)
        benchmark.extra_info["payload_bytes"] = len(large_payload)
        benchmark.extra_info["peak_memory_MB"] = round(peak / 1_048_576, 2)

    def test_stream_write_large(self, bench_backend: Backend, large_payload: bytes, benchmark: Any) -> None:
        """Streaming write — memory should stay low regardless of file size."""
        import tracemalloc

        peak: float = 0

        def _write() -> None:
            nonlocal peak
            tracemalloc.start()
            bench_backend.write(_unique("lg_sw"), io.BytesIO(large_payload))
            _, p = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak = max(peak, p)

        benchmark.pedantic(_write, rounds=5, warmup_rounds=1)
        benchmark.extra_info["payload_bytes"] = len(large_payload)
        benchmark.extra_info["peak_memory_MB"] = round(peak / 1_048_576, 2)

    def test_roundtrip_large(self, bench_backend: Backend, large_payload: bytes, benchmark: Any) -> None:
        import tracemalloc

        peak: float = 0

        def _rt() -> None:
            nonlocal peak
            tracemalloc.start()
            path = _unique("lg_rt")
            bench_backend.write(path, large_payload)
            bench_backend.read_bytes(path)
            _, p = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak = max(peak, p)

        benchmark.pedantic(_rt, rounds=5, warmup_rounds=1)
        benchmark.extra_info["payload_bytes"] = len(large_payload) * 2
        benchmark.extra_info["peak_memory_MB"] = round(peak / 1_048_576, 2)
