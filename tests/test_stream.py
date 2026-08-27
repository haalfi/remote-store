"""Tests for _ErrorMappingStream and _safe_wrap."""

from __future__ import annotations

import io
from typing import cast

import pytest

from remote_store._errors import NotFound, RemoteStoreError
from remote_store._stream import _ErrorMappingStream, _safe_wrap


def _test_mapper(exc: Exception, path: str) -> RemoteStoreError:
    """Simple mapper that converts any exception to NotFound."""
    return NotFound(f"mapped: {exc}", path=path, backend="test")


# ---------------------------------------------------------------------------
# Helper streams
# ---------------------------------------------------------------------------


class _ParamikoLikeStream(io.RawIOBase):
    """A stream that returns None from seek() like paramiko SFTPFile."""

    def __init__(self, data: bytes) -> None:
        super().__init__()
        self._buf = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        return self._buf.readinto(b)  # type: ignore[arg-type]

    def seek(self, offset: int, whence: int = 0) -> int:
        self._buf.seek(offset, whence)
        return None  # type: ignore[return-value]  # paramiko behavior

    def tell(self) -> int:
        return self._buf.tell()


class _FailingStream(io.RawIOBase):
    """A stream that raises an OSError on every operation."""

    def __init__(self, exc_type: type = OSError) -> None:
        super().__init__()
        self._exc_type = exc_type

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        raise self._exc_type("disk failure" if self._exc_type is OSError else "bad argument")

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise self._exc_type("disk failure" if self._exc_type is OSError else "bad argument")

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise OSError("disk failure")

    def seek(self, offset: int, whence: int = 0) -> int:
        raise OSError("disk failure")

    def tell(self) -> int:
        raise OSError("disk failure")


class _EOFStream(io.RawIOBase):
    """Raises ``EOFError`` on every read op — how paramiko signals a channel death mid-read.

    paramiko's ``_read_all`` / ``_read_response`` raise ``EOFError`` (which is
    *not* an ``OSError``) when the channel dies during a streamed read.
    """

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        raise EOFError("server closed connection")

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise EOFError("server closed connection")

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise EOFError("server closed connection")

    def seek(self, offset: int, whence: int = 0) -> int:
        raise EOFError("server closed connection")

    def tell(self) -> int:
        raise EOFError("server closed connection")


class _FailingCloseStream(io.RawIOBase):
    """A stream that raises on close."""

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        return 0

    def close(self) -> None:
        if not self.closed:
            super().close()
            raise OSError("close failed")


class _ChannelDeath(OSError):
    """The failure shape ``_fatal`` below treats as condemning the connection.

    A distinct type rather than a message match, so a test that means "not
    fatal" can raise a plain ``OSError`` and be sure the predicate says so.
    """


def _fatal(exc: Exception) -> bool:
    """Stand-in for ``SFTPBackend._is_connection_dead`` — shape, not message."""
    return isinstance(exc, _ChannelDeath)


