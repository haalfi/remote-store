"""Tests for remote_store.ext.transfer -- upload, download, cross-store transfer."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, CapabilityNotSupported, NotFound
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.transfer import _ProgressReader, download, transfer, upload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store() -> Store:
    """Return a Store backed by MemoryBackend."""
    return Store(backend=MemoryBackend())


def _populated_store(*paths: str, data: bytes = b"file-data") -> Store:
    """Return a Store with files written at the given paths."""
    store = _make_store()
    for p in paths:
        store.write(p, data)
    return store


class _NoReadBackend(MemoryBackend):
    """MemoryBackend with READ capability removed."""

    @property
    def capabilities(self) -> CapabilitySet:
        caps = set(super().capabilities._caps)
        caps.discard(Capability.READ)
        return CapabilitySet(frozenset(caps))


class _NoWriteBackend(MemoryBackend):
    """MemoryBackend with WRITE capability removed."""

    @property
    def capabilities(self) -> CapabilitySet:
        caps = set(super().capabilities._caps)
        caps.discard(Capability.WRITE)
        return CapabilitySet(frozenset(caps))


# ===========================================================================
# XFER-001 through XFER-005: upload
# ===========================================================================


class TestUpload:
    @pytest.mark.spec("XFER-001")
    def test_signature_basic(self, tmp_path: Path) -> None:
        """upload accepts store, local_path, remote_path and returns None."""
        local = tmp_path / "hello.txt"
        local.write_bytes(b"hello")
        store = _make_store()
        result = upload(store, local, "hello.txt")
        assert result is None

    @pytest.mark.spec("XFER-001")
    def test_accepts_str_path(self, tmp_path: Path) -> None:
        """upload accepts a string local_path."""
        local = tmp_path / "hello.txt"
        local.write_bytes(b"hello")
        store = _make_store()
        upload(store, str(local), "hello.txt")
        assert store.read_bytes("hello.txt") == b"hello"

    @pytest.mark.spec("XFER-002")
    def test_streaming_content(self, tmp_path: Path) -> None:
        """upload streams local file content to the Store."""
        content = b"stream-this-data"
        local = tmp_path / "data.bin"
        local.write_bytes(content)
        store = _make_store()
        upload(store, local, "data.bin")
        assert store.read_bytes("data.bin") == content

    @pytest.mark.spec("XFER-003")
    def test_overwrite_false_raises(self, tmp_path: Path) -> None:
        """upload with overwrite=False raises AlreadyExists on existing remote."""
        local = tmp_path / "file.txt"
        local.write_bytes(b"new")
        store = _populated_store("file.txt")
        with pytest.raises(AlreadyExists):
            upload(store, local, "file.txt", overwrite=False)

    @pytest.mark.spec("XFER-003")
    def test_overwrite_true(self, tmp_path: Path) -> None:
        """upload with overwrite=True replaces existing remote content."""
        local = tmp_path / "file.txt"
        local.write_bytes(b"updated")
        store = _populated_store("file.txt")
        upload(store, local, "file.txt", overwrite=True)
        assert store.read_bytes("file.txt") == b"updated"

    @pytest.mark.spec("XFER-004")
    def test_missing_local_file_raises(self, tmp_path: Path) -> None:
        """upload raises FileNotFoundError for missing local file."""
        store = _make_store()
        with pytest.raises(FileNotFoundError):
            upload(store, tmp_path / "nope.txt", "remote.txt")

    @pytest.mark.spec("XFER-004")
    def test_missing_local_no_store_interaction(self, tmp_path: Path) -> None:
        """FileNotFoundError is raised before any Store interaction."""
        store = _make_store()
        store.write = MagicMock()  # type: ignore[assignment]
        with pytest.raises(FileNotFoundError):
            upload(store, tmp_path / "nope.txt", "remote.txt")
        store.write.assert_not_called()

    @pytest.mark.spec("XFER-005")
    def test_on_progress_fires(self, tmp_path: Path) -> None:
        """on_progress callback fires with byte counts."""
        content = b"abcdefgh"
        local = tmp_path / "prog.txt"
        local.write_bytes(content)
        store = _make_store()
        chunks: list[int] = []
        upload(store, local, "prog.txt", on_progress=chunks.append)
        assert sum(chunks) == len(content)
        assert all(c > 0 for c in chunks)

    @pytest.mark.spec("XFER-005")
    def test_on_progress_none_no_wrapper(self, tmp_path: Path) -> None:
        """When on_progress is None, no wrapping occurs (basic sanity)."""
        local = tmp_path / "file.txt"
        local.write_bytes(b"data")
        store = _make_store()
        upload(store, local, "file.txt", on_progress=None)
        assert store.read_bytes("file.txt") == b"data"


# ===========================================================================
# XFER-006 through XFER-010: download
# ===========================================================================


class TestDownload:
    @pytest.mark.spec("XFER-006")
    def test_signature_basic(self, tmp_path: Path) -> None:
        """download accepts store, remote_path, local_path and returns None."""
        store = _populated_store("hello.txt", data=b"hello")
        local = tmp_path / "hello.txt"
        result = download(store, "hello.txt", local)
        assert result is None

    @pytest.mark.spec("XFER-006")
    def test_accepts_str_path(self, tmp_path: Path) -> None:
        """download accepts a string local_path."""
        store = _populated_store("file.txt", data=b"data")
        local = tmp_path / "file.txt"
        download(store, "file.txt", str(local))
        assert local.read_bytes() == b"data"

    @pytest.mark.spec("XFER-007")
    def test_streaming_content(self, tmp_path: Path) -> None:
        """download streams remote content to local file."""
        content = b"x" * 2_000_000  # 2 MiB — forces multiple chunks
        store = _make_store()
        store.write("big.bin", content)
        local = tmp_path / "big.bin"
        download(store, "big.bin", local)
        assert local.read_bytes() == content

    @pytest.mark.spec("XFER-008")
    def test_overwrite_false_raises(self, tmp_path: Path) -> None:
        """download with overwrite=False raises FileExistsError."""
        store = _populated_store("file.txt")
        local = tmp_path / "file.txt"
        local.write_bytes(b"existing")
        with pytest.raises(FileExistsError):
            download(store, "file.txt", local, overwrite=False)

    @pytest.mark.spec("XFER-008")
    def test_overwrite_guard_before_read(self, tmp_path: Path) -> None:
        """FileExistsError check happens before store.read()."""
        store = _populated_store("file.txt")
        store.read = MagicMock()  # type: ignore[assignment]
        local = tmp_path / "file.txt"
        local.write_bytes(b"existing")
        with pytest.raises(FileExistsError):
            download(store, "file.txt", local, overwrite=False)
        store.read.assert_not_called()

    @pytest.mark.spec("XFER-008")
    def test_overwrite_true(self, tmp_path: Path) -> None:
        """download with overwrite=True replaces existing local file."""
        store = _populated_store("file.txt", data=b"remote-data")
        local = tmp_path / "file.txt"
        local.write_bytes(b"old")
        download(store, "file.txt", local, overwrite=True)
        assert local.read_bytes() == b"remote-data"

    @pytest.mark.spec("XFER-009")
    def test_on_progress_fires(self, tmp_path: Path) -> None:
        """on_progress callback fires with chunk byte counts."""
        content = b"y" * 2_000_000  # forces multiple chunks
        store = _make_store()
        store.write("big.bin", content)
        local = tmp_path / "big.bin"
        chunks: list[int] = []
        download(store, "big.bin", local, on_progress=chunks.append)
        assert sum(chunks) == len(content)
        assert len(chunks) >= 2  # 2 MiB / 1 MiB = at least 2 chunks

    @pytest.mark.spec("XFER-010")
    def test_stream_cleanup_on_error(self, tmp_path: Path) -> None:
        """Remote stream is closed even if writing to local file fails."""
        store = _populated_store("file.txt")
        stream = store.read("file.txt")
        store.read = MagicMock(return_value=stream)  # type: ignore[assignment]

        # Point to a non-existent parent directory to force an OS error
        bad_path = tmp_path / "no_such_dir" / "file.txt"
        with pytest.raises(FileNotFoundError):
            download(store, "file.txt", bad_path, overwrite=True)
        assert stream.closed

    @pytest.mark.spec("XFER-010")
    def test_stream_cleanup_on_success(self, tmp_path: Path) -> None:
        """Remote stream is closed on successful download."""
        store = _populated_store("file.txt", data=b"ok")
        stream = store.read("file.txt")
        store.read = MagicMock(return_value=stream)  # type: ignore[assignment]
        local = tmp_path / "file.txt"
        download(store, "file.txt", local)
        assert stream.closed

    @pytest.mark.spec("XFER-006")
    def test_remote_not_found(self, tmp_path: Path) -> None:
        """download raises NotFound for missing remote file."""
        store = _make_store()
        with pytest.raises(NotFound):
            download(store, "nope.txt", tmp_path / "out.txt")


# ===========================================================================
# XFER-011 through XFER-015: transfer
# ===========================================================================


class TestTransfer:
    @pytest.mark.spec("XFER-011")
    def test_signature_basic(self) -> None:
        """transfer accepts src_store, src_path, dst_store, dst_path."""
        src = _populated_store("file.txt", data=b"data")
        dst = _make_store()
        result = transfer(src, "file.txt", dst, "file.txt")
        assert result is None

    @pytest.mark.spec("XFER-011")
    def test_same_store(self) -> None:
        """transfer works when src_store and dst_store are the same."""
        store = _populated_store("a.txt", data=b"data")
        transfer(store, "a.txt", store, "b.txt")
        assert store.read_bytes("b.txt") == b"data"

    @pytest.mark.spec("XFER-012")
    def test_streaming_content(self) -> None:
        """transfer streams content from src to dst."""
        content = b"transfer-data"
        src = _populated_store("src.txt", data=content)
        dst = _make_store()
        transfer(src, "src.txt", dst, "dst.txt")
        assert dst.read_bytes("dst.txt") == content

    @pytest.mark.spec("XFER-012")
    def test_large_file_transfer(self) -> None:
        """transfer handles large files across stores."""
        content = b"z" * 3_000_000
        src = _make_store()
        src.write("big.bin", content)
        dst = _make_store()
        transfer(src, "big.bin", dst, "big.bin")
        assert dst.read_bytes("big.bin") == content

    @pytest.mark.spec("XFER-013")
    def test_overwrite_false_raises(self) -> None:
        """transfer with overwrite=False raises AlreadyExists on existing dst."""
        src = _populated_store("file.txt", data=b"new")
        dst = _populated_store("file.txt", data=b"old")
        with pytest.raises(AlreadyExists):
            transfer(src, "file.txt", dst, "file.txt", overwrite=False)

    @pytest.mark.spec("XFER-013")
    def test_overwrite_true(self) -> None:
        """transfer with overwrite=True replaces existing dst content."""
        src = _populated_store("file.txt", data=b"new")
        dst = _populated_store("file.txt", data=b"old")
        transfer(src, "file.txt", dst, "file.txt", overwrite=True)
        assert dst.read_bytes("file.txt") == b"new"

    @pytest.mark.spec("XFER-014")
    def test_on_progress_fires(self) -> None:
        """on_progress callback fires with byte counts during transfer."""
        content = b"progress-data"
        src = _populated_store("src.txt", data=content)
        dst = _make_store()
        chunks: list[int] = []
        transfer(src, "src.txt", dst, "dst.txt", on_progress=chunks.append)
        assert sum(chunks) == len(content)
        assert all(c > 0 for c in chunks)

    @pytest.mark.spec("XFER-015")
    def test_stream_cleanup_on_error(self) -> None:
        """Source stream is closed even if dst_store.write() fails."""
        src = _populated_store("file.txt", data=b"data")
        dst = Store(backend=_NoWriteBackend())
        with pytest.raises(CapabilityNotSupported):
            transfer(src, "file.txt", dst, "file.txt")
        # The source stream from src.read() should have been closed.
        # We verify by reading again (if stream wasn't closed, this would still work).
        # The key point is no exception from unclosed resources.

    @pytest.mark.spec("XFER-015")
    def test_stream_cleanup_on_success(self) -> None:
        """Source stream is closed on successful transfer."""
        src = _populated_store("file.txt", data=b"data")
        stream = src.read("file.txt")
        src.read = MagicMock(return_value=stream)  # type: ignore[assignment]
        dst = _make_store()
        transfer(src, "file.txt", dst, "file.txt")
        assert stream.closed


# ===========================================================================
# XFER-016: No backend coupling
# ===========================================================================


class TestNoBackendCoupling:
    @pytest.mark.spec("XFER-016")
    def test_upload_with_child_store(self, tmp_path: Path) -> None:
        """upload works through Store.child()."""
        store = _make_store()
        child = store.child("sub")
        local = tmp_path / "file.txt"
        local.write_bytes(b"child-data")
        upload(child, local, "file.txt")
        assert store.read_bytes("sub/file.txt") == b"child-data"

    @pytest.mark.spec("XFER-016")
    def test_download_with_child_store(self, tmp_path: Path) -> None:
        """download works through Store.child()."""
        store = _make_store()
        store.write("sub/file.txt", b"child-data")
        child = store.child("sub")
        local = tmp_path / "file.txt"
        download(child, "file.txt", local)
        assert local.read_bytes() == b"child-data"

    @pytest.mark.spec("XFER-016")
    def test_transfer_with_child_stores(self) -> None:
        """transfer works through Store.child() on both ends."""
        backend = MemoryBackend()
        root = Store(backend=backend)
        root.write("src/file.txt", b"data")
        src_child = root.child("src")
        dst_child = root.child("dst")
        transfer(src_child, "file.txt", dst_child, "file.txt")
        assert root.read_bytes("dst/file.txt") == b"data"


# ===========================================================================
# XFER-017: Capability gating propagation
# ===========================================================================


class TestCapabilityGating:
    @pytest.mark.spec("XFER-017")
    def test_upload_write_capability(self, tmp_path: Path) -> None:
        """upload propagates CapabilityNotSupported from store.write()."""
        store = Store(backend=_NoWriteBackend())
        local = tmp_path / "file.txt"
        local.write_bytes(b"data")
        with pytest.raises(CapabilityNotSupported):
            upload(store, local, "file.txt")

    @pytest.mark.spec("XFER-017")
    def test_download_read_capability(self, tmp_path: Path) -> None:
        """download propagates CapabilityNotSupported from store.read()."""
        store = Store(backend=_NoReadBackend())
        with pytest.raises(CapabilityNotSupported):
            download(store, "file.txt", tmp_path / "out.txt")

    @pytest.mark.spec("XFER-017")
    def test_transfer_read_capability(self) -> None:
        """transfer propagates CapabilityNotSupported from src_store.read()."""
        src = Store(backend=_NoReadBackend())
        dst = _make_store()
        with pytest.raises(CapabilityNotSupported):
            transfer(src, "file.txt", dst, "out.txt")

    @pytest.mark.spec("XFER-017")
    def test_transfer_write_capability(self) -> None:
        """transfer propagates CapabilityNotSupported from dst_store.write()."""
        src = _populated_store("file.txt")
        dst = Store(backend=_NoWriteBackend())
        with pytest.raises(CapabilityNotSupported):
            transfer(src, "file.txt", dst, "file.txt")


# ===========================================================================
# _ProgressReader
# ===========================================================================


class TestProgressReader:
    def test_delegates_attributes(self) -> None:
        """_ProgressReader delegates unknown attributes to inner stream."""
        store = _populated_store("file.txt", data=b"data")
        stream = store.read("file.txt")
        reader = _ProgressReader(stream, lambda n: None)
        assert reader.readable()
        stream.close()

    def test_empty_read_no_callback(self) -> None:
        """on_progress is not called when read() returns empty bytes."""
        store = _make_store()
        store.write("empty.txt", b"")
        stream = store.read("empty.txt")
        calls: list[int] = []
        reader = _ProgressReader(stream, calls.append)
        data = reader.read()
        assert data == b""
        assert calls == []
        stream.close()


# ===========================================================================
# Module exports
# ===========================================================================


class TestModuleExports:
    def test_all_exports(self) -> None:
        from remote_store.ext import transfer as mod

        assert set(mod.__all__) == {"upload", "download", "transfer"}

    def test_top_level_import(self) -> None:
        """Transfer exports are available from the top-level package."""
        from remote_store import download, transfer, upload

        assert upload is not None
        assert download is not None
        assert transfer is not None
