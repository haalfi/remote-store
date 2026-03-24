"""Seekable read benchmarks — measure read_seekable() cost across backends.

Backends have different seekable strategies:
- Local, S3, SFTP: passthrough (already seekable)
- Azure: _AzureRangeReader (HTTP Range per read)
- HTTP: spool to SpooledTemporaryFile

This benchmark measures open cost, sequential read, and random seek patterns
to quantify the real cost of seekable access.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


# ---------------------------------------------------------------------------
# Seekable read: open + full read
# ---------------------------------------------------------------------------


class TestSeekableReadPerformance:
    """Seekable read latency — remote-store only (bench_backend)."""

    def test_seekable_open_read(self, bench_backend: Backend, benchmark: Any) -> None:
        """Open a seekable stream and read the entire file."""
        path = _unique("seek")
        data = b"S" * 1_048_576  # 1MB
        bench_backend.write(path, data)

        def _open_read() -> None:
            with bench_backend.read_seekable(path) as f:
                f.read()

        benchmark(_open_read)
        benchmark.extra_info["payload_bytes"] = len(data)

    def test_seekable_sequential_chunks(self, bench_backend: Backend, benchmark: Any) -> None:
        """Read a 1MB file in 64KB sequential chunks via seekable stream."""
        path = _unique("seqchunk")
        size = 1_048_576
        chunk = 65_536
        bench_backend.write(path, b"C" * size)

        def _sequential() -> None:
            with bench_backend.read_seekable(path) as f:
                while f.read(chunk):
                    pass

        benchmark(_sequential)
        benchmark.extra_info["payload_bytes"] = size

    def test_seekable_random_seeks(self, bench_backend: Backend, benchmark: Any) -> None:
        """Seek to 10 random positions in a 1MB file and read 4KB each."""
        path = _unique("randseek")
        size = 1_048_576
        bench_backend.write(path, b"R" * size)
        # Fixed positions for reproducibility.
        positions = [102400, 819200, 51200, 921600, 409600, 204800, 716800, 307200, 614400, 0]

        def _random_seeks() -> None:
            with bench_backend.read_seekable(path) as f:
                for pos in positions:
                    f.seek(pos)
                    f.read(4096)

        benchmark(_random_seeks)
        benchmark.extra_info["seek_count"] = len(positions)