class _CloseTrackingStream(io.RawIOBase):
    """Reads fail with *exc* (or return *data* when it is ``None``); closes are counted.

    Counted rather than flagged: the skip has to hold when close is reached
    twice — a ``with`` block plus an explicit ``close()``, or a
    ``BufferedReader`` layer closing its raw — and a boolean cannot tell a
    second inner close from the first.
    """

    def __init__(self, exc: Exception | None = None, data: bytes = b"payload") -> None:
        super().__init__()
        self._exc = exc
        self._buf = io.BytesIO(data)
        self.close_calls = 0

    def readable(self) -> bool:
        return True

    def _check(self) -> None:
        if self._exc is not None:
            raise self._exc

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        self._check()
        return self._buf.readinto(b)  # type: ignore[arg-type]

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        self._check()
        return self._buf.read(size)

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        self._check()
        return self._buf.readline(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        self._check()
        return self._buf.seek(offset, whence)

    def tell(self) -> int:
        self._check()
        return self._buf.tell()

    def close(self) -> None:
        self.close_calls += 1
        super().close()


# ---------------------------------------------------------------------------
# Passthrough tests
# ---------------------------------------------------------------------------


class TestErrorMappingStreamPassthrough:
    """Stream operations pass through to the inner stream when no error occurs."""

    @pytest.mark.parametrize(
        ("data", "action", "expected"),
        [
            pytest.param(b"hello world", lambda s: s.read(), b"hello world", id="read-all"),
            pytest.param(b"hello world", lambda s: s.read(5), b"hello", id="read-sized"),
            pytest.param(b"line1\nline2\n", lambda s: s.readline(), b"line1\n", id="readline"),
        ],
    )
    def test_read_operations(self, data: bytes, action, expected: bytes) -> None:
        stream = _ErrorMappingStream(io.BytesIO(data), _test_mapper, "f.txt")
        assert action(stream) == expected

    def test_seek_tell_passthrough(self) -> None:
        inner = io.BytesIO(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.read(5)
        assert stream.tell() == 5
        stream.seek(0)
        assert stream.tell() == 0

    @pytest.mark.parametrize(
        ("attr", "expected"),
        [
            pytest.param("seekable", True, id="seekable"),
            pytest.param("readable", True, id="readable"),
        ],
    )
    def test_stream_capabilities(self, attr: str, expected: bool) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"hello"), _test_mapper, "f.txt")
        assert getattr(stream, attr)() is expected

    def test_iteration(self) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"a\nb\nc\n"), _test_mapper, "f.txt")
        assert list(stream) == [b"a\n", b"b\n", b"c\n"]

    def test_close_passthrough(self) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"hello"), _test_mapper, "f.txt")
        stream.close()
        assert stream.closed

    def test_readinto_passthrough(self) -> None:
        stream = _ErrorMappingStream(io.BytesIO(b"hello"), _test_mapper, "f.txt")
        buf = bytearray(5)
        n = stream.readinto(buf)
        assert n == 5
        assert buf == b"hello"


# ---------------------------------------------------------------------------
# Seek/tell None-fallback (paramiko-style)
# ---------------------------------------------------------------------------


class TestSeekTellNoneFallback:
    """seek()/tell() None-fallback for paramiko-style streams."""

    @pytest.mark.parametrize(
        ("offset", "setup_action", "expected_pos"),
        [
            pytest.param(0, lambda s: s.read(5), 0, id="seek-to-zero-after-read"),
            pytest.param(3, lambda _: None, 3, id="seek-to-nonzero"),
        ],
    )
    def test_seek_returns_position_when_inner_returns_none(
        self,
        offset,
        setup_action,
        expected_pos,
    ) -> None:
        inner = _ParamikoLikeStream(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        setup_action(stream)
        pos = stream.seek(offset)
        assert pos == expected_pos

    def test_tell_returns_int_when_inner_returns_none(self) -> None:
        """tell() guards against None even though paramiko returns int."""
        inner = io.BytesIO(b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.read(3)
        inner.tell = lambda: None  # type: ignore[assignment]
        assert stream.tell() == 0


# ---------------------------------------------------------------------------
# Error remapping and edge cases
# ---------------------------------------------------------------------------


class TestErrorMappingStreamErrors:
    """OSError remapping, programming error propagation, close swallowing."""

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
            pytest.param(lambda s: s.readline(), id="readline"),
            pytest.param(lambda s: s.seek(0), id="seek"),
            pytest.param(lambda s: s.tell(), id="tell"),
            pytest.param(lambda s: next(iter(s)), id="iteration"),
        ],
    )
    def test_operation_remaps_oserror(self, action) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            action(stream)

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
            pytest.param(lambda s: s.readline(), id="readline"),
            pytest.param(lambda s: s.seek(0), id="seek"),
            pytest.param(lambda s: s.tell(), id="tell"),
            pytest.param(lambda s: next(iter(s)), id="iteration"),
        ],
    )
    def test_operation_remaps_eoferror(self, action) -> None:
        """audit-020 M1: ``EOFError`` must map like ``OSError``.

        paramiko raises ``EOFError`` (not an ``OSError``) on a channel death
        mid-read. The wrapper caught only ``OSError``, so an ``EOFError`` escaped
        raw to the ``read()`` consumer, unmapped — and for the SFTP backend that
        also meant the dead client was never invalidated (a read-path wedge).
        """
        stream = _ErrorMappingStream(_EOFStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            action(stream)

    def test_exception_chain_preserved(self) -> None:
        """Mapped exception preserves original via __cause__ (from exc)."""
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound) as exc_info:
            stream.read()
        assert isinstance(exc_info.value.__cause__, OSError)

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
        ],
    )
    def test_type_error_propagates(self, action) -> None:
        stream = _ErrorMappingStream(_FailingStream(TypeError), _test_mapper, "f.txt")
        with pytest.raises(TypeError, match="bad argument"):
            action(stream)

    def test_close_swallows_errors(self) -> None:
        stream = _ErrorMappingStream(_FailingCloseStream(), _test_mapper, "f.txt")
        stream.close()  # should not raise
        assert stream.closed


