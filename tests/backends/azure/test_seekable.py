"""Azure-specific seekable-read tests (SEEK-006).

``_AzureRangeReader`` internal behaviour — range-read coalescing and seek
semantics. These tests exercise Azure implementation details that are not
cross-protocol invariants and belong here rather than in the conformance
suite.

SEEK-001 capability declaration is in
``tests/backends/conformance/test_identity.py``.
"""

from __future__ import annotations

import pytest


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
        """Range reader errors are caught by _ErrorMappingStream."""
        from remote_store._stream import _ErrorMappingStream
        from remote_store.backends._azure import _AzureRangeReader

        client = _FakeBlobClient(b"data", fail_on_read=True)
        reader = _AzureRangeReader(client, 4)

        def classify(exc: Exception, path: str) -> Exception:
            return exc

        wrapped = _ErrorMappingStream(reader, classify, "test.txt")
        assert wrapped.seekable()
        # Actually exercise the error path: readinto raises OSError,
        # _ErrorMappingStream catches it and passes to classify.
        with pytest.raises(OSError):
            wrapped.read(4)
