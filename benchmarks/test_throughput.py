"""Throughput benchmarks — write, read, and stream performance.

Comparative tests use ``bench_target`` (remote-store vs raw SDK vs fsspec).
Stream and roundtrip tests stay ``bench_backend``-only since raw SDKs don't
have a uniform BinaryIO interface.
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from benchmarks.targets._protocol import BenchTarget
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


# ---------------------------------------------------------------------------
# Comparative: write bytes
# ---------------------------------------------------------------------------


class TestWriteThroughput:
    """Comparative write throughput (bench_target)."""

    def test_write_bytes(self, bench_target: BenchTarget, payload: bytes, benchmark: Any) -> None:
        def _write() -> None:
            bench_target.write(_unique(), payload)

        benchmark(_write)
        benchmark.extra_info["payload_bytes"] = len(payload)


# ---------------------------------------------------------------------------
# Comparative: read bytes
# ---------------------------------------------------------------------------


class TestReadThroughput:
    """Comparative read throughput (bench_target)."""

    def test_read_bytes(self, bench_target: BenchTarget, payload: bytes, benchmark: Any) -> None:
        path = _unique("read")
        bench_target.write(path, payload)

        def _read() -> None:
            bench_target.read(path)

        benchmark(_read)
        benchmark.extra_info["payload_bytes"] = len(payload)


# ---------------------------------------------------------------------------
# Remote-store only: stream write/read
# ---------------------------------------------------------------------------


class TestStreamPerformance:
    """Stream write/read — remote-store only (no uniform BinaryIO in raw SDKs)."""

    def test_write_stream(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _write() -> None:
            bench_backend.write(_unique(), io.BytesIO(payload))

        benchmark(_write)
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
# Remote-store only: roundtrip
# ---------------------------------------------------------------------------


class TestRoundtripPerformance:
    """Measure full write-then-read round-trip — remote-store only."""

    def test_roundtrip(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _roundtrip() -> None:
            path = _unique("rt")
            bench_backend.write(path, payload)
            bench_backend.read_bytes(path)

        benchmark(_roundtrip)
        # Round-trip moves 2x the payload (write + read)
        benchmark.extra_info["payload_bytes"] = len(payload) * 2
