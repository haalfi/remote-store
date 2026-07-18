"""Tests for _ErrorMappingStream and _safe_wrap."""

from __future__ import annotations

import io

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
