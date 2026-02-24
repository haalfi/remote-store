"""Performance benchmarks for remote-store backends.

Run with:
    docker compose up -d          # start MinIO, Azurite, SFTP
    hatch run bench               # all backends, pretty table
    hatch run bench-save          # save results for later comparison
    hatch run bench-compare       # compare against last saved run

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
# Write benchmarks
# ---------------------------------------------------------------------------


class TestWritePerformance:
    """Measure write throughput for bytes payloads of various sizes."""

    def test_write_bytes(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _write() -> None:
            bench_backend.write(_unique(), payload)

        benchmark(_write)

    def test_write_stream(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _write() -> None:
            bench_backend.write(_unique(), io.BytesIO(payload))

        benchmark(_write)


# ---------------------------------------------------------------------------
# Read benchmarks
# ---------------------------------------------------------------------------


class TestReadPerformance:
    """Measure read latency and throughput."""

    def test_read_bytes(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        path = _unique("read")
        bench_backend.write(path, payload)

        def _read() -> None:
            bench_backend.read_bytes(path)

        benchmark(_read)

    def test_read_stream(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        path = _unique("readstream")
        bench_backend.write(path, payload)

        def _read() -> None:
            stream = bench_backend.read(path)
            while stream.read(65_536):
                pass
            stream.close()

        benchmark(_read)


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
# List benchmarks
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
# Delete benchmarks
# ---------------------------------------------------------------------------


class TestDeletePerformance:
    """Measure delete latency."""

    def test_delete(self, bench_backend: Backend, benchmark: Any) -> None:
        # Pre-create a pool of files to delete one per iteration
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
# Write + read round-trip benchmark
# ---------------------------------------------------------------------------


class TestRoundtripPerformance:
    """Measure full write-then-read round-trip."""

    def test_roundtrip(self, bench_backend: Backend, payload: bytes, benchmark: Any) -> None:
        def _roundtrip() -> None:
            path = _unique("rt")
            bench_backend.write(path, payload)
            bench_backend.read_bytes(path)

        benchmark(_roundtrip)
