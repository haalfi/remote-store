"""Tests for Store.read_seekable() -- seekable reads on any backend.

Tier 1: Capability.SEEKABLE_READ declaration (SEEK-001)
Store API: Store.read_seekable() (SEEK-002 through SEEK-012)

Covers spec 036-seekable-read.md.
"""

from __future__ import annotations

import io

import pytest

from remote_store._capabilities import Capability
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store() -> Store:
    """MemoryBackend store -- seekable streams."""
    s = Store(backend=MemoryBackend())
    s.write("test.txt", b"hello seekable world")
    s.write("large.bin", b"x" * 200)
    return s


class _NonSeekableRaw(io.RawIOBase):
    """A forward-only stream wrapping bytes for testing."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        data = self._buf.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def seekable(self) -> bool:
        return False


# ===========================================================================
# SEEK-001: Capability declaration
# ===========================================================================


class TestCapabilityDeclaration:
    """SEEK-001: backends that always return seekable streams declare SEEKABLE_READ."""

    @pytest.mark.spec("SEEK-001")
    @pytest.mark.parametrize(
        "backend_mod,backend_cls,declares",
        [
            pytest.param("remote_store.backends._local", "LocalBackend", True, id="local"),
            pytest.param("remote_store.backends._memory", "MemoryBackend", True, id="memory"),
            pytest.param("remote_store.backends._s3", "S3Backend", True, id="s3"),
            pytest.param("remote_store.backends._s3_pyarrow", "S3PyArrowBackend", True, id="s3-pyarrow"),
            pytest.param("remote_store.backends._sftp", "SFTPBackend", True, id="sftp"),
        ],
    )
    def test_declares_seekable_read(self, backend_mod: str, backend_cls: str, declares: bool) -> None:
        import importlib

        mod = importlib.import_module(backend_mod)
        cap_set = None
        for name in ("_ALL_CAPABILITIES", "_SFTP_CAPABILITIES"):
            cap_set = getattr(mod, name, None)
            if cap_set is not None:
                break
        assert cap_set is not None
        assert cap_set.supports(Capability.SEEKABLE_READ) is declares

    @pytest.mark.spec("SEEK-001")
    def test_azure_does_not_declare(self) -> None:
        from remote_store.backends._azure import _ALL_CAPABILITIES

        assert _ALL_CAPABILITIES.supports(Capability.SEEKABLE_READ) is False

    @pytest.mark.spec("SEEK-001")
    def test_http_does_not_declare(self) -> None:
        from remote_store.backends._http import _CAPABILITIES

        assert _CAPABILITIES.supports(Capability.SEEKABLE_READ) is False

    @pytest.mark.spec("SEEK-001")
    def test_memory_declares(self) -> None:
        from remote_store.backends._memory import _ALL_CAPABILITIES

        assert _ALL_CAPABILITIES.supports(Capability.SEEKABLE_READ) is True


# ===========================================================================
# SEEK-002: Store.read_seekable() contract
# ===========================================================================


class TestReadSeekableContract:
    """SEEK-002: read_seekable() always returns a seekable stream at byte 0."""

    @pytest.mark.spec("SEEK-002")
    def test_returns_seekable_stream(self, store: Store) -> None:
        stream = store.read_seekable("test.txt")
        assert stream.seekable()
        assert stream.read() == b"hello seekable world"
        stream.close()


# ===========================================================================
# SEEK-004: Passthrough for seekable backends
# ===========================================================================


class TestPassthrough:
    """SEEK-004: read_seekable() returns the read() stream on seekable backends."""

    @pytest.mark.spec("SEEK-004")
    def test_passthrough_returns_same_object(self, store: Store) -> None:
        read_stream = store.read("test.txt")
        seekable_stream = store.read_seekable("test.txt")
        # Both should produce the same content
        assert read_stream.read() == seekable_stream.read()
        read_stream.close()
        seekable_stream.close()


# ===========================================================================
# SEEK-005: Spool fallback for non-seekable backends
# ===========================================================================


class TestSpoolFallback:
    """SEEK-005: non-seekable backends get spooled to SpooledTemporaryFile."""

    @pytest.mark.spec("SEEK-005")
    def test_non_seekable_backend_spools(self) -> None:
        """Backend.read_seekable() default spools non-seekable streams."""
        from remote_store._backend import Backend

        backend = MemoryBackend()
        backend.write("test.txt", b"hello world")

        # Monkey-patch read() to return non-seekable stream
        original_read = backend.read

        def non_seekable_read(path: str) -> io.BinaryIO:
            stream = original_read(path)
            data = stream.read()
            stream.close()
            return io.BufferedReader(_NonSeekableRaw(data))  # type: ignore[arg-type]

        backend.read = non_seekable_read  # type: ignore[assignment]

        # Default read_seekable() should spool and return seekable
        result = Backend.read_seekable(backend, "test.txt")
        assert result.seekable()
        assert result.read() == b"hello world"
        result.seek(0)
        assert result.read() == b"hello world"
        result.close()


# ===========================================================================
# SEEK-010: Error propagation
# ===========================================================================


class TestErrorPropagation:
    """SEEK-010: backend errors propagate through read_seekable()."""

    @pytest.mark.spec("SEEK-010")
    def test_not_found_propagates(self, store: Store) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            store.read_seekable("nonexistent.txt")


# ===========================================================================
# SEEK-011: Original stream closed after spooling
# ===========================================================================


class TestStreamClosure:
    """SEEK-011: original stream is closed after spooling."""

    @pytest.mark.spec("SEEK-011")
    def test_original_closed_after_spool(self) -> None:
        backend = MemoryBackend()
        backend.write("test.txt", b"hello world")

        original_read = backend.read
        streams: list[io.BinaryIO] = []

        def tracking_read(path: str) -> io.BinaryIO:
            stream = original_read(path)
            data = stream.read()
            stream.close()
            raw = _NonSeekableRaw(data)
            s = io.BufferedReader(raw)  # type: ignore[arg-type]
            streams.append(s)
            return s

        backend.read = tracking_read  # type: ignore[assignment]

        from remote_store._backend import Backend

        result = Backend.read_seekable(backend, "test.txt")
        assert len(streams) == 1
        assert streams[0].closed
        result.close()
