"""Tests covering specific uncovered code paths in MemoryBackend (BK-006)."""

from __future__ import annotations

import io

import pytest

from remote_store._errors import DirectoryNotEmpty, InvalidPath, NotFound
from remote_store.backends._memory import MemoryBackend


@pytest.fixture
def mb() -> MemoryBackend:
    return MemoryBackend()


# ---------------------------------------------------------------------------
# _split_path / _traverse / _ensure_parents validation
# ---------------------------------------------------------------------------


@pytest.mark.spec("MEM-DS-005")
@pytest.mark.parametrize(
    "path,match",
    [
        pytest.param("a/\0b", "null byte", id="null_byte"),
        pytest.param("/root/file", "Absolute", id="absolute"),
        pytest.param("a/../b", "\\.\\.", id="dotdot"),
    ],
)
def test_split_path_validation(mb: MemoryBackend, path: str, match: str) -> None:
    with pytest.raises(InvalidPath, match=match):
        mb.exists(path)


@pytest.mark.spec("MEM-DS-005")
@pytest.mark.parametrize(
    "method",
    [
        pytest.param("exists", id="exists"),
        pytest.param("is_file", id="is_file"),
        pytest.param("is_folder", id="is_folder"),
    ],
)
def test_traverse_through_file_returns_false(mb: MemoryBackend, method: str) -> None:
    mb.write("a/b", b"data")
    assert getattr(mb, method)("a/b/c") is False


@pytest.mark.spec("MEM-DS-005")
def test_file_blocks_intermediate_directory(mb: MemoryBackend) -> None:
    mb.write("a/b", b"data")
    with pytest.raises(InvalidPath, match="exists as a file"):
        mb.write("a/b/c/d", b"nested")


# ---------------------------------------------------------------------------
# is_file / write / delete empty/root path rejection
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-005")
@pytest.mark.parametrize("path", ["", "."], ids=["empty", "dot"])
def test_is_file_root(mb: MemoryBackend, path: str) -> None:
    assert mb.is_file(path) is False


@pytest.mark.parametrize(
    "op,args,match",
    [
        pytest.param("write", ("", b"data"), "must not be empty", id="write_empty"),
        pytest.param("write", (".", b"data"), "must not be empty", id="write_dot"),
        pytest.param("delete", ("",), "must not be empty", id="delete_empty"),
        pytest.param("delete_folder", ("",), "must not be empty", id="delete_folder_empty"),
    ],
)
def test_empty_path_rejected(mb: MemoryBackend, op: str, args: tuple, match: str) -> None:
    with pytest.raises(InvalidPath, match=match):
        getattr(mb, op)(*args)


@pytest.mark.spec("MEM-012")
@pytest.mark.parametrize(
    "label,data,expected",
    [
        pytest.param("directory", b"overwrite-dir", None, id="over_directory"),
        pytest.param("binaryio", io.BytesIO(b"streamed"), b"streamed", id="binaryio"),
    ],
)
def test_write_special_cases(mb: MemoryBackend, label: str, data: bytes, expected: bytes | None) -> None:
    if label == "directory":
        mb.write("a/b/c", b"file-under-b")
        with pytest.raises(InvalidPath, match="exists as a directory"):
            mb.write("a/b", data)
    else:
        mb.write("file.txt", data)
        assert mb.read_bytes("file.txt") == expected


# ---------------------------------------------------------------------------
# delete_folder edge cases
# ---------------------------------------------------------------------------


@pytest.mark.spec("MEM-014")
@pytest.mark.parametrize(
    "missing_ok,expect_raise",
    [
        pytest.param(False, True, id="raises"),
        pytest.param(True, False, id="missing_ok"),
    ],
)
def test_delete_folder_parent_is_file(mb: MemoryBackend, missing_ok: bool, expect_raise: bool) -> None:
    mb.write("a/b", b"data")
    if expect_raise:
        with pytest.raises(NotFound, match="Folder not found"):
            mb.delete_folder("a/b/sub", missing_ok=missing_ok)
    else:
        mb.delete_folder("a/b/sub", missing_ok=missing_ok)


@pytest.mark.spec("MEM-014")
def test_delete_folder_non_recursive_non_empty(mb: MemoryBackend) -> None:
    mb.write("a/b/c", b"data")
    with pytest.raises(DirectoryNotEmpty, match="not empty"):
        mb.delete_folder("a/b", recursive=False)


# ---------------------------------------------------------------------------
# get_file_info / get_folder_info
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-016")
def test_get_file_info_empty_path(mb: MemoryBackend) -> None:
    with pytest.raises(NotFound, match="empty path"):
        mb.get_file_info("")


@pytest.mark.spec("MEM-015")
def test_get_folder_info_with_nested_subdirectories(mb: MemoryBackend) -> None:
    mb.write("a/b/c", b"deep")
    mb.write("a/d", b"shallow")
    info = mb.get_folder_info("a")
    assert info.file_count == 2
    assert info.total_size == len(b"deep") + len(b"shallow")
    assert info.modified_at is not None


# ---------------------------------------------------------------------------
# move/copy empty paths and destination-is-directory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "op,src,dst,match",
    [
        pytest.param("move", "", "dst", "Source path must not be empty", id="move_empty_src"),
        pytest.param("move", "src", "", "Destination path must not be empty", id="move_empty_dst"),
        pytest.param("copy", "", "dst", "Source path must not be empty", id="copy_empty_src"),
        pytest.param("copy", "src", "", "Destination path must not be empty", id="copy_empty_dst"),
    ],
)
def test_move_copy_empty_paths(mb: MemoryBackend, op: str, src: str, dst: str, match: str) -> None:
    with pytest.raises(InvalidPath, match=match):
        getattr(mb, op)(src, dst)


@pytest.mark.parametrize("op", [pytest.param("move", id="move"), pytest.param("copy", id="copy")])
def test_dst_is_directory(mb: MemoryBackend, op: str) -> None:
    mb.write("src", b"data")
    mb.write("dst/child", b"nested")
    with pytest.raises(InvalidPath, match="exists as a directory"):
        getattr(mb, op)("src", "dst")


# ---------------------------------------------------------------------------
# move same-path / source parent not DirNode
# ---------------------------------------------------------------------------


@pytest.mark.spec("MEM-016")
def test_move_same_path_exists(mb: MemoryBackend) -> None:
    mb.write("a/b", b"data")
    mb.move("a/b", "a/b")
    assert mb.read_bytes("a/b") == b"data"


@pytest.mark.spec("MEM-016")
@pytest.mark.parametrize(
    "setup,path",
    [
        pytest.param(None, "missing", id="not_found"),
        pytest.param(("a/b/c", b"data"), "a/b", id="is_directory"),
    ],
)
def test_move_same_path_raises(mb: MemoryBackend, setup: tuple | None, path: str) -> None:
    if setup:
        mb.write(*setup)
    with pytest.raises(NotFound, match="Source not found"):
        mb.move(path, path)


@pytest.mark.spec("MEM-016")
def test_move_source_parent_is_file(mb: MemoryBackend) -> None:
    mb.write("x", b"file")
    with pytest.raises(NotFound, match="Source not found"):
        mb.move("x/child", "dst")
