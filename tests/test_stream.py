"""Tests for _ErrorMappingStream."""

from __future__ import annotations

import io

import pytest

from remote_store._errors import NotFound, RemoteStoreError
from remote_store._stream import _ErrorMappingStream


def _test_mapper(exc: Exception, path: str) -> RemoteStoreError:
    """Simple mapper that converts any exception to NotFound."""
    return NotFound(f"mapped: {exc}", path=path, backend="test")


class TestErrorMappingStreamPassthrough:
    """Stream operations pass through to the inner stream when no error occurs."""

    def test_read_passthrough(self) -> None:
        inner = io.BytesIO(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        assert stream.read() == b"hello world"

    def test_read_with_size(self) -> None:
        inner = io.BytesIO(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        assert stream.read(5) == b"hello"

    def test_readline_passthrough(self) -> None:
        inner = io.BytesIO(b"line1\nline2\n")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        assert stream.readline() == b"line1\n"

    def test_seek_tell_passthrough(self) -> None:
        inner = io.BytesIO(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.read(5)
        assert stream.tell() == 5
        stream.seek(0)
        assert stream.tell() == 0

    def test_seekable(self) -> None:
        inner = io.BytesIO(b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        assert stream.seekable() is True

    def test_readable(self) -> None:
        inner = io.BytesIO(b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        assert stream.readable() is True

    def test_iteration(self) -> None:
        inner = io.BytesIO(b"a\nb\nc\n")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        lines = list(stream)
        assert lines == [b"a\n", b"b\n", b"c\n"]

    def test_close_passthrough(self) -> None:
        inner = io.BytesIO(b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.close()
        assert stream.closed

    def test_readinto_passthrough(self) -> None:
        inner = io.BytesIO(b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        buf = bytearray(5)
        n = stream.readinto(buf)
        assert n == 5
        assert buf == b"hello"


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


class TestSeekTellNoneFallback:
    """seek()/tell() None-fallback for paramiko-style streams."""

    def test_seek_returns_position_when_inner_returns_none(self) -> None:
        inner = _ParamikoLikeStream(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.read(5)
        pos = stream.seek(0)
        assert pos == 0
        assert stream.tell() == 0

    def test_seek_returns_position_for_nonzero_offset(self) -> None:
        inner = _ParamikoLikeStream(b"hello world")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        pos = stream.seek(3)
        assert pos == 3

    def test_tell_returns_int_when_inner_returns_none(self) -> None:
        """tell() guards against None even though paramiko returns int."""
        inner = io.BytesIO(b"hello")
        stream = _ErrorMappingStream(inner, _test_mapper, "f.txt")
        stream.read(3)
        # Patch tell to return None to exercise the guard
        inner.tell = lambda: None  # type: ignore[assignment]
        assert stream.tell() == 0


class _FailingStream(io.RawIOBase):
    """A stream that raises an OSError on every operation."""

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        raise OSError("disk failure")

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise OSError("disk failure")

    def readline(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise OSError("disk failure")

    def seek(self, offset: int, whence: int = 0) -> int:
        raise OSError("disk failure")

    def tell(self) -> int:
        raise OSError("disk failure")


class TestErrorMappingStreamRemapping:
    """OSError from the inner stream is remapped through the mapper."""

    def test_read_remaps(self) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            stream.read()

    def test_readinto_remaps(self) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        buf = bytearray(10)
        with pytest.raises(NotFound, match="mapped"):
            stream.readinto(buf)

    def test_readline_remaps(self) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            stream.readline()

    def test_seek_remaps(self) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            stream.seek(0)

    def test_tell_remaps(self) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            stream.tell()

    def test_iteration_remaps(self) -> None:
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound, match="mapped"):
            next(iter(stream))

    def test_exception_chain_preserved(self) -> None:
        """Mapped exception preserves original via __cause__ (from exc)."""
        stream = _ErrorMappingStream(_FailingStream(), _test_mapper, "f.txt")
        with pytest.raises(NotFound) as exc_info:
            stream.read()
        assert isinstance(exc_info.value.__cause__, OSError)


class _TypeErrorStream(io.RawIOBase):
    """A stream that raises TypeError (programming error) on read."""

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        raise TypeError("bad argument")

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        raise TypeError("bad argument")


class TestErrorMappingStreamProgrammingErrors:
    """Programming errors (TypeError, ValueError, etc.) must NOT be caught."""

    def test_type_error_propagates(self) -> None:
        stream = _ErrorMappingStream(_TypeErrorStream(), _test_mapper, "f.txt")
        with pytest.raises(TypeError, match="bad argument"):
            stream.read()

    def test_type_error_readinto_propagates(self) -> None:
        stream = _ErrorMappingStream(_TypeErrorStream(), _test_mapper, "f.txt")
        buf = bytearray(10)
        with pytest.raises(TypeError, match="bad argument"):
            stream.readinto(buf)


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


class TestErrorMappingStreamCloseSwallowing:
    """Errors during close() are swallowed."""

    def test_close_swallows_errors(self) -> None:
        stream = _ErrorMappingStream(_FailingCloseStream(), _test_mapper, "f.txt")
        stream.close()  # should not raise
        assert stream.closed
