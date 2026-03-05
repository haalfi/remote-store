"""Tests covering specific uncovered code paths in MemoryBackend (BK-006)."""

from __future__ import annotations

import io

import pytest

from remote_store._errors import DirectoryNotEmpty, InvalidPath, NotFound
from remote_store.backends._memory import MemoryBackend


@pytest.fixture
def mb() -> MemoryBackend:
    return MemoryBackend()


# region: _split_path validation (lines 82, 84, 91)


class TestSplitPathValidation:
    """InvalidPath raised for null bytes, absolute paths, and '..' segments."""

    @pytest.mark.spec("MEM-DS-005")
    def test_null_byte_rejected(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="null byte"):
            mb.exists("a/\0b")

    @pytest.mark.spec("MEM-DS-005")
    def test_absolute_path_rejected(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="Absolute"):
            mb.exists("/root/file")

    @pytest.mark.spec("MEM-DS-005")
    def test_dotdot_segment_rejected(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="\\.\\."):
            mb.exists("a/../b")


# endregion


# region: _traverse file-as-directory (line 100)


class TestTraverseFileAsDirectory:
    """_traverse returns None when a file node is hit mid-path."""

    @pytest.mark.spec("MEM-DS-005")
    def test_traverse_through_file_returns_false(self, mb: MemoryBackend) -> None:
        mb.write("a/b", b"data")
        # "b" is a file, so "a/b/c" doesn't exist
        assert mb.exists("a/b/c") is False

    @pytest.mark.spec("MEM-DS-005")
    def test_is_file_through_file_returns_false(self, mb: MemoryBackend) -> None:
        mb.write("a/b", b"data")
        assert mb.is_file("a/b/c") is False

    @pytest.mark.spec("MEM-DS-005")
    def test_is_folder_through_file_returns_false(self, mb: MemoryBackend) -> None:
        mb.write("a/b", b"data")
        assert mb.is_folder("a/b/c") is False


# endregion


# region: _ensure_parents file-as-intermediate (line 117)


class TestEnsureParentsConflict:
    """InvalidPath when a file blocks directory creation."""

    @pytest.mark.spec("MEM-DS-005")
    def test_file_blocks_intermediate_directory(self, mb: MemoryBackend) -> None:
        mb.write("a/b", b"data")
        with pytest.raises(InvalidPath, match="exists as a file"):
            mb.write("a/b/c/d", b"nested")


# endregion


# region: is_file empty/root (line 140)


class TestIsFileRoot:
    """is_file returns False for root path."""

    @pytest.mark.spec("BE-005")
    def test_is_file_empty_string(self, mb: MemoryBackend) -> None:
        assert mb.is_file("") is False

    @pytest.mark.spec("BE-005")
    def test_is_file_dot(self, mb: MemoryBackend) -> None:
        assert mb.is_file(".") is False


# endregion


# region: write empty path (line 178)


class TestWriteEmptyPath:
    """write raises InvalidPath for empty path."""

    @pytest.mark.spec("MEM-012")
    def test_write_empty_path(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="must not be empty"):
            mb.write("", b"data")

    @pytest.mark.spec("MEM-012")
    def test_write_dot_path(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="must not be empty"):
            mb.write(".", b"data")


# endregion


# region: write directory-at-leaf (line 188)


class TestWriteDirectoryAtLeaf:
    """write raises InvalidPath when leaf is a directory."""

    @pytest.mark.spec("MEM-012")
    def test_write_over_directory(self, mb: MemoryBackend) -> None:
        mb.write("a/b/c", b"file-under-b")
        # "b" is now a directory
        with pytest.raises(InvalidPath, match="exists as a directory"):
            mb.write("a/b", b"overwrite-dir")


# endregion


# region: delete empty path (line 215)


class TestDeleteEmptyPath:
    """delete raises InvalidPath for empty path."""

    @pytest.mark.spec("BE-012")
    def test_delete_empty_path(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="must not be empty"):
            mb.delete("")


# endregion


# region: delete_folder empty path (line 235)


class TestDeleteFolderEmptyPath:
    """delete_folder raises InvalidPath for empty path."""

    @pytest.mark.spec("MEM-014")
    def test_delete_folder_empty_path(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="must not be empty"):
            mb.delete_folder("")


# endregion


# region: delete_folder parent not a DirNode (lines 240-242)


class TestDeleteFolderParentNotDir:
    """delete_folder raises NotFound when parent is a file."""

    @pytest.mark.spec("MEM-014")
    def test_delete_folder_parent_is_file(self, mb: MemoryBackend) -> None:
        mb.write("a/b", b"data")
        with pytest.raises(NotFound, match="Folder not found"):
            mb.delete_folder("a/b/sub")

    @pytest.mark.spec("MEM-014")
    def test_delete_folder_parent_is_file_missing_ok(self, mb: MemoryBackend) -> None:
        mb.write("a/b", b"data")
        # Should not raise
        mb.delete_folder("a/b/sub", missing_ok=True)


# endregion


# region: delete_folder non-recursive non-empty (line 253)


