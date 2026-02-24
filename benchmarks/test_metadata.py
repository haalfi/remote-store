"""Metadata benchmarks.

Comparative: exists (hit + miss) via ``bench_target``.
Remote-store only: get_file_info via ``bench_backend``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from benchmarks.targets._protocol import BenchTarget
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


# ---------------------------------------------------------------------------
# Comparative: exists
# ---------------------------------------------------------------------------


class TestExistsPerformance:
    """Comparative exists check (bench_target)."""

    def test_exists_hit(self, bench_target: BenchTarget, benchmark: Any) -> None:
        path = _unique("exists")
        bench_target.write(path, b"x")
        benchmark(bench_target.exists, path)

    def test_exists_miss(self, bench_target: BenchTarget, benchmark: Any) -> None:
        benchmark(bench_target.exists, "nonexistent/file.bin")


# ---------------------------------------------------------------------------
# Remote-store only: get_file_info
# ---------------------------------------------------------------------------


class TestMetadataPerformance:
    """Remote-store only metadata queries."""

    def test_get_file_info(self, bench_backend: Backend, benchmark: Any) -> None:
        path = _unique("info")
        bench_backend.write(path, b"0" * 4096)
        benchmark(bench_backend.get_file_info, path)
