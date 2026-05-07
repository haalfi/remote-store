"""Streaming I/O + resource cleanup conformance.

SIO-001 only requires a readable BinaryIO at start-of-stream. Pre-loading
the full file into memory before returning (e.g. BytesIO) is acceptable for
backends that do not declare LAZY_READ. The LAZY_READ tests below enforce
the laziness contract only on backends that declare it.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from tests.backends.conformance._helpers import _require
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestStreamingConformance:
    """SIO-001, SIO-003, SIO-009: streaming semantics."""

    @pytest.mark.spec("SIO-001")
    def test_read_returns_readable_stream(self, backend: Backend) -> None:
        """read() must return a readable BinaryIO stream with correct content."""
        backend.write("stream_test.bin", b"hello streaming")
        stream = backend.read("stream_test.bin")
        assert stream.readable(), "read() must return a readable stream"
        assert stream.read() == b"hello streaming"
        stream.close()

    @pytest.mark.spec("SIO-009")
    def test_read_is_lazy(self, backend: Backend) -> None:
        """Backends declaring LAZY_READ must not return a BytesIO-backed stream."""
        _require(backend, Capability.LAZY_READ)
        backend.write("lazy_test.bin", b"lazy read test")
        stream = backend.read("lazy_test.bin")
        # Peel every layer of buffering until we reach a stream with no further
        # `.raw` attribute -- this guards against multi-level wrappers such as
        # BufferedReader(CustomWrapper(BytesIO(...))).
        inner = stream
        while hasattr(inner, "raw"):
            inner = inner.raw  # type: ignore[union-attr]
        assert not isinstance(inner, io.BytesIO), (
            "Backend declares LAZY_READ but read() returned a BytesIO-backed stream"
        )
        assert stream.read() == b"lazy read test"
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_supports_chunked_reads(self, backend: Backend) -> None:
        """Streams must support reading in fixed-size chunks."""
        content = b"A" * 1000
        backend.write("chunks.bin", content)
        stream = backend.read("chunks.bin")
        chunks = []
        while True:
            chunk = stream.read(100)
            if not chunk:
                break
            assert len(chunk) <= 100
            chunks.append(chunk)
        assert b"".join(chunks) == content
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_eof_returns_empty_bytes_not_none(self, backend: Backend) -> None:
        """read() at EOF must return b'' (empty bytes), not None."""
        backend.write("eof_test.bin", b"x")
        stream = backend.read("eof_test.bin")
        data = stream.read()
        assert data == b"x"
        eof = stream.read()
        assert eof == b"", f"Expected b'' at EOF, got {eof!r}"
        eof2 = stream.read(10)
        assert eof2 == b"", f"Expected b'' at EOF with size hint, got {eof2!r}"
        stream.close()

    @pytest.mark.spec("SIO-009")
    def test_read_is_lazy_readinto(self, backend: Backend) -> None:
        """LAZY_READ streams must support readinto() via the RawIOBase protocol."""
        _require(backend, Capability.LAZY_READ)
        content = b"readinto test data"
        backend.write("readinto_test.bin", content)
        stream = backend.read("readinto_test.bin")
        # Reach the raw layer for readinto() -- BufferedReader handles readinto
        # at the buffered level, but we want to exercise the raw stream.
        raw = stream
        while hasattr(raw, "raw"):
            raw = raw.raw  # type: ignore[union-attr]
        buf = bytearray(len(content))
        n = raw.readinto(buf)
        assert isinstance(n, int), f"readinto() must return int, got {type(n).__name__}"
        assert n > 0, "readinto() must return > 0 bytes on a non-empty stream"
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_stream_position_starts_at_zero(self, backend: Backend) -> None:
        """Stream must be positioned at the start on return."""
        backend.write("pos.bin", b"0123456789")
        stream = backend.read("pos.bin")
        assert stream.read(3) == b"012"
        assert stream.read() == b"3456789"
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_stream_supports_context_manager(self, backend: Backend) -> None:
        """read() stream supports context manager protocol for reliable cleanup."""
        backend.write("ctx.bin", b"context manager test")
        with backend.read("ctx.bin") as stream:
            content = stream.read()
        assert content == b"context manager test"
        assert stream.closed

    @pytest.mark.spec("SIO-003")
    def test_write_from_binaryio_streams_content(self, backend: Backend) -> None:
        """write() with BinaryIO must not require the caller to materialize bytes."""
        content = b"X" * 8192
        backend.write("binio_write.bin", io.BytesIO(content))
        assert backend.read_bytes("binio_write.bin") == content

    @pytest.mark.spec("SIO-003")
    def test_write_binaryio_reads_from_current_position(self, backend: Backend) -> None:
        """write() must read BinaryIO from its current position, not from start."""
        buf = io.BytesIO(b"HEADER_PAYLOAD")
        buf.seek(7)  # Skip past "HEADER_"
        backend.write("partial_pos.bin", buf)
        assert backend.read_bytes("partial_pos.bin") == b"PAYLOAD"


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestResourceCleanup:
    """Streams from read() must support close/context-manager."""

    @pytest.mark.spec("SIO-001")
    def test_read_stream_close(self, backend: Backend) -> None:
        """Stream must be closeable."""
        backend.write("ec_rc.txt", b"data")
        stream = backend.read("ec_rc.txt")
        stream.read()
        stream.close()
        assert stream.closed

    @pytest.mark.spec("SIO-001")
    def test_read_stream_context_manager(self, backend: Backend) -> None:
        """Context manager must close the stream on exit."""
        backend.write("ec_rcm.txt", b"data")
        with backend.read("ec_rcm.txt") as stream:
            stream.read()
        assert stream.closed

    @pytest.mark.spec("SIO-001")
    def test_read_stream_double_close(self, backend: Backend) -> None:
        """Double close must not raise, stream stays closed."""
        backend.write("ec_rdc.txt", b"data")
        stream = backend.read("ec_rdc.txt")
        stream.close()
        stream.close()  # must not raise
        assert stream.closed
