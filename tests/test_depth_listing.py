"""Tests for depth-limited listing.

Covers spec 037-depth-limited-listing.md (DEPTH-001, DEPTH-002).
"""

from __future__ import annotations

import pytest

from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> Store:
    """Store with a nested directory structure for depth tests."""
    s = Store(backend=MemoryBackend())
    # depth 0
    s.write("d/a.txt", b"a")
    # depth 1
    s.write("d/sub1/b.txt", b"b")
    s.write("d/sub2/c.txt", b"c")
    # depth 2
    s.write("d/sub1/deep/d.txt", b"d")
    # depth 3
    s.write("d/sub1/deep/deeper/e.txt", b"e")
    return s


@pytest.fixture
def root_store() -> Store:
    """Store with files at root for empty-path tests."""
    s = Store(backend=MemoryBackend())
    s.write("root.txt", b"r")
    s.write("lvl1/one.txt", b"1")
    s.write("lvl1/lvl2/two.txt", b"2")
    s.write("lvl1/lvl2/lvl3/three.txt", b"3")
    return s


# ---------------------------------------------------------------------------
# DEPTH-001: list_files(max_depth=N)
# ---------------------------------------------------------------------------


class TestListFilesMaxDepth:
    """DEPTH-001: list_files with max_depth parameter."""

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_none_default(self, store: Store) -> None:
        """max_depth=None preserves existing behavior."""
        non_recursive = sorted(str(f.path) for f in store.list_files("d"))
        assert non_recursive == ["d/a.txt"]

        recursive = sorted(str(f.path) for f in store.list_files("d", recursive=True))
        assert len(recursive) == 5

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_zero(self, store: Store) -> None:
        """max_depth=0 returns only files directly in path."""
        files = sorted(str(f.path) for f in store.list_files("d", max_depth=0))
        assert files == ["d/a.txt"]

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_one(self, store: Store) -> None:
        """max_depth=1 returns files in path and its immediate subfolders."""
        files = sorted(str(f.path) for f in store.list_files("d", max_depth=1))
        assert files == ["d/a.txt", "d/sub1/b.txt", "d/sub2/c.txt"]

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_two(self, store: Store) -> None:
        """max_depth=2 returns files up to 2 levels deep."""
        files = sorted(str(f.path) for f in store.list_files("d", max_depth=2))
        assert files == ["d/a.txt", "d/sub1/b.txt", "d/sub1/deep/d.txt", "d/sub2/c.txt"]

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_exceeds_tree(self, store: Store) -> None:
        """max_depth larger than tree depth returns all files."""
        files = sorted(str(f.path) for f in store.list_files("d", max_depth=100))
        assert len(files) == 5

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_negative_raises(self, store: Store) -> None:
        """Negative max_depth raises ValueError."""
        with pytest.raises(ValueError, match="max_depth must be >= 0"):
            list(store.list_files("d", max_depth=-1))

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_ignores_recursive(self, store: Store) -> None:
        """When max_depth is set, recursive is ignored."""
        with_recursive = sorted(str(f.path) for f in store.list_files("d", recursive=False, max_depth=1))
        without_recursive = sorted(str(f.path) for f in store.list_files("d", recursive=True, max_depth=1))
        assert with_recursive == without_recursive
        assert len(with_recursive) == 3

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_with_pattern(self, store: Store) -> None:
        """max_depth composes with pattern filtering."""
        # depth 0 + 1, but only .txt matching "b*"
        files = sorted(str(f.path) for f in store.list_files("d", max_depth=1, pattern="b*"))
        assert files == ["d/sub1/b.txt"]

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_empty_path(self, root_store: Store) -> None:
        """max_depth works with empty path (store root)."""
        files = sorted(str(f.path) for f in root_store.list_files("", max_depth=0))
        assert files == ["root.txt"]

        files = sorted(str(f.path) for f in root_store.list_files("", max_depth=1))
        assert files == ["lvl1/one.txt", "root.txt"]

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_child_store(self) -> None:
        """max_depth works correctly with child stores (path rebasing)."""
        parent = Store(backend=MemoryBackend())
        parent.write("root/sub/a.txt", b"a")
        parent.write("root/sub/deep/b.txt", b"b")
        child = parent.child("root")
        files = sorted(str(f.path) for f in child.list_files("sub", max_depth=0))
        assert files == ["sub/a.txt"]


# ---------------------------------------------------------------------------
# DEPTH-002: list_folders(max_depth=N)
# ---------------------------------------------------------------------------


class TestListFoldersMaxDepth:
    """DEPTH-002: list_folders with max_depth parameter."""

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_none_default(self, store: Store) -> None:
        """max_depth=None returns immediate children only."""
        folders = sorted(f.name for f in store.list_folders("d"))
        assert folders == ["sub1", "sub2"]

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_zero(self, store: Store) -> None:
        """max_depth=0 returns immediate children (same as default)."""
        folders = sorted(f.name for f in store.list_folders("d", max_depth=0))
        assert folders == ["sub1", "sub2"]

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_one(self, store: Store) -> None:
        """max_depth=1 returns children and grandchildren."""
        folders = sorted(str(f.path) for f in store.list_folders("d", max_depth=1))
        assert folders == ["d/sub1", "d/sub1/deep", "d/sub2"]

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_two(self, store: Store) -> None:
        """max_depth=2 returns folders up to 2 levels deep."""
        folders = sorted(str(f.path) for f in store.list_folders("d", max_depth=2))
        assert folders == ["d/sub1", "d/sub1/deep", "d/sub1/deep/deeper", "d/sub2"]

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_exceeds_tree(self, store: Store) -> None:
        """max_depth larger than tree returns all folders."""
        folders = sorted(str(f.path) for f in store.list_folders("d", max_depth=100))
        assert len(folders) == 4  # sub1, sub2, sub1/deep, sub1/deep/deeper

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_negative_raises(self, store: Store) -> None:
        """Negative max_depth raises ValueError."""
        with pytest.raises(ValueError, match="max_depth must be >= 0"):
            list(store.list_folders("d", max_depth=-1))

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_empty_path(self, root_store: Store) -> None:
        """max_depth works with empty path (store root)."""
        folders = sorted(f.name for f in root_store.list_folders("", max_depth=0))
        assert folders == ["lvl1"]

        folders = sorted(str(f.path) for f in root_store.list_folders("", max_depth=1))
        assert folders == ["lvl1", "lvl1/lvl2"]

    @pytest.mark.spec("DEPTH-002")
    def test_max_depth_child_store(self) -> None:
        """max_depth works correctly with child stores (path rebasing)."""
        parent = Store(backend=MemoryBackend())
        parent.write("root/sub/deep/a.txt", b"a")
        child = parent.child("root")
        folders = sorted(str(f.path) for f in child.list_folders("", max_depth=1))
        assert folders == ["sub", "sub/deep"]
