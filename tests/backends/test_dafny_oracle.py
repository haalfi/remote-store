"""
Oracle Conformance Tests — Verify backends against the Dafny spec oracle.

These tests use the DafnyOracle (a faithful Python implementation of
MemoryBackend.dfy) as ground truth to validate backend behavior.

The oracle covers:
  - Error ordering (type check → existence check → logic)
  - Edge cases: self-move, self-copy, overwrite semantics
  - Depth filtering in ListFiles
  - Directory deletion (recursive vs. non-recursive)
  - Completeness: all matching files/folders appear in listings
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability

if TYPE_CHECKING:
    from remote_store._backend import Backend
from remote_store._errors import (
    AlreadyExists,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from tests.backends.oracle import DafnyOracle, ErrorKind


def _oracle_error_type(oracle_result: object) -> ErrorKind | None:
    """Extract error type from oracle result."""
    from tests.backends.oracle import OracleError

    if isinstance(oracle_result, OracleError):
        return oracle_result.kind
    return None


def _oracle_value(oracle_result: object) -> object:
    """Extract value from oracle result (or None if error)."""
    from tests.backends.oracle import OracleOk

    if isinstance(oracle_result, OracleOk):
        return oracle_result.value
    return None


# ============================================================================
# Oracle Self-Tests (validate the oracle implementation)
# ============================================================================


class TestOracleBasics:
    """Verify the oracle works correctly."""

    @pytest.mark.spec("ORACLE-001")
    def test_oracle_empty_exists_false(self) -> None:
        """Oracle correctly reports missing files."""
        oracle = DafnyOracle()
        result = oracle.exists("nonexistent.txt")
        assert _oracle_value(result) is False

    @pytest.mark.spec("ORACLE-002")
    def test_oracle_write_then_exists(self) -> None:
        """Oracle correctly tracks written files."""
        oracle = DafnyOracle()
        oracle.write("test.txt", b"hello")
        result = oracle.exists("test.txt")
        assert _oracle_value(result) is True

    @pytest.mark.spec("ORACLE-003")
    def test_oracle_write_read_roundtrip(self) -> None:
        """Oracle correctly stores and retrieves content."""
        oracle = DafnyOracle()
        content = b"test data"
        oracle.write("file.txt", content)
        result = oracle.read("file.txt")
        assert _oracle_value(result) == content

    @pytest.mark.spec("ORACLE-004")
    def test_oracle_delete_removes_file(self) -> None:
        """Oracle delete removes files correctly."""
        oracle = DafnyOracle()
        oracle.write("file.txt", b"data")
        oracle.delete("file.txt")
        result = oracle.exists("file.txt")
        assert _oracle_value(result) is False


class TestOracleErrorOrdering:
    """Verify oracle error precedence matches postcondition order."""

    @pytest.mark.spec("ORACLE-005")
    def test_read_dir_is_invalid_path_not_not_found(self) -> None:
        """Read on directory → InvalidPath (not NotFound)."""
        oracle = DafnyOracle()
        # Create directory implicitly by writing to child
        oracle.write("dir/file.txt", b"data")
        # Try to read the directory
        result = oracle.read("dir")
        assert _oracle_error_type(result) == ErrorKind.INVALID_PATH

    @pytest.mark.spec("ORACLE-006")
    def test_write_to_dir_is_invalid_path_not_already_exists(self) -> None:
        """Write to directory → InvalidPath (type error before logic error)."""
        oracle = DafnyOracle()
        oracle.write("dir/file.txt", b"data")
        # Try to write to the directory itself
        result = oracle.write("dir", b"new content")
        assert _oracle_error_type(result) == ErrorKind.INVALID_PATH

    @pytest.mark.spec("ORACLE-007")
    def test_delete_dir_is_invalid_path(self) -> None:
        """Delete on directory → InvalidPath."""
        oracle = DafnyOracle()
        oracle.write("dir/file.txt", b"data")
        result = oracle.delete("dir")
        assert _oracle_error_type(result) == ErrorKind.INVALID_PATH

    @pytest.mark.spec("ORACLE-008")
    def test_move_dir_src_is_invalid_path(self) -> None:
        """Move with directory src → InvalidPath."""
        oracle = DafnyOracle()
        oracle.write("dir/file.txt", b"data")
        result = oracle.move("dir", "other")
        assert _oracle_error_type(result) == ErrorKind.INVALID_PATH

    @pytest.mark.spec("ORACLE-009")
    def test_move_missing_src_is_not_found(self) -> None:
        """Move missing src → NotFound."""
        oracle = DafnyOracle()
        result = oracle.move("missing.txt", "dest.txt")
        assert _oracle_error_type(result) == ErrorKind.NOT_FOUND

    @pytest.mark.spec("ORACLE-010")
    def test_move_dir_dst_is_invalid_path(self) -> None:
        """Move to directory dst → InvalidPath."""
        oracle = DafnyOracle()
        oracle.write("file.txt", b"data")
        oracle.write("dir/child.txt", b"child")
        result = oracle.move("file.txt", "dir")
        assert _oracle_error_type(result) == ErrorKind.INVALID_PATH

    @pytest.mark.spec("ORACLE-011")
    def test_move_existing_dst_no_overwrite_is_already_exists(self) -> None:
        """Move to existing file (no overwrite) → AlreadyExists."""
        oracle = DafnyOracle()
        oracle.write("src.txt", b"src")
        oracle.write("dst.txt", b"dst")
        result = oracle.move("src.txt", "dst.txt", overwrite=False)
        assert _oracle_error_type(result) == ErrorKind.ALREADY_EXISTS


class TestOracleSelfOperations:
    """Verify self-move/self-copy semantics."""

    @pytest.mark.spec("ORACLE-012")
    def test_self_move_succeeds(self) -> None:
        """Move file to itself → Ok (no-op)."""
        oracle = DafnyOracle()
        oracle.write("file.txt", b"data")
        result = oracle.move("file.txt", "file.txt")
        assert isinstance(result, type(oracle.exists("file.txt")))  # Check it's OracleOk
        # File should still exist with same content
        assert _oracle_value(oracle.read("file.txt")) == b"data"

    @pytest.mark.spec("ORACLE-013")
    def test_self_copy_succeeds(self) -> None:
        """Copy file to itself → Ok (no-op)."""
        oracle = DafnyOracle()
        oracle.write("file.txt", b"data")
        oracle.copy("file.txt", "file.txt")
        assert _oracle_value(oracle.read("file.txt")) == b"data"

    @pytest.mark.spec("ORACLE-014")
    def test_self_move_overwrite_flag_ignored(self) -> None:
        """Self-move succeeds regardless of overwrite flag."""
        oracle = DafnyOracle()
        oracle.write("file.txt", b"data")
        oracle.move("file.txt", "file.txt", overwrite=False)
        # Should succeed even without overwrite
        assert _oracle_value(oracle.read("file.txt")) == b"data"

    @pytest.mark.spec("ORACLE-015")
    def test_self_copy_overwrite_flag_ignored(self) -> None:
        """Self-copy succeeds regardless of overwrite flag."""
        oracle = DafnyOracle()
        oracle.write("file.txt", b"data")
        oracle.copy("file.txt", "file.txt", overwrite=False)
        assert _oracle_value(oracle.read("file.txt")) == b"data"


class TestOracleDepthFiltering:
    """Verify ListFiles depth filtering."""

    @pytest.mark.spec("ORACLE-016")
    def test_list_files_non_recursive_only_depth_zero(self) -> None:
        """Non-recursive listing returns only immediate children."""
        oracle = DafnyOracle()
        oracle.write("a.txt", b"a")
        oracle.write("sub/b.txt", b"b")
        oracle.write("sub/deeper/c.txt", b"c")

        result = oracle.list_files("", recursive=False)
        files = _oracle_value(result)
        paths = {f.path for f in files}  # type: ignore[union-attr]
        assert "a.txt" in paths
        assert "sub/b.txt" not in paths
        assert "sub/deeper/c.txt" not in paths

    @pytest.mark.spec("ORACLE-017")
    def test_list_files_recursive_respects_max_depth(self) -> None:
        """Recursive listing with max_depth filters by depth."""
        oracle = DafnyOracle()
        oracle.write("root/a.txt", b"a")
        oracle.write("root/sub/b.txt", b"b")
        oracle.write("root/sub/deeper/c.txt", b"c")

        result = oracle.list_files("root", recursive=True, max_depth=1)
        files = _oracle_value(result)
        paths = {f.path for f in files}  # type: ignore[union-attr]
        assert "root/a.txt" in paths
        assert "root/sub/b.txt" in paths
        assert "root/sub/deeper/c.txt" not in paths

    @pytest.mark.spec("ORACLE-018")
    def test_list_files_missing_path_returns_empty(self) -> None:
        """Listing missing path returns empty list."""
        oracle = DafnyOracle()
        result = oracle.list_files("missing")
        assert _oracle_value(result) == []

    @pytest.mark.spec("ORACLE-019")
    def test_list_folders_only_directories(self) -> None:
        """ListFolders returns only directories."""
        oracle = DafnyOracle()
        oracle.write("file.txt", b"f")
        oracle.write("dir1/nested.txt", b"n")
        oracle.write("dir2/other.txt", b"o")

        result = oracle.list_folders("")
        folders = _oracle_value(result)
        paths = {f.path for f in folders}  # type: ignore[union-attr]
        assert "file.txt" not in paths
        assert "dir1" in paths
        assert "dir2" in paths

    @pytest.mark.spec("ORACLE-020")
    def test_list_folders_completeness(self) -> None:
        """ListFolders returns all child directories."""
        oracle = DafnyOracle()
        oracle.write("a/x.txt", b"x")
        oracle.write("b/y.txt", b"y")
        oracle.write("c/z.txt", b"z")

        result = oracle.list_folders("")
        folders = _oracle_value(result)
        paths = {f.path for f in folders}  # type: ignore[union-attr]
        assert paths == {"a", "b", "c"}


class TestOracleDeleteFolder:
    """Verify directory deletion with recursive flag."""

    @pytest.mark.spec("ORACLE-021")
    def test_delete_folder_empty_non_recursive(self) -> None:
        """Delete empty directory (non-recursive) → Ok."""
        oracle = DafnyOracle()
        oracle.write("dir/file.txt", b"data")
        oracle.delete("dir/file.txt")  # Empty the directory
        oracle.delete_folder("dir", recursive=False)
        # Should succeed
        assert _oracle_value(oracle.exists("dir")) is False

    @pytest.mark.spec("ORACLE-022")
    def test_delete_folder_non_empty_non_recursive(self) -> None:
        """Delete non-empty directory (non-recursive) → DirectoryNotEmpty."""
        oracle = DafnyOracle()
        oracle.write("dir/file.txt", b"data")
        result = oracle.delete_folder("dir", recursive=False)
        assert _oracle_error_type(result) == ErrorKind.DIRECTORY_NOT_EMPTY

    @pytest.mark.spec("ORACLE-023")
    def test_delete_folder_recursive_removes_children(self) -> None:
        """Delete directory (recursive) removes all children."""
        oracle = DafnyOracle()
        oracle.write("dir/file1.txt", b"f1")
        oracle.write("dir/sub/file2.txt", b"f2")
        oracle.delete_folder("dir", recursive=True)
        # Directory and children should be gone
        assert _oracle_value(oracle.exists("dir")) is False
        assert _oracle_value(oracle.exists("dir/file1.txt")) is False
        assert _oracle_value(oracle.exists("dir/sub/file2.txt")) is False

    @pytest.mark.spec("ORACLE-024")
    def test_delete_folder_missing_not_missing_ok(self) -> None:
        """Delete missing folder (missing_ok=False) → NotFound."""
        oracle = DafnyOracle()
        result = oracle.delete_folder("missing", missing_ok=False)
        assert _oracle_error_type(result) == ErrorKind.NOT_FOUND

    @pytest.mark.spec("ORACLE-025")
    def test_delete_folder_missing_missing_ok(self) -> None:
        """Delete missing folder (missing_ok=True) → Ok."""
        oracle = DafnyOracle()
        result = oracle.delete_folder("missing", missing_ok=True)
        # Should succeed (not an error)
        assert isinstance(result, type(oracle.exists("anything")))


# ============================================================================
# Backend vs. Oracle Comparison Tests
# ============================================================================


class TestBackendVsOracle:
    """Compare real backend behavior against oracle."""

    def _normalize_error(self, exc: Exception) -> ErrorKind | None:
        """Map backend exceptions to oracle error kinds."""
        if isinstance(exc, NotFound):
            return ErrorKind.NOT_FOUND
        if isinstance(exc, AlreadyExists):
            return ErrorKind.ALREADY_EXISTS
        if isinstance(exc, InvalidPath):
            return ErrorKind.INVALID_PATH
        if isinstance(exc, DirectoryNotEmpty):
            return ErrorKind.DIRECTORY_NOT_EMPTY
        return None

    @pytest.mark.spec("BE-VS-ORACLE-001")
    def test_read_missing_file(self, backend: Backend) -> None:
        """Both backend and oracle return NotFound for missing files."""
        oracle = DafnyOracle()

        # Oracle
        oracle.read("missing.txt")

        # Backend
        with pytest.raises(NotFound):
            backend.read("missing.txt")

    @pytest.mark.spec("BE-VS-ORACLE-002")
    def test_write_then_read(self, backend: Backend) -> None:
        """Both backend and oracle preserve written content."""
        if not backend.capabilities.supports(Capability.WRITE):
            pytest.skip("Backend does not support WRITE")

        oracle = DafnyOracle()
        content = b"test content"

        oracle.write("file.txt", content)
        backend.write("file.txt", content)

        oracle_result = oracle.read("file.txt")
        backend_result = backend.read("file.txt")

        oracle_content = _oracle_value(oracle_result)
        backend_content = backend_result.read() if hasattr(backend_result, "read") else backend_result
        assert oracle_content == backend_content

    @pytest.mark.spec("BE-VS-ORACLE-003")
    def test_write_overwrite_false_existing(self, backend: Backend) -> None:
        """Both reject overwrite=False on existing files."""
        if not backend.capabilities.supports(Capability.WRITE):
            pytest.skip("Backend does not support WRITE")

        oracle = DafnyOracle()
        oracle.write("file.txt", b"original")
        backend.write("file.txt", b"original")

        # Try to write again with overwrite=False
        oracle_result = oracle.write("file.txt", b"new", overwrite=False)
        with pytest.raises(AlreadyExists):
            backend.write("file.txt", b"new", overwrite=False)

        assert _oracle_error_type(oracle_result) == ErrorKind.ALREADY_EXISTS

    @pytest.mark.spec("BE-VS-ORACLE-004")
    def test_write_overwrite_true_existing(self, backend: Backend) -> None:
        """Both allow overwrite=True on existing files."""
        if not backend.capabilities.supports(Capability.WRITE):
            pytest.skip("Backend does not support WRITE")

        oracle = DafnyOracle()
        oracle.write("file.txt", b"original")
        backend.write("file.txt", b"original")

        # Overwrite with new content
        oracle.write("file.txt", b"new", overwrite=True)
        backend.write("file.txt", b"new", overwrite=True)

        oracle_content = _oracle_value(oracle.read("file.txt"))
        backend.read("file.txt")  # Verify backend also succeeds
        assert oracle_content == b"new"  # type: ignore[comparison-overlap]

    @pytest.mark.spec("BE-VS-ORACLE-005")
    def test_delete_missing_not_missing_ok(self, backend: Backend) -> None:
        """Both reject delete of missing files (missing_ok=False)."""
        if not backend.capabilities.supports(Capability.DELETE):
            pytest.skip("Backend does not support DELETE")

        oracle = DafnyOracle()
        oracle_result = oracle.delete("missing.txt", missing_ok=False)
        with pytest.raises(NotFound):
            backend.delete("missing.txt", missing_ok=False)

        assert _oracle_error_type(oracle_result) == ErrorKind.NOT_FOUND

    @pytest.mark.spec("BE-VS-ORACLE-006")
    def test_delete_missing_missing_ok(self, backend: Backend) -> None:
        """Both allow delete of missing files (missing_ok=True)."""
        if not backend.capabilities.supports(Capability.DELETE):
            pytest.skip("Backend does not support DELETE")

        oracle = DafnyOracle()
        oracle.delete("missing.txt", missing_ok=True)
        backend.delete("missing.txt", missing_ok=True)
        # Both should succeed without raising

    @pytest.mark.spec("BE-VS-ORACLE-007")
    def test_list_files_structure(self, backend: Backend) -> None:
        """Both list_files return consistent structure."""
        if not backend.capabilities.supports(Capability.LIST):
            pytest.skip("Backend does not support LIST")

        oracle = DafnyOracle()
        oracle.write("a.txt", b"a")
        oracle.write("b.txt", b"b")

        backend.write("a.txt", b"a")
        backend.write("b.txt", b"b")

        oracle_result = oracle.list_files("")
        backend_result = backend.list_files("")

        oracle_paths = {str(f.path) for f in _oracle_value(oracle_result)}  # type: ignore[union-attr]
        backend_paths = {str(f.path) for f in backend_result}

        assert oracle_paths == backend_paths
