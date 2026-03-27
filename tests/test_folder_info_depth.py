"""Tests for non-recursive get_folder_info optimization.

Covers spec 038-nonrecursive-folder-info.md (FOLDERINFO-001, FOLDERINFO-002).
"""

from __future__ import annotations

import pytest

from remote_store._models import FolderInfo
from remote_store._path import RemotePath
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> Store:
    """Store with a nested directory structure for depth tests."""
    s = Store(backend=MemoryBackend())
    # depth 0: 2 files, 5 bytes
    s.write("d/a.txt", b"aaa")  # 3 bytes
    s.write("d/b.txt", b"bb")  # 2 bytes
    # depth 1: 2 files, 3 bytes
    s.write("d/sub1/c.txt", b"c")  # 1 byte
    s.write("d/sub2/d.txt", b"dd")  # 2 bytes
    # depth 2: 1 file, 4 bytes
    s.write("d/sub1/deep/e.txt", b"eeee")  # 4 bytes
    return s


# ---------------------------------------------------------------------------
# FOLDERINFO-001: get_folder_info(max_depth=N)
# ---------------------------------------------------------------------------


class TestGetFolderInfoMaxDepth:
    """FOLDERINFO-001: get_folder_info with max_depth parameter."""

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_none_default(self, store: Store) -> None:
        """max_depth=None delegates to backend (full recursive)."""
        fi = store.get_folder_info("d")
        assert fi.file_count == 5
        assert fi.total_size == 12

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_zero(self, store: Store) -> None:
        """max_depth=0 aggregates only files directly in path."""
        fi = store.get_folder_info("d", max_depth=0)
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_one(self, store: Store) -> None:
        """max_depth=1 includes files in path and its immediate subfolders."""
        fi = store.get_folder_info("d", max_depth=1)
        assert fi.file_count == 4
        assert fi.total_size == 8

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_two(self, store: Store) -> None:
        """max_depth=2 includes all files (tree only 2 levels deep)."""
        fi = store.get_folder_info("d", max_depth=2)
        assert fi.file_count == 5
        assert fi.total_size == 12

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_exceeds_tree(self, store: Store) -> None:
        """max_depth larger than tree depth returns all files."""
        fi = store.get_folder_info("d", max_depth=100)
        assert fi.file_count == 5
        assert fi.total_size == 12

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_negative_raises(self, store: Store) -> None:
        """Negative max_depth raises ValueError."""
        with pytest.raises(ValueError, match="max_depth must be >= 0"):
            store.get_folder_info("d", max_depth=-1)

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_path_set(self, store: Store) -> None:
        """Returned FolderInfo has the correct path."""
        fi = store.get_folder_info("d", max_depth=0)
        assert str(fi.path) == "d"

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_modified_at(self, store: Store) -> None:
        """modified_at reflects the latest file within the depth limit."""
        fi_shallow = store.get_folder_info("d", max_depth=0)
        fi_deep = store.get_folder_info("d")
        # Both should have a modified_at (files exist at both depths)
        assert fi_shallow.modified_at is not None
        assert fi_deep.modified_at is not None

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_empty_folder(self) -> None:
        """max_depth on a folder with no files at that depth returns zero counts."""
        s = Store(backend=MemoryBackend())
        s.write("empty/sub/file.txt", b"x")
        fi = s.get_folder_info("empty", max_depth=0)
        assert fi.file_count == 0
        assert fi.total_size == 0
        assert fi.modified_at is None

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_not_found(self, store: Store) -> None:
        """max_depth on a non-existent folder raises NotFound."""
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            store.get_folder_info("nonexistent", max_depth=0)

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_root_path(self) -> None:
        """max_depth works with empty path (store root)."""
        s = Store(backend=MemoryBackend())
        s.write("root.txt", b"r")
        s.write("sub/nested.txt", b"nn")
        fi = s.get_folder_info("", max_depth=0)
        assert fi.file_count == 1
        assert fi.total_size == 1
        assert fi.path is RemotePath.ROOT

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_child_store(self) -> None:
        """max_depth works correctly with child stores."""
        parent = Store(backend=MemoryBackend())
        parent.write("root/a.txt", b"aaa")
        parent.write("root/sub/b.txt", b"bb")
        child = parent.child("root")
        fi = child.get_folder_info("", max_depth=0)
        assert fi.file_count == 1
        assert fi.total_size == 3

    @pytest.mark.spec("FOLDERINFO-001")
    def test_max_depth_consistency_with_full_recursive(self, store: Store) -> None:
        """max_depth=large should match full recursive results."""
        fi_full = store.get_folder_info("d")
        fi_deep = store.get_folder_info("d", max_depth=100)
        assert fi_full.file_count == fi_deep.file_count
        assert fi_full.total_size == fi_deep.total_size


# ---------------------------------------------------------------------------
# FOLDERINFO-002: Proxy / extension pass-through
# ---------------------------------------------------------------------------


class TestGetFolderInfoProxy:
    """FOLDERINFO-002: Proxy stores forward max_depth."""

    @pytest.mark.spec("FOLDERINFO-002")
    def test_cached_store_forwards_max_depth(self) -> None:
        """CachedStore forwards max_depth and caches by (path, max_depth)."""
        from remote_store.ext.cache import cache

        inner = Store(backend=MemoryBackend())
        inner.write("d/a.txt", b"aaa")
        inner.write("d/sub/b.txt", b"bb")
        cached = cache(inner, ttl=60.0)

        fi_shallow = cached.get_folder_info("d", max_depth=0)
        fi_deep = cached.get_folder_info("d")

        assert fi_shallow.file_count == 1
        assert fi_deep.file_count == 2

        # Verify caching: different max_depth = different cache entries
        fi_shallow2 = cached.get_folder_info("d", max_depth=0)
        assert fi_shallow2.file_count == 1

    @pytest.mark.spec("FOLDERINFO-002")
    def test_observed_store_forwards_max_depth(self) -> None:
        """ObservedStore forwards max_depth and records it in event details."""
        from remote_store.ext.observe import StoreEvent, observe

        events: list[StoreEvent] = []
        inner = Store(backend=MemoryBackend())
        inner.write("d/a.txt", b"aaa")
        inner.write("d/sub/b.txt", b"bb")
        observed = observe(inner, on_any=events.append)

        fi = observed.get_folder_info("d", max_depth=0)
        assert fi.file_count == 1
        assert len(events) == 1
        assert events[0].metadata.get("max_depth") == 0