class TestDeleteFolderNonRecursiveNonEmpty:
    """delete_folder raises DirectoryNotEmpty when recursive=False."""

    @pytest.mark.spec("MEM-014")
    def test_delete_folder_non_recursive_non_empty(self, mb: MemoryBackend) -> None:
        mb.write("a/b/c", b"data")
        with pytest.raises(DirectoryNotEmpty, match="not empty"):
            mb.delete_folder("a/b", recursive=False)


# endregion


# region: get_file_info empty path (line 340)


class TestGetFileInfoEmptyPath:
    """get_file_info raises NotFound for empty path."""

    @pytest.mark.spec("BE-016")
    def test_get_file_info_empty_path(self, mb: MemoryBackend) -> None:
        with pytest.raises(NotFound, match="empty path"):
            mb.get_file_info("")


# endregion


# region: get_folder_info nested subdirectories (lines 371-372)


class TestGetFolderInfoNestedDirs:
    """get_folder_info traverses DirNode children in stack."""

    @pytest.mark.spec("MEM-015")
    def test_get_folder_info_with_nested_subdirectories(self, mb: MemoryBackend) -> None:
        mb.write("a/b/c", b"deep")
        mb.write("a/d", b"shallow")
        info = mb.get_folder_info("a")
        assert info.file_count == 2
        assert info.total_size == len(b"deep") + len(b"shallow")
        assert info.modified_at is not None


# endregion


# region: move empty paths (lines 388, 390)


class TestMoveEmptyPaths:
    """move raises InvalidPath for empty source or destination."""

    @pytest.mark.spec("MEM-016")
    def test_move_empty_src(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="Source path must not be empty"):
            mb.move("", "dst")

    @pytest.mark.spec("MEM-016")
    def test_move_empty_dst(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="Destination path must not be empty"):
            mb.move("src", "")


# endregion


# region: move same-path (lines 394-399)


class TestMoveSamePath:
    """move same-path is a no-op when source exists, NotFound when missing."""

    @pytest.mark.spec("MEM-016")
    def test_move_same_path_exists(self, mb: MemoryBackend) -> None:
        mb.write("a/b", b"data")
        mb.move("a/b", "a/b")
        assert mb.read_bytes("a/b") == b"data"

    @pytest.mark.spec("MEM-016")
    def test_move_same_path_not_found(self, mb: MemoryBackend) -> None:
        with pytest.raises(NotFound, match="Source not found"):
            mb.move("missing", "missing")

    @pytest.mark.spec("MEM-016")
    def test_move_same_path_is_directory(self, mb: MemoryBackend) -> None:
        mb.write("a/b/c", b"data")
        # "a/b" is a directory, not a file
        with pytest.raises(NotFound, match="Source not found"):
            mb.move("a/b", "a/b")


# endregion


# region: move source parent not DirNode (line 405)


class TestMoveSourceParentNotDir:
    """move raises NotFound when source parent is a file."""

    @pytest.mark.spec("MEM-016")
    def test_move_source_parent_is_file(self, mb: MemoryBackend) -> None:
        mb.write("x", b"file")
        with pytest.raises(NotFound, match="Source not found"):
            mb.move("x/child", "dst")


# endregion


# region: move destination is directory (line 417)


class TestMoveDstIsDirectory:
    """move raises InvalidPath when destination is a directory."""

    @pytest.mark.spec("MEM-016")
    def test_move_dst_is_directory(self, mb: MemoryBackend) -> None:
        mb.write("src", b"data")
        mb.write("dst/child", b"nested")
        with pytest.raises(InvalidPath, match="exists as a directory"):
            mb.move("src", "dst")


# endregion


# region: copy empty paths (lines 437, 439)


class TestCopyEmptyPaths:
    """copy raises InvalidPath for empty source or destination."""

    @pytest.mark.spec("MEM-016b")
    def test_copy_empty_src(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="Source path must not be empty"):
            mb.copy("", "dst")

    @pytest.mark.spec("MEM-016b")
    def test_copy_empty_dst(self, mb: MemoryBackend) -> None:
        with pytest.raises(InvalidPath, match="Destination path must not be empty"):
            mb.copy("src", "")


# endregion


# region: copy destination is directory (line 453)


class TestCopyDstIsDirectory:
    """copy raises InvalidPath when destination is a directory."""

    @pytest.mark.spec("MEM-016b")
    def test_copy_dst_is_directory(self, mb: MemoryBackend) -> None:
        mb.write("src", b"data")
        mb.write("dst/child", b"nested")
        with pytest.raises(InvalidPath, match="exists as a directory"):
            mb.copy("src", "dst")


# endregion


# region: write with BinaryIO content


class TestWriteWithStream:
    """write accepts BinaryIO content (exercises content.read() branch)."""

    @pytest.mark.spec("MEM-012")
    def test_write_binaryio(self, mb: MemoryBackend) -> None:
        stream = io.BytesIO(b"streamed")
        mb.write("file.txt", stream)
        assert mb.read_bytes("file.txt") == b"streamed"


# endregion
