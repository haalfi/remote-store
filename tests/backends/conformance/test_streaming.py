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
from tests._helpers import KNOWN_STREAM_WRAPPERS, PEEL_STOPPED_ON_WRAPPER, peel_to_body
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
        inner = peel_to_body(stream)
        # The contract first: a bare BytesIO peels to itself, and this is the
        # assertion that must name the backend for it. The wrapper guard below
        # is about the *test* losing its way, so it must not pre-empt this one.
        assert not isinstance(inner, io.BytesIO), (
            f"Backend declares LAZY_READ but read() returned a BytesIO-backed stream (peeled to {type(inner).__name__})"
        )
        assert not isinstance(inner, KNOWN_STREAM_WRAPPERS), PEEL_STOPPED_ON_WRAPPER
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
        # Reach the body for readinto(); BufferedReader handles readinto at the
        # buffered level, but we want to exercise the stream underneath it.
        raw = peel_to_body(stream)
        assert not isinstance(raw, KNOWN_STREAM_WRAPPERS), PEEL_STOPPED_ON_WRAPPER
        buf = bytearray(len(content))
        n = raw.readinto(buf)  # type: ignore[attr-defined]
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

    @pytest.mark.spec("SIO-008")
    def test_read_returns_seekable_stream_when_declared(self, backend: Backend) -> None:
        """SEEKABLE_READ-declaring backends must return a seekable stream.

        ID-188 / SIO-008: the Dafny ``Backend.Read`` postcondition obliges
        every backend declaring ``CapSeekableRead`` to return a stream whose
        ``seekable()`` is ``True``. The DafnyOracleBackend certifies this
        test by construction (it wraps content in ``io.BytesIO``); real
        backends that declare the capability must produce the same shape.

        The flag is necessary but not sufficient for the spec contract
        ("callers that need to seek can rely on it"), so the test also
        exercises an actual ``seek`` round-trip — a backend whose
        ``seekable()`` returns ``True`` but whose ``seek()`` raises or
        no-ops would slip past a flag-only assertion. The mid-stream seek
        reads the remainder with bare ``stream.read()`` rather than a
        sized ``read(n)``: backends whose stream is a bare ``RawIOBase``
        (no ``BufferedReader`` layer — e.g. ``_ErrorMappingStream`` wrapping
        s3fs) are permitted to short-read on a sized call.

        Scope note: the assertion is forward-direction only. The Dafny
        postcondition is capability-gated, so a backend silently returning
        a seekable stream *without* declaring ``CapSeekableRead`` is not
        in scope here (SIO-008 imposes no such obligation).
        """
        _require(backend, Capability.SEEKABLE_READ)
        payload = b"seekable data"
        backend.write("seek_decl.bin", payload)
        stream = backend.read("seek_decl.bin")
        try:
            assert stream.seekable() is True
            assert stream.read() == payload
            stream.seek(0)
            assert stream.read() == payload
            stream.seek(4)
            assert stream.read() == payload[4:]
        finally:
            stream.close()

    @pytest.mark.spec("SIO-008")
    @pytest.mark.spec("SIO-011")
    def test_seek_to_end_reports_the_true_size(self, backend: Backend) -> None:
        """An end-relative seek answers the real size on every seekable backend.

        SIO-011 splits the backends in two: one hands the shared stream wrapper
        a ``size_probe`` and the wrapper resolves ``SEEK_END`` itself, and the
        rest delegate the end-relative seek to their own stream exactly as they
        always did. Which is which is the spec's business, not this layer's —
        what makes the case belong *here* is that it is the one assertion
        holding both halves to the same answer, so a probe that drifts from the
        delegating path fails in conformance rather than in whichever backend
        introduced it.

        Until this was added, no conformance test seeked to the end at all:
        every ``.seek()`` in this directory passed an offset and no whence.
        ``SEEK_END`` appeared under ``tests/`` in three files, none of them
        here — the shared wrapper's own unit stubs, one backend's stalled-channel
        suite, and one backend's range-reader suite. So the wrapper's
        ``SEEK_END`` branch had been exercised against a single in-process stub
        server whose ``stat()`` is a local ``os.fstat``, and the Stage-2 lane —
        the one that exists to catch real-server differences — never reached the
        path SIO-011 changed.

        It does now, but only where Stage 2 runs: ``--stage=2`` collection lists
        the containerised fixtures here while a default local run does not, so
        CI is what actually executes them.

        The negative offset is the shape that matters: an analytical reader
        sizing a file seeks backwards from the end (a Parquet footer read is
        exactly ``seek(-n, SEEK_END)``), and it is the case where an
        off-by-one in the wrapper's own arithmetic would show. ``seek(0,
        SEEK_END)`` alone would pass against an implementation that ignored the
        caller's offset entirely.

        Read with a bare ``stream.read()`` rather than a sized call, for the
        reason the sibling test above gives: an unbuffered ``RawIOBase`` stream
        is permitted to short-read on ``read(n)``.
        """
        _require(backend, Capability.SEEKABLE_READ)
        payload = b"0123456789abcdef"
        backend.write("seek_end.bin", payload)
        stream = backend.read("seek_end.bin")
        try:
            assert stream.seek(0, io.SEEK_END) == len(payload), (
                "seek-to-end must report the file's real size, not a swallowed 0"
            )
            assert stream.read() == b"", "nothing follows the true end"

            assert stream.seek(-6, io.SEEK_END) == len(payload) - 6
            assert stream.read() == payload[-6:], "a footer read must land on the last 6 bytes"

            # The probe must not disturb the handle's own position bookkeeping:
            # an absolute seek after an end-relative one still answers from 0.
            assert stream.seek(0) == 0
            assert stream.read() == payload
        finally:
            stream.close()


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
