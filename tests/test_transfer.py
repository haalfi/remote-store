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


def _store(*paths: str, data: bytes = b"file-data") -> Store:
    s = Store(backend=MemoryBackend())
    for p in paths:
        s.write(p, data)
    return s


def _restricted(exclude: set[Capability]) -> Store:
    return Store(backend=RestrictedBackend(MemoryBackend(), exclude=exclude), root_path="")  # type: ignore[arg-type]


def _file(tmp: Path, name: str = "file.txt", data: bytes = b"data") -> Path:
    p = tmp / name
    p.write_bytes(data)
    return p


# ===========================================================================
# XFER-001 through XFER-005: upload
# ===========================================================================


class TestUpload:
    @pytest.mark.spec("XFER-001")
    @pytest.mark.parametrize("use_str", [pytest.param(False, id="path_object"), pytest.param(True, id="str_path")])
    def test_basic_and_str_path(self, tmp_path: Path, use_str: bool) -> None:
        local = _file(tmp_path, "hello.txt", b"hello")
        dst = _store()
        assert upload(dst, str(local) if use_str else local, "hello.txt") is None
        assert dst.read_bytes("hello.txt") == b"hello"

    @pytest.mark.spec("XFER-002")
    def test_streaming_content(self, tmp_path: Path) -> None:
        dst = _store()
        upload(dst, _file(tmp_path, "data.bin", b"stream-this-data"), "data.bin")
        assert dst.read_bytes("data.bin") == b"stream-this-data"

    @pytest.mark.spec("XFER-003")
    @pytest.mark.parametrize("overwrite", [False, True], ids=["no_overwrite", "overwrite"])
    def test_overwrite(self, tmp_path: Path, overwrite: bool) -> None:
        local = _file(tmp_path, data=b"updated" if overwrite else b"new")
        dst = _store("file.txt")
        if overwrite:
            upload(dst, local, "file.txt", overwrite=True)
            assert dst.read_bytes("file.txt") == b"updated"
        else:
            with pytest.raises(AlreadyExists):
                upload(dst, local, "file.txt", overwrite=False)

    @pytest.mark.spec("XFER-004")
    @pytest.mark.parametrize(
        "mock_write", [pytest.param(False, id="raises"), pytest.param(True, id="no_store_interaction")]
    )
    def test_missing_local_file(self, tmp_path: Path, mock_write: bool) -> None:
        dst = _store()
        if mock_write:
            dst.write = MagicMock()  # type: ignore[assignment]
        with pytest.raises(FileNotFoundError):
            upload(dst, tmp_path / "nope.txt", "remote.txt")
        if mock_write:
            dst.write.assert_not_called()

    @pytest.mark.spec("XFER-005")
    @pytest.mark.parametrize(
        "use_callback", [pytest.param(True, id="fires"), pytest.param(False, id="none_no_wrapper")]
    )
    def test_on_progress(self, tmp_path: Path, use_callback: bool) -> None:
        local = _file(tmp_path, "prog.txt", b"abcdefgh")
        dst = _store()
        if use_callback:
            chunks: list[int] = []
            upload(dst, local, "prog.txt", on_progress=chunks.append)
            assert sum(chunks) == 8 and all(c > 0 for c in chunks)
        else:
            upload(dst, local, "prog.txt", on_progress=None)
            assert dst.read_bytes("prog.txt") == b"abcdefgh"


# ===========================================================================
# XFER-006 through XFER-010: download
# ===========================================================================


