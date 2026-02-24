"""Metadata and exists benchmarks — remote-store only."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


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
