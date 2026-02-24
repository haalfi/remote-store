"""Large-file benchmarks with memory tracking — remote-store only."""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


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

    @pytest.fixture()
    def large_payload(self) -> bytes:
        from benchmarks.conftest import BENCH_LARGE_FILE_MB

        return b"L" * (BENCH_LARGE_FILE_MB * 1_048_576)

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