class TestDownload:
    @pytest.mark.spec("XFER-006")
    @pytest.mark.parametrize("use_str", [pytest.param(False, id="path_object"), pytest.param(True, id="str_path")])
    def test_basic_and_str_path(self, tmp_path: Path, use_str: bool) -> None:
        src = _store("file.txt", data=b"data")
        local = tmp_path / "file.txt"
        assert download(src, "file.txt", str(local) if use_str else local) is None
        assert local.read_bytes() == b"data"

    @pytest.mark.spec("XFER-007")
    def test_streaming_content(self, tmp_path: Path) -> None:
        content = b"x" * 2_000_000
        src = _store()
        src.write("big.bin", content)
        local = tmp_path / "big.bin"
        download(src, "big.bin", local)
        assert local.read_bytes() == content

    @pytest.mark.spec("XFER-008")
    @pytest.mark.parametrize(
        "scenario",
        [
            pytest.param("no_overwrite", id="no_overwrite"),
            pytest.param("overwrite", id="overwrite"),
            pytest.param("guard", id="guard_before_read"),
        ],
    )
    def test_overwrite(self, tmp_path: Path, scenario: str) -> None:
        src = _store("file.txt", data=b"remote-data")
        local = _file(tmp_path, data=b"existing")
        if scenario == "overwrite":
            download(src, "file.txt", local, overwrite=True)
            assert local.read_bytes() == b"remote-data"
        elif scenario == "guard":
            src.read = MagicMock()  # type: ignore[assignment]
            with pytest.raises(FileExistsError):
                download(src, "file.txt", local, overwrite=False)
            src.read.assert_not_called()
        else:
            with pytest.raises(FileExistsError):
                download(src, "file.txt", local, overwrite=False)

    @pytest.mark.spec("XFER-009")
    def test_on_progress_fires(self, tmp_path: Path) -> None:
        content = b"y" * 2_000_000
        src = _store()
        src.write("big.bin", content)
        chunks: list[int] = []
        download(src, "big.bin", tmp_path / "big.bin", on_progress=chunks.append)
        assert sum(chunks) == len(content) and len(chunks) >= 2

    @pytest.mark.spec("XFER-010")
    @pytest.mark.parametrize("scenario", ["error", "success"], ids=["on_error", "on_success"])
    def test_stream_cleanup(self, tmp_path: Path, scenario: str) -> None:
        src = _store("file.txt", data=b"data")
        stream = src.read("file.txt")
        src.read = MagicMock(return_value=stream)  # type: ignore[assignment]
        if scenario == "error":
            with pytest.raises(FileNotFoundError):
                download(src, "file.txt", tmp_path / "no_such_dir" / "file.txt", overwrite=True)
        else:
            download(src, "file.txt", tmp_path / "file.txt")
        assert stream.closed

    @pytest.mark.spec("XFER-006")
    def test_remote_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(NotFound):
            download(_store(), "nope.txt", tmp_path / "out.txt")


# ===========================================================================
# XFER-011 through XFER-015: transfer
# ===========================================================================


class TestTransfer:
    @pytest.mark.spec("XFER-011")
    def test_basic(self) -> None:
        src = _store("file.txt", data=b"data")
        assert transfer(src, "file.txt", _store(), "file.txt") is None

    @pytest.mark.spec("XFER-011")
    def test_same_store(self) -> None:
        s = _store("a.txt", data=b"data")
        transfer(s, "a.txt", s, "b.txt")
        assert s.read_bytes("b.txt") == b"data"

    @pytest.mark.spec("XFER-012")
    @pytest.mark.parametrize(
        "content", [pytest.param(b"transfer-data", id="small"), pytest.param(b"z" * 3_000_000, id="large")]
    )
    def test_streaming_content(self, content: bytes) -> None:
        src = _store("src.bin", data=content)
        dst = _store()
        transfer(src, "src.bin", dst, "dst.bin")
        assert dst.read_bytes("dst.bin") == content

    @pytest.mark.spec("XFER-013")
    @pytest.mark.parametrize("overwrite", [False, True], ids=["no_overwrite", "overwrite"])
    def test_overwrite(self, overwrite: bool) -> None:
        src = _store("file.txt", data=b"new")
        dst = _store("file.txt", data=b"old")
        if overwrite:
            transfer(src, "file.txt", dst, "file.txt", overwrite=True)
            assert dst.read_bytes("file.txt") == b"new"
        else:
            with pytest.raises(AlreadyExists):
                transfer(src, "file.txt", dst, "file.txt", overwrite=False)

    @pytest.mark.spec("XFER-014")
    def test_on_progress_fires(self) -> None:
        content = b"progress-data"
        src = _store("src.txt", data=content)
        chunks: list[int] = []
        transfer(src, "src.txt", _store(), "dst.txt", on_progress=chunks.append)
        assert sum(chunks) == len(content) and all(c > 0 for c in chunks)

    @pytest.mark.spec("XFER-015")
    @pytest.mark.parametrize(
        "scenario", [pytest.param("error", id="on_error"), pytest.param("success", id="on_success")]
    )
    def test_stream_cleanup(self, scenario: str) -> None:
        src = _store("file.txt", data=b"data")
        if scenario == "error":
            with pytest.raises(CapabilityNotSupported):
                transfer(src, "file.txt", _restricted({Capability.WRITE}), "file.txt")
        else:
            stream = src.read("file.txt")
            src.read = MagicMock(return_value=stream)  # type: ignore[assignment]
            transfer(src, "file.txt", _store(), "file.txt")
            assert stream.closed


