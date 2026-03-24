"""Tests for ext.seekable -- portable seekable reads.

Tier 1: Capability.SEEKABLE_READ declaration (SEEK-001)
Tier 3: ext.seekable.seekable_read() (SEEK-002 through SEEK-009)

Covers spec 036-seekable-read.md.
"""

from __future__ import annotations

import io
import warnings

import pytest

from remote_store._capabilities import Capability
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.seekable import seekable_read

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


class _NonSeekableStream(io.RawIOBase):
    """A forward-only stream wrapping bytes for testing."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:
        data = self._buf.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def seekable(self) -> bool:
        return False


def _make_non_seekable_store(store: Store) -> Store:
    """Wrap a store so read() returns non-seekable streams."""
    original_read = store.read

    def _read(path: str) -> io.BinaryIO:
        stream = original_read(path)
        data = stream.read()
        stream.close()
        return io.BufferedReader(_NonSeekableStream(data))  # type: ignore[arg-type]

    store.read = _read  # type: ignore[assignment]
    return store


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
            pytest.param("remote_store.backends._sftp", "SFTPBackend", True, id="sftp"),
        ],
    )
    def test_declares_seekable_read(self, backend_mod: str, backend_cls: str, declares: bool) -> None:
        import importlib

        mod = importlib.import_module(backend_mod)
        # Access the module-level capability set constant
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
# SEEK-002: Passthrough for seekable streams
# ===========================================================================


class TestPassthrough:
    """SEEK-002: seekable_read returns the same stream when already seekable."""

    @pytest.mark.spec("SEEK-002")
    def test_passthrough_returns_same_stream(self, store: Store) -> None:
        original = store.read("test.txt")
        try:
            assert original.seekable()
        finally:
            original.close()

        stream = seekable_read(store, "test.txt")
        assert stream.seekable()
        assert stream.read() == b"hello seekable world"
        stream.close()


# ===========================================================================
# SEEK-003: Spool for non-seekable streams
# ===========================================================================


class TestSpool:
    """SEEK-003: non-seekable streams are spooled to SpooledTemporaryFile."""

    @pytest.mark.spec("SEEK-003")
    def test_non_seekable_returns_seekable(self, store: Store) -> None:
        ns_store = _make_non_seekable_store(store)
        stream = seekable_read(ns_store, "test.txt")
        assert stream.seekable()
        assert stream.read() == b"hello seekable world"
        stream.seek(0)
        assert stream.read() == b"hello seekable world"
        stream.close()


# ===========================================================================
# SEEK-004: Large file spool spills to disk
# ===========================================================================


class TestLargeFileSpool:
    """SEEK-004: content > max_memory spills to disk."""

    @pytest.mark.spec("SEEK-004")
    def test_large_file_rolls_to_disk(self, store: Store) -> None:
        ns_store = _make_non_seekable_store(store)
        stream = seekable_read(ns_store, "large.bin", max_memory=50)
        assert stream.seekable()
        assert stream.read() == b"x" * 200
        # SpooledTemporaryFile._rolled is True when spilled to disk
        assert getattr(stream, "_rolled", False) is True
        stream.close()


# ===========================================================================
# SEEK-005: max_memory=0 always spools to disk
# ===========================================================================


class TestMaxMemoryZero:
    """SEEK-005: max_memory=0 forces spool even for tiny content."""

    @pytest.mark.spec("SEEK-005")
    def test_max_memory_zero(self, store: Store) -> None:
        ns_store = _make_non_seekable_store(store)
        stream = seekable_read(ns_store, "test.txt", max_memory=0)
        assert stream.seekable()
        assert stream.read() == b"hello seekable world"
        stream.close()


# ===========================================================================
# SEEK-006: Error propagation
# ===========================================================================


class TestErrorPropagation:
    """SEEK-006: backend errors propagate as Store errors."""

    @pytest.mark.spec("SEEK-006")
    def test_not_found_propagates(self, store: Store) -> None:
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            seekable_read(store, "nonexistent.txt")


# ===========================================================================
# SEEK-007: Original stream closed after spooling
# ===========================================================================


class TestStreamClosure:
    """SEEK-007: original stream is closed after spooling."""

    @pytest.mark.spec("SEEK-007")
    def test_original_closed_after_spool(self, store: Store) -> None:
        ns_store = _make_non_seekable_store(store)
        original_read = ns_store.read
        streams: list[io.BinaryIO] = []

        def tracking_read(path: str) -> io.BinaryIO:
            s = original_read(path)
            streams.append(s)
            return s

        ns_store.read = tracking_read  # type: ignore[assignment]
        result = seekable_read(ns_store, "test.txt")
        assert len(streams) == 1
        assert streams[0].closed
        result.close()


# ===========================================================================
# SEEK-008: Runtime guard -- capability declared but stream not seekable
# ===========================================================================


class TestRuntimeGuard:
    """SEEK-008: warning + fallback when capability declared but stream non-seekable."""

    @pytest.mark.spec("SEEK-008")
    def test_mismatch_warns_and_falls_back(self, store: Store) -> None:
        # MemoryBackend declares SEEKABLE_READ, so mock the stream to be non-seekable
        original_read = store.read

        def broken_read(path: str) -> io.BinaryIO:
            stream = original_read(path)
            data = stream.read()
            stream.close()
            return io.BufferedReader(_NonSeekableStream(data))  # type: ignore[arg-type]

        store.read = broken_read  # type: ignore[assignment]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = seekable_read(store, "test.txt")

        assert len(w) == 1
        assert "SEEKABLE_READ" in str(w[0].message)
        assert result.seekable()
        assert result.read() == b"hello seekable world"
        result.close()


# ===========================================================================
# SEEK-009: fileno() limitation on in-memory spool
# ===========================================================================


class TestFilenoLimitation:
    """SEEK-009: SpooledTemporaryFile fileno() availability depends on Python version.

    Python < 3.12: fileno() raises when content is in memory.
    Python >= 3.12: SpooledTemporaryFile always has a file descriptor.
    """

    @pytest.mark.spec("SEEK-009")
    def test_fileno_on_spooled_stream(self, store: Store) -> None:
        import sys

        ns_store = _make_non_seekable_store(store)
        stream = seekable_read(ns_store, "test.txt", max_memory=1024 * 1024)
        assert stream.seekable()
        if sys.version_info >= (3, 12):
            # Python 3.12+ always has a real file descriptor
            assert isinstance(stream.fileno(), int)
        else:
            with pytest.raises((AttributeError, io.UnsupportedOperation)):
                stream.fileno()
        stream.close()
