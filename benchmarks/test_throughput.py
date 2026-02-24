"""Throughput benchmarks — write, read, and stream performance."""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


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
