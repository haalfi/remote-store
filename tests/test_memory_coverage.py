"""Tests covering specific uncovered code paths in MemoryBackend (BK-006)."""

from __future__ import annotations

import io

import pytest

from remote_store._errors import DirectoryNotEmpty, InvalidPath, NotFound
from remote_store.backends._memory import MemoryBackend


@pytest.fixture
def mb() -> MemoryBackend:
    return MemoryBackend()


# region: _split_path validation


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


# endregion


# region: _traverse file-as-directory


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


# endregion


# region: _ensure_parents file-as-intermediate


@pytest.mark.spec("MEM-DS-005")
def test_file_blocks_intermediate_directory(mb: MemoryBackend) -> None:
    mb.write("a/b", b"data")
    with pytest.raises(InvalidPath, match="exists as a file"):
        mb.write("a/b/c/d", b"nested")


# endregion


# region: is_file empty/root


@pytest.mark.spec("BE-005")
@pytest.mark.parametrize("path", ["", "."], ids=["empty", "dot"])
def test_is_file_root(mb: MemoryBackend, path: str) -> None:
    assert mb.is_file(path) is False


# endregion


# region: write/delete empty path rejection


@pytest.mark.parametrize(
    "op,args,match,spec",
    [
        pytest.param("write", ("", b"data"), "must not be empty", "MEM-012", id="write_empty"),
        pytest.param("write", (".", b"data"), "must not be empty", "MEM-012", id="write_dot"),
        pytest.param("delete", ("",), "must not be empty", "BE-012", id="delete_empty"),
        pytest.param("delete_folder", ("",), "must not be empty", "MEM-014", id="delete_folder_empty"),
    ],
)
def test_empty_path_rejected(
    mb: MemoryBackend,
    op: str,
    args: tuple,
    match: str,
    spec: str,  # noqa: ARG001
) -> None:
    with pytest.raises(InvalidPath, match=match):
        getattr(mb, op)(*args)


# endregion


# region: write directory-at-leaf


@pytest.mark.spec("MEM-012")
def test_write_over_directory(mb: MemoryBackend) -> None:
    mb.write("a/b/c", b"file-under-b")
    with pytest.raises(InvalidPath, match="exists as a directory"):
        mb.write("a/b", b"overwrite-dir")


# endregion


# region: delete_folder edge cases


@pytest.mark.spec("MEM-014")
def test_delete_folder_parent_is_file(mb: MemoryBackend) -> None:
    mb.write("a/b", b"data")
    with pytest.raises(NotFound, match="Folder not found"):
        mb.delete_folder("a/b/sub")


@pytest.mark.spec("MEM-014")
def test_delete_folder_parent_is_file_missing_ok(mb: MemoryBackend) -> None:
    mb.write("a/b", b"data")
    mb.delete_folder("a/b/sub", missing_ok=True)


@pytest.mark.spec("MEM-014")
def test_delete_folder_non_recursive_non_empty(mb: MemoryBackend) -> None:
    mb.write("a/b/c", b"data")
    with pytest.raises(DirectoryNotEmpty, match="not empty"):
        mb.delete_folder("a/b", recursive=False)


# endregion


# region: get_file_info / get_folder_info


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


# endregion


# region: move/copy empty paths and destination-is-directory


@pytest.mark.parametrize(
    "op,src,dst,match,spec",
    [
        pytest.param("move", "", "dst", "Source path must not be empty", "MEM-016", id="move_empty_src"),
        pytest.param("move", "src", "", "Destination path must not be empty", "MEM-016", id="move_empty_dst"),
        pytest.param("copy", "", "dst", "Source path must not be empty", "MEM-016b", id="copy_empty_src"),
        pytest.param("copy", "src", "", "Destination path must not be empty", "MEM-016b", id="copy_empty_dst"),
    ],
)
def test_move_copy_empty_paths(
    mb: MemoryBackend,
    op: str,
    src: str,
    dst: str,
    match: str,
    spec: str,  # noqa: ARG001
) -> None:
    with pytest.raises(InvalidPath, match=match):
        getattr(mb, op)(src, dst)


@pytest.mark.parametrize(
    "op,spec",
    [
        pytest.param("move", "MEM-016", id="move"),
        pytest.param("copy", "MEM-016b", id="copy"),
    ],
)
def test_dst_is_directory(
    mb: MemoryBackend,
    op: str,
    spec: str,  # noqa: ARG001
) -> None:
    mb.write("src", b"data")
    mb.write("dst/child", b"nested")
    with pytest.raises(InvalidPath, match="exists as a directory"):
        getattr(mb, op)("src", "dst")


# endregion


# region: move same-path


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


# endregion


# region: move source parent not DirNode


@pytest.mark.spec("MEM-016")
def test_move_source_parent_is_file(mb: MemoryBackend) -> None:
    mb.write("x", b"file")
    with pytest.raises(NotFound, match="Source not found"):
        mb.move("x/child", "dst")


# endregion


# region: write with BinaryIO content


@pytest.mark.spec("MEM-012")
def test_write_binaryio(mb: MemoryBackend) -> None:
    stream = io.BytesIO(b"streamed")
    mb.write("file.txt", stream)
    assert mb.read_bytes("file.txt") == b"streamed"


# endregion