# ===========================================================================
# XFER-016: No backend coupling
# ===========================================================================


@pytest.mark.spec("XFER-016")
@pytest.mark.parametrize(
    "op",
    [
        pytest.param("upload", id="upload"),
        pytest.param("download", id="download"),
        pytest.param("transfer", id="transfer"),
    ],
)
def test_child_store_operations(op: str, tmp_path: Path) -> None:
    root = Store(backend=MemoryBackend())
    if op == "upload":
        upload(root.child("sub"), _file(tmp_path, data=b"child-data"), "file.txt")
        assert root.read_bytes("sub/file.txt") == b"child-data"
    elif op == "download":
        root.write("sub/file.txt", b"child-data")
        download(root.child("sub"), "file.txt", tmp_path / "file.txt")
        assert (tmp_path / "file.txt").read_bytes() == b"child-data"
    else:
        root.write("src/file.txt", b"data")
        transfer(root.child("src"), "file.txt", root.child("dst"), "file.txt")
        assert root.read_bytes("dst/file.txt") == b"data"


# ===========================================================================
# XFER-017: Capability gating propagation
# ===========================================================================


@pytest.mark.spec("XFER-017")
@pytest.mark.parametrize(
    "make_call",
    [
        pytest.param(
            lambda tmp: upload(_restricted({Capability.WRITE}), _file(tmp, "f.txt"), "f.txt"), id="upload_no_write"
        ),
        pytest.param(
            lambda tmp: download(_restricted({Capability.READ}), "f.txt", tmp / "out.txt"), id="download_no_read"
        ),
        pytest.param(
            lambda tmp: transfer(_restricted({Capability.READ}), "f.txt", _store(), "o.txt"), id="transfer_no_read"
        ),
        pytest.param(
            lambda tmp: transfer(_store("f.txt"), "f.txt", _restricted({Capability.WRITE}), "f.txt"),
            id="transfer_no_write",
        ),
    ],
)
def test_capability_gating(make_call: Any, tmp_path: Path) -> None:
    with pytest.raises(CapabilityNotSupported):
        make_call(tmp_path)


# ===========================================================================
# ProgressReader & Module exports
# ===========================================================================


@pytest.mark.parametrize(
    "content, check_readable",
    [pytest.param(b"data", True, id="delegates_attributes"), pytest.param(b"", False, id="empty_no_callback")],
)
def test_progress_reader(content: bytes, check_readable: bool) -> None:
    s = _store()
    s.write("f.txt", content)
    stream = s.read("f.txt")
    calls: list[int] = []
    reader = ProgressReader(stream, (lambda n: None) if check_readable else calls.append)
    if check_readable:
        assert reader.readable()
    else:
        assert reader.read() == b"" and calls == []
    stream.close()


def test_module_exports() -> None:
    from remote_store.ext import transfer as mod

    assert set(mod.__all__) == {"upload", "download", "transfer"}
    from remote_store import download, transfer, upload

    assert all(x is not None for x in (upload, download, transfer))
