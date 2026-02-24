"""TTFB (Time to First Byte) benchmarks — remote-store only."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


class TestTTFB:
    """Measure Time-to-First-Byte using a tiny (1 KB) file.

    High TTFB usually indicates slow authentication handshakes or protocol
    overhead — common in SFTP.  These tests deliberately use a 1 KB payload
    so the transfer time is negligible and what you measure is pure overhead.
    """

    _TTFB_PAYLOAD = b"T" * 1_024

    def test_write_latency(self, bench_backend: Backend, benchmark: Any) -> None:
        """Measure full write latency for a tiny (1 KB) file."""

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
