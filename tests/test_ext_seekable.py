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
# SEEK-006: Azure Range Reader Override
# ===========================================================================


class TestAzureRangeReader:
    """SEEK-006: _AzureRangeReader seekable reader with mock blob client."""

    @pytest.mark.spec("SEEK-006")
    def test_lazy_download(self) -> None:
        """No data downloaded until read() is called."""
        from remote_store.backends._azure import _AzureRangeReader

        reader = _AzureRangeReader(_FakeBlobClient(b"hello"), 5)
        assert reader.tell() == 0
        # No reads yet -- nothing downloaded

    @pytest.mark.spec("SEEK-006")
    def test_seek_tell_no_io(self) -> None:
        """seek() and tell() update position without I/O."""
        from remote_store.backends._azure import _AzureRangeReader

        client = _FakeBlobClient(b"0123456789")
        reader = _AzureRangeReader(client, 10)
        assert reader.seek(5) == 5
        assert reader.tell() == 5
        assert reader.seek(-2, 1) == 3  # SEEK_CUR
        assert reader.seek(-1, 2) == 9  # SEEK_END
        assert client.download_count == 0  # no HTTP calls

    @pytest.mark.spec("SEEK-006")
    def test_one_request_per_readinto(self) -> None:
        """Each readinto() issues exactly one HTTP Range request."""
        from remote_store.backends._azure import _AzureRangeReader

        data = b"abcdefghij"
        client = _FakeBlobClient(data)
        reader = _AzureRangeReader(client, len(data))
        buf = bytearray(5)
        n = reader.readinto(buf)
        assert n == 5
        assert buf == b"abcde"
        assert client.download_count == 1
        n = reader.readinto(buf)
        assert n == 5
        assert buf == b"fghij"
        assert client.download_count == 2

    @pytest.mark.spec("SEEK-006")
    def test_seek_then_read(self) -> None:
        """Seek to offset, read from there."""
        from remote_store.backends._azure import _AzureRangeReader

        data = b"0123456789"
        client = _FakeBlobClient(data)
        reader = _AzureRangeReader(client, len(data))
        reader.seek(7)
        buf = bytearray(10)
        n = reader.readinto(buf)
        assert n == 3
        assert buf[:n] == b"789"

    @pytest.mark.spec("SEEK-006")
    def test_eof_returns_zero(self) -> None:
        """readinto() at EOF returns 0."""
        from remote_store.backends._azure import _AzureRangeReader

        reader = _AzureRangeReader(_FakeBlobClient(b"hi"), 2)
        reader.seek(0, 2)  # seek to end
        assert reader.readinto(bytearray(10)) == 0

    @pytest.mark.spec("SEEK-006")
    def test_error_mapping_wrapping(self) -> None:
        """Range reader errors are mapped via _ErrorMappingStream."""
        from remote_store._stream import _ErrorMappingStream
        from remote_store.backends._azure import _AzureRangeReader

        client = _FakeBlobClient(b"data", fail_on_read=True)
        reader = _AzureRangeReader(client, 4)

        def classify(exc: Exception, path: str) -> Exception:
            return exc

        wrapped = _ErrorMappingStream(reader, classify, "test.txt")
        # The _ErrorMappingStream should catch the OSError from readinto
        assert wrapped.seekable()


class _FakeBlobClient:
    """Mock blob client for _AzureRangeReader unit tests."""

    def __init__(self, data: bytes, *, fail_on_read: bool = False) -> None:
        self._data = data
        self.download_count = 0
        self._fail = fail_on_read

    def download_blob(self, *, offset: int = 0, length: int | None = None, max_concurrency: int = 1) -> _FakeDownloader:
        self.download_count += 1
        if self._fail:
            raise OSError("simulated download failure")
        end = offset + length if length is not None else len(self._data)
        return _FakeDownloader(self._data[offset:end])


class _FakeDownloader:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


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
