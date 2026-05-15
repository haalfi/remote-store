"""Tests for Store.read_seekable() -- seekable reads on any backend.

Store API: Store.read_seekable() (SEEK-002 through SEEK-012)
SEEK-001 capability declaration is in tests/backends/conformance/test_identity.py.
SEEK-006 Azure _AzureRangeReader internals are in tests/backends/azure/test_seekable.py.

Covers spec 036-seekable-read.md.
"""

from __future__ import annotations

import io

import pytest

from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
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

    @pytest.mark.spec("SEEK-003")
    @pytest.mark.spec("SEEK-004")
    def test_passthrough_returns_same_object(self, store: Store) -> None:
        # Monkey-patch the backend's read() to capture the returned stream,
        # then verify read_seekable() returns the exact same object (identity).
        captured: list[io.BinaryIO] = []
        backend = store._backend
        original_read = backend.read

        def tracking_read(path: str) -> io.BinaryIO:
            s = original_read(path)
            captured.append(s)
            return s

        backend.read = tracking_read  # type: ignore[assignment]
        try:
            result = store.read_seekable("test.txt")
            assert len(captured) == 1
            assert result is captured[0], "read_seekable must return the same stream, not a wrapper"
            assert result.read() == b"hello seekable world"
            result.close()
        finally:
            backend.read = original_read  # type: ignore[assignment]


# ===========================================================================
# SEEK-005: Spool fallback for non-seekable backends
# ===========================================================================


class TestSpoolFallback:
    """SEEK-005: non-seekable backends get spooled to SpooledTemporaryFile."""

    @pytest.mark.spec("SEEK-003")
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


# ===========================================================================
# SEEK-012: read_seekable cleanup on error (_backend.py lines 159-161, 168-170)
# ===========================================================================


class TestReadSeekableCleanup:
    """SEEK-012: read_seekable closes stream/spool on error during setup."""

    @pytest.mark.spec("SEEK-012")
    def test_seekable_check_raises_closes_stream(self) -> None:
        """If stream.seekable() raises, the stream is closed before re-raise."""
        from remote_store._backend import Backend

        backend = MemoryBackend()
        backend.write("test.txt", b"data")
        opened: list[io.RawIOBase] = []

        class _BrokenSeekable(io.RawIOBase):
            def readable(self) -> bool:
                return True

            def seekable(self) -> bool:
                raise RuntimeError("seekable exploded")

            def readinto(self, b: bytearray) -> int:
                return 0

        def patched_read(path: str) -> io.BinaryIO:
            s = _BrokenSeekable()
            opened.append(s)
            return s  # type: ignore[return-value]

        backend.read = patched_read  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="seekable exploded"):
            Backend.read_seekable(backend, "test.txt")

        assert len(opened) == 1
        assert opened[0].closed

    @pytest.mark.spec("SEEK-012")
    def test_spool_copy_raises_closes_spool_and_stream(self) -> None:
        """If copyfileobj into spool raises, both spool and stream are closed."""

        from remote_store._backend import Backend

        backend = MemoryBackend()
        backend.write("test.txt", b"data")
        opened: list[io.RawIOBase] = []

        class _ExplodingNonSeekable(io.RawIOBase):
            def readable(self) -> bool:
                return True

            def seekable(self) -> bool:
                return False

            def readinto(self, b: bytearray) -> int:  # type: ignore[override]
                raise RuntimeError("read exploded mid-copy")

        def patched_read(path: str) -> io.BinaryIO:
            s = _ExplodingNonSeekable()
            opened.append(s)
            return s  # type: ignore[return-value]

        backend.read = patched_read  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="read exploded"):
            Backend.read_seekable(backend, "test.txt")

        assert len(opened) == 1
        assert opened[0].closed


# ===========================================================================
# SEEK-008: Arrow integration
# ===========================================================================


class TestArrowIntegration:
    """SEEK-008: open_input_file() calls read_seekable() for Tier 3."""

    @pytest.mark.spec("SEEK-008")
    def test_arrow_uses_read_seekable(self, store: Store) -> None:
        """Arrow open_input_file calls read_seekable for large files."""
        calls: list[str] = []
        original = store.read_seekable

        def tracking(path: str) -> io.BinaryIO:
            calls.append(path)
            return original(path)

        store.read_seekable = tracking  # type: ignore[assignment]
        try:
            from remote_store.ext.arrow import pyarrow_fs

            store.write("test.bin", b"x" * 100)
            fs = pyarrow_fs(store, materialization_threshold=10)
            with fs.open_input_file("test.bin") as f:
                f.read()
            assert "test.bin" in calls
        except ImportError:
            pytest.skip("pyarrow not installed")
        finally:
            store.read_seekable = original  # type: ignore[assignment]


# ===========================================================================
# SEEK-009: ProxyStore forwarding
# ===========================================================================


class TestProxyForwarding:
    """SEEK-009: ProxyStore.read_seekable() delegates to inner."""

    @pytest.mark.spec("SEEK-009")
    def test_proxy_forwards_read_seekable(self, store: Store) -> None:
        from remote_store._proxy import ProxyStore

        proxy = ProxyStore(store)
        stream = proxy.read_seekable("test.txt")
        assert stream.seekable()
        assert stream.read() == b"hello seekable world"
        stream.close()
