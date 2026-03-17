"""Tests for remote_store.ext.transfer -- upload, download, cross-store transfer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, CapabilityNotSupported, NotFound
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.streams import ProgressReader
from remote_store.ext.transfer import download, transfer, upload

from .conftest import RestrictedBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store() -> Store:
    return Store(backend=MemoryBackend())


def _populated_store(*paths: str, data: bytes = b"file-data") -> Store:
    store = _make_store()
    for p in paths:
        store.write(p, data)
    return store


def _no_write_store() -> Store:
    backend = MemoryBackend()
    return Store(backend=RestrictedBackend(backend, exclude={Capability.WRITE}), root_path="")  # type: ignore[arg-type]


def _no_read_store() -> Store:
    backend = MemoryBackend()
    return Store(backend=RestrictedBackend(backend, exclude={Capability.READ}), root_path="")  # type: ignore[arg-type]


# ===========================================================================
# XFER-001 through XFER-005: upload
# ===========================================================================


class TestUpload:
    @pytest.mark.spec("XFER-001")
    def test_signature_basic(self, tmp_path: Path) -> None:
        local = tmp_path / "hello.txt"
        local.write_bytes(b"hello")
        assert upload(_make_store(), local, "hello.txt") is None

    @pytest.mark.spec("XFER-001")
    def test_accepts_str_path(self, tmp_path: Path) -> None:
        local = tmp_path / "hello.txt"
        local.write_bytes(b"hello")
        store = _make_store()
        upload(store, str(local), "hello.txt")
        assert store.read_bytes("hello.txt") == b"hello"

    @pytest.mark.spec("XFER-002")
    def test_streaming_content(self, tmp_path: Path) -> None:
        content = b"stream-this-data"
        local = tmp_path / "data.bin"
        local.write_bytes(content)
        store = _make_store()
        upload(store, local, "data.bin")
        assert store.read_bytes("data.bin") == content

    @pytest.mark.spec("XFER-003")
    @pytest.mark.parametrize("overwrite", [False, True], ids=["no_overwrite", "overwrite"])
    def test_overwrite(self, tmp_path: Path, overwrite: bool) -> None:
        local = tmp_path / "file.txt"
        local.write_bytes(b"new" if not overwrite else b"updated")
        store = _populated_store("file.txt")
        if overwrite:
            upload(store, local, "file.txt", overwrite=True)
            assert store.read_bytes("file.txt") == b"updated"
        else:
            with pytest.raises(AlreadyExists):
                upload(store, local, "file.txt", overwrite=False)

    @pytest.mark.spec("XFER-004")
    def test_missing_local_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            upload(_make_store(), tmp_path / "nope.txt", "remote.txt")

    @pytest.mark.spec("XFER-004")
    def test_missing_local_no_store_interaction(self, tmp_path: Path) -> None:
        store = _make_store()
        store.write = MagicMock()  # type: ignore[assignment]
        with pytest.raises(FileNotFoundError):
            upload(store, tmp_path / "nope.txt", "remote.txt")
        store.write.assert_not_called()

    @pytest.mark.spec("XFER-005")
    def test_on_progress_fires(self, tmp_path: Path) -> None:
        content = b"abcdefgh"
        local = tmp_path / "prog.txt"
        local.write_bytes(content)
        chunks: list[int] = []
        upload(_make_store(), local, "prog.txt", on_progress=chunks.append)
        assert sum(chunks) == len(content) and all(c > 0 for c in chunks)

    @pytest.mark.spec("XFER-005")
    def test_on_progress_none_no_wrapper(self, tmp_path: Path) -> None:
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
        store = _populated_store("hello.txt", data=b"hello")
        assert download(store, "hello.txt", tmp_path / "hello.txt") is None

    @pytest.mark.spec("XFER-006")
    def test_accepts_str_path(self, tmp_path: Path) -> None:
        store = _populated_store("file.txt", data=b"data")
        local = tmp_path / "file.txt"
        download(store, "file.txt", str(local))
        assert local.read_bytes() == b"data"

    @pytest.mark.spec("XFER-007")
    def test_streaming_content(self, tmp_path: Path) -> None:
        content = b"x" * 2_000_000
        store = _make_store()
        store.write("big.bin", content)
        local = tmp_path / "big.bin"
        download(store, "big.bin", local)
        assert local.read_bytes() == content

    @pytest.mark.spec("XFER-008")
    def test_overwrite_false_raises(self, tmp_path: Path) -> None:
        store = _populated_store("file.txt")
        local = tmp_path / "file.txt"
        local.write_bytes(b"existing")
        with pytest.raises(FileExistsError):
            download(store, "file.txt", local, overwrite=False)

    @pytest.mark.spec("XFER-008")
    def test_overwrite_guard_before_read(self, tmp_path: Path) -> None:
        store = _populated_store("file.txt")
        store.read = MagicMock()  # type: ignore[assignment]
        local = tmp_path / "file.txt"
        local.write_bytes(b"existing")
        with pytest.raises(FileExistsError):
            download(store, "file.txt", local, overwrite=False)
        store.read.assert_not_called()

    @pytest.mark.spec("XFER-008")
    def test_overwrite_true(self, tmp_path: Path) -> None:
        store = _populated_store("file.txt", data=b"remote-data")
        local = tmp_path / "file.txt"
        local.write_bytes(b"old")
        download(store, "file.txt", local, overwrite=True)
        assert local.read_bytes() == b"remote-data"

    @pytest.mark.spec("XFER-009")
    def test_on_progress_fires(self, tmp_path: Path) -> None:
        content = b"y" * 2_000_000
        store = _make_store()
        store.write("big.bin", content)
        chunks: list[int] = []
        download(store, "big.bin", tmp_path / "big.bin", on_progress=chunks.append)
        assert sum(chunks) == len(content) and len(chunks) >= 2

    @pytest.mark.spec("XFER-010")
    @pytest.mark.parametrize(
        "scenario",
        ["error", "success"],
        ids=["on_error", "on_success"],
    )
    def test_stream_cleanup(self, tmp_path: Path, scenario: str) -> None:
        store = _populated_store("file.txt", data=b"data")
        stream = store.read("file.txt")
        store.read = MagicMock(return_value=stream)  # type: ignore[assignment]
        if scenario == "error":
            bad_path = tmp_path / "no_such_dir" / "file.txt"
            with pytest.raises(FileNotFoundError):
                download(store, "file.txt", bad_path, overwrite=True)
        else:
            download(store, "file.txt", tmp_path / "file.txt")
        assert stream.closed

    @pytest.mark.spec("XFER-006")
    def test_remote_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(NotFound):
            download(_make_store(), "nope.txt", tmp_path / "out.txt")


# ===========================================================================
# XFER-011 through XFER-015: transfer
# ===========================================================================


class TestTransfer:
    @pytest.mark.spec("XFER-011")
    def test_signature_basic(self) -> None:
        src = _populated_store("file.txt", data=b"data")
        assert transfer(src, "file.txt", _make_store(), "file.txt") is None

    @pytest.mark.spec("XFER-011")
    def test_same_store(self) -> None:
        store = _populated_store("a.txt", data=b"data")
        transfer(store, "a.txt", store, "b.txt")
        assert store.read_bytes("b.txt") == b"data"

    @pytest.mark.spec("XFER-012")
    def test_streaming_content(self) -> None:
        content = b"transfer-data"
        src = _populated_store("src.txt", data=content)
        dst = _make_store()
        transfer(src, "src.txt", dst, "dst.txt")
        assert dst.read_bytes("dst.txt") == content

    @pytest.mark.spec("XFER-012")
    def test_large_file_transfer(self) -> None:
        content = b"z" * 3_000_000
        src = _make_store()
        src.write("big.bin", content)
        dst = _make_store()
        transfer(src, "big.bin", dst, "big.bin")
        assert dst.read_bytes("big.bin") == content

    @pytest.mark.spec("XFER-013")
    @pytest.mark.parametrize("overwrite", [False, True], ids=["no_overwrite", "overwrite"])
    def test_overwrite(self, overwrite: bool) -> None:
        src = _populated_store("file.txt", data=b"new")
        dst = _populated_store("file.txt", data=b"old")
        if overwrite:
            transfer(src, "file.txt", dst, "file.txt", overwrite=True)
            assert dst.read_bytes("file.txt") == b"new"
        else:
            with pytest.raises(AlreadyExists):
                transfer(src, "file.txt", dst, "file.txt", overwrite=False)

    @pytest.mark.spec("XFER-014")
    def test_on_progress_fires(self) -> None:
        content = b"progress-data"
        src = _populated_store("src.txt", data=content)
        chunks: list[int] = []
        transfer(src, "src.txt", _make_store(), "dst.txt", on_progress=chunks.append)
        assert sum(chunks) == len(content) and all(c > 0 for c in chunks)

    @pytest.mark.spec("XFER-015")
    def test_stream_cleanup_on_error(self) -> None:
        src = _populated_store("file.txt", data=b"data")
        with pytest.raises(CapabilityNotSupported):
            transfer(src, "file.txt", _no_write_store(), "file.txt")

    @pytest.mark.spec("XFER-015")
    def test_stream_cleanup_on_success(self) -> None:
        src = _populated_store("file.txt", data=b"data")
        stream = src.read("file.txt")
        src.read = MagicMock(return_value=stream)  # type: ignore[assignment]
        transfer(src, "file.txt", _make_store(), "file.txt")
        assert stream.closed


# ===========================================================================
# XFER-016: No backend coupling
# ===========================================================================


class TestNoBackendCoupling:
    @pytest.mark.spec("XFER-016")
    def test_upload_with_child_store(self, tmp_path: Path) -> None:
        store = _make_store()
        local = tmp_path / "file.txt"
        local.write_bytes(b"child-data")
        upload(store.child("sub"), local, "file.txt")
        assert store.read_bytes("sub/file.txt") == b"child-data"

    @pytest.mark.spec("XFER-016")
    def test_download_with_child_store(self, tmp_path: Path) -> None:
        store = _make_store()
        store.write("sub/file.txt", b"child-data")
        local = tmp_path / "file.txt"
        download(store.child("sub"), "file.txt", local)
        assert local.read_bytes() == b"child-data"

    @pytest.mark.spec("XFER-016")
    def test_transfer_with_child_stores(self) -> None:
        root = Store(backend=MemoryBackend())
        root.write("src/file.txt", b"data")
        transfer(root.child("src"), "file.txt", root.child("dst"), "file.txt")
        assert root.read_bytes("dst/file.txt") == b"data"


# ===========================================================================
# XFER-017: Capability gating propagation
# ===========================================================================


@pytest.mark.spec("XFER-017")
def test_upload_write_capability(tmp_path: Path) -> None:
    local = tmp_path / "file.txt"
    local.write_bytes(b"data")
    with pytest.raises(CapabilityNotSupported):
        upload(_no_write_store(), local, "file.txt")


@pytest.mark.spec("XFER-017")
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda tmp: download(_no_read_store(), "f.txt", tmp / "out.txt"), id="download_no_read"),
        pytest.param(lambda tmp: transfer(_no_read_store(), "f.txt", _make_store(), "o.txt"), id="transfer_no_read"),
        pytest.param(
            lambda tmp: transfer(_populated_store("f.txt"), "f.txt", _no_write_store(), "f.txt"),
            id="transfer_no_write",
        ),
    ],
)
def test_capability_gating(call: Any, tmp_path: Path) -> None:
    with pytest.raises(CapabilityNotSupported):
        call(tmp_path)


# ===========================================================================
# ProgressReader (from ext.streams, used by ext.transfer)
# ===========================================================================


class TestProgressReader:
    def test_delegates_attributes(self) -> None:
        store = _populated_store("file.txt", data=b"data")
        stream = store.read("file.txt")
        reader = ProgressReader(stream, lambda n: None)
        assert reader.readable()
        stream.close()

    def test_empty_read_no_callback(self) -> None:
        store = _make_store()
        store.write("empty.txt", b"")
        stream = store.read("empty.txt")
        calls: list[int] = []
        reader = ProgressReader(stream, calls.append)
        assert reader.read() == b"" and calls == []
        stream.close()


# ===========================================================================
# Module exports
# ===========================================================================


class TestModuleExports:
    def test_all_exports(self) -> None:
        from remote_store.ext import transfer as mod

        assert set(mod.__all__) == {"upload", "download", "transfer"}

    def test_top_level_import(self) -> None:
        from remote_store import download, transfer, upload

        assert all(x is not None for x in (upload, download, transfer))