# ---------------------------------------------------------------------------
# Futile-close guard (SIO-010, BK-355)
# ---------------------------------------------------------------------------


class TestFutileCloseGuard:
    """A close that would re-enter a connection the failure condemned is skipped.

    The cost this exists to remove is a *second* blocking round-trip: paramiko's
    ``SFTPFile.close()`` issues a synchronous ``CMD_CLOSE`` and waits, so
    releasing a stream that already failed on a stalled channel pays the bound
    again — silently, since the close sits under ``contextlib.suppress``. What
    is asserted here is the skip itself; that it costs one bound rather than two
    is measured against a real stalled channel in
    ``tests/backends/sftp/test_io_timeout.py``.
    """

    @pytest.mark.spec("SIO-010")
    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: s.read(), id="read"),
            pytest.param(lambda s: s.readinto(bytearray(10)), id="readinto"),
            pytest.param(lambda s: s.readline(), id="readline"),
            pytest.param(lambda s: s.seek(0), id="seek"),
            pytest.param(lambda s: s.tell(), id="tell"),
        ],
    )
    def test_a_fatal_failure_skips_the_inner_close(self, action) -> None:
        """Every mapping path arms the guard, not just the two a read goes through.

        Parametrised because the guard is per-path: an implementation recording
        the verdict in ``read``/``readinto`` only would leave the others unarmed,
        and this is the level at which that is a wrapper property.

        **What this does not claim.** These are wrapper-level cases against an
        inner stream that raises on demand; they do not say a real backend
        handle raises from all five. Against paramiko it does not: ``tell`` and a
        ``SEEK_SET`` / ``SEEK_CUR`` seek read ``_realpos`` locally and never
        round-trip, so a stalled channel neither blocks nor fails them, and
        ``SEEK_END`` round-trips but swallows the failure inside ``_get_size``
        (SFTP-030 states that as an exception;
        ``test_seek_to_end_on_a_stalled_channel_still_costs_two_bounds`` pins
        it). The guard is written per-path because the *wrapper* serves several
        backends whose inner streams differ, not because every path is reachable
        on any one of them.
        """
        inner = _CloseTrackingStream(_ChannelDeath("channel stalled"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)

        with pytest.raises(NotFound):
            action(stream)
        stream.close()

        assert inner.close_calls == 0, "the close re-entered a connection already condemned"
        assert stream.closed, "the wrapper must still report itself closed"

    @pytest.mark.spec("SIO-010")
    def test_a_non_fatal_failure_still_closes(self) -> None:
        """The guard is narrow: only what the predicate condemns skips the close.

        A stream can fail for reasons a close survives, and on those the close is
        what releases the handle — so skipping on *any* mapped failure would
        trade a bounded wait for a leak.
        """
        inner = _CloseTrackingStream(OSError("transient read error"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)

        with pytest.raises(NotFound):
            stream.read()
        stream.close()

        assert inner.close_calls == 1

    @pytest.mark.spec("SIO-010")
    def test_without_a_predicate_a_failure_never_skips_the_close(self) -> None:
        """The default is the old behaviour, unconditionally.

        S3, S3-boto3, S3-PyArrow, Azure and HTTP all construct the wrapper
        without a predicate. This pins that their close is byte-for-byte what it
        was: the guard must be opt-in, not a default the shared wrapper applies
        on their behalf.
        """
        inner = _CloseTrackingStream(_ChannelDeath("channel stalled"))
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")

        with pytest.raises(NotFound):
            stream.read()
        stream.close()

        assert inner.close_calls == 1

    @pytest.mark.spec("SIO-010")
    def test_a_stream_that_never_failed_closes_normally(self) -> None:
        """Holding a predicate is not itself a reason to skip."""
        inner = _CloseTrackingStream(data=b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)

        assert stream.read() == b"hello"
        stream.close()

        assert inner.close_calls == 1

    @pytest.mark.spec("SIO-010")
    def test_a_raising_predicate_propagates(self) -> None:
        """A classifier that raises is a programming error, not a mapped failure.

        The wrapper's contract is that programming errors propagate, and a
        predicate is pure inspection — so a raising one is a bug in the backend.
        Suppressing it would substitute silence for the real failure and leave
        the guard's verdict unset with nothing to say so.
        """
        inner = _CloseTrackingStream(OSError("read failed"))

        def _broken(exc: Exception) -> bool:
            raise AttributeError("predicate is broken")

        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_broken)

        with pytest.raises(AttributeError, match="predicate is broken"):
            stream.read()

        # The other half of the docstring, and the half a mutation reaches: a
        # predicate that raised returned no verdict, so the guard must stay
        # unarmed and the close must still release the handle. An
        # implementation that re-raised but set the flag would leak here while
        # the assertion above still passed.
        stream.close()
        assert inner.close_calls == 1, "a predicate that raised must not arm the guard"

    @pytest.mark.spec("SIO-010")
    def test_the_guard_survives_the_buffered_layer(self) -> None:
        """SFTP hands back ``BufferedReader(_ErrorMappingStream(...))``.

        The caller therefore never closes the wrapper directly — the buffer
        does, on its raw. A guard that only held when closed directly would be
        armed on the one construction no SFTP caller has.
        """
        inner = _CloseTrackingStream(_ChannelDeath("channel stalled"))
        raw = _ErrorMappingStream(inner, _test_mapper, "f.txt", is_fatal=_fatal)
        buffered = io.BufferedReader(cast("io.RawIOBase", raw))

        with pytest.raises(NotFound):
            buffered.read()
        buffered.close()

        assert inner.close_calls == 0
        assert raw.closed


# ---------------------------------------------------------------------------
# _safe_wrap tests (BUG-159)
# ---------------------------------------------------------------------------


class _TrackingStream(io.RawIOBase):
    """Stream that tracks whether close() was called.

    Extends RawIOBase (not BytesIO) so it can be wrapped in
    ``io.BufferedReader`` on Python 3.14+ which enforces the
    RawIOBase requirement.
    """

    def __init__(self, data: bytes = b"hello") -> None:
        super().__init__()
        self._buf = io.BytesIO(data)
        self.was_closed = False

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:
        return self._buf.readinto(b)  # type: ignore[arg-type]

    def close(self) -> None:
        self.was_closed = True
        super().close()


class TestSafeWrap:
    """Tests for the _safe_wrap helper."""

    @pytest.mark.spec("BUG-159")
    def test_successful_wrap(self) -> None:
        raw = _TrackingStream()
        result = _safe_wrap(raw, lambda s: io.BufferedReader(s))
        assert isinstance(result, io.BufferedReader)
        assert not raw.was_closed

    @pytest.mark.spec("BUG-159")
    def test_wrapper_failure_closes_raw(self) -> None:
        """If a wrapper raises, the raw handle is closed (BUG-159 fix)."""
        raw = _TrackingStream()

        def failing_wrapper(s: object) -> io.BytesIO:
            raise RuntimeError("wrapping failed")

        with pytest.raises(RuntimeError, match="wrapping failed"):
            _safe_wrap(raw, failing_wrapper)

        assert raw.was_closed, "Raw stream must be closed when wrapper fails"

    @pytest.mark.spec("BUG-159")
    def test_multi_layer_wrap(self) -> None:
        raw = _TrackingStream()
        result = _safe_wrap(
            raw,
            lambda s: _ErrorMappingStream(s, _test_mapper, "f.txt"),
            lambda s: io.BufferedReader(s),
        )
        assert isinstance(result, io.BufferedReader)
        assert not raw.was_closed

    @pytest.mark.spec("BUG-159")
    def test_second_wrapper_failure_closes_all(self) -> None:
        """If the second wrapper fails, both the first wrapper and raw are closed."""
        raw = _TrackingStream()
        first_layer_closed = []

        class _TrackingWrapper(io.RawIOBase):
            def __init__(self, inner: object) -> None:
                self._inner = inner

            def close(self) -> None:
                first_layer_closed.append(True)
                super().close()

            def readable(self) -> bool:
                return True

            def readinto(self, b: bytearray | memoryview) -> int:
                return 0

        def second_fails(s: object) -> io.BytesIO:
            raise ValueError("second layer failed")

        with pytest.raises(ValueError, match="second layer failed"):
            _safe_wrap(raw, _TrackingWrapper, second_fails)

        assert raw.was_closed
        assert first_layer_closed, "First wrapper layer must also be closed"
