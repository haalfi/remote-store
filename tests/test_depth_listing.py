"""Tests for depth-limited listing.

Covers spec 037-depth-limited-listing.md (DEPTH-001, DEPTH-002, DEPTH-003).
"""

from __future__ import annotations

import stat as stat_module
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from pathlib import Path

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

    @pytest.mark.spec("DEPTH-001")
    def test_max_depth_child_store_empty_path(self) -> None:
        """max_depth with empty path on child store exercises base_parts=0 + root_path rebasing."""
        parent = Store(backend=MemoryBackend())
        parent.write("root/a.txt", b"a")
        parent.write("root/sub/b.txt", b"b")
        parent.write("root/sub/deep/c.txt", b"c")
        child = parent.child("root")
        files = sorted(str(f.path) for f in child.list_files("", max_depth=1))
        assert files == ["a.txt", "sub/b.txt"]


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


# ---------------------------------------------------------------------------
# DEPTH-003: Backend-native max_depth optimization
# ---------------------------------------------------------------------------


def _seed_backend(backend: MemoryBackend | LocalBackend) -> None:
    """Write a nested file tree into a backend for depth tests."""
    for key, data in [
        ("d/a.txt", b"a"),
        ("d/sub1/b.txt", b"b"),
        ("d/sub2/c.txt", b"c"),
        ("d/sub1/deep/d.txt", b"d"),
        ("d/sub1/deep/deeper/e.txt", b"e"),
    ]:
        backend.write(key, data)


class TestMemoryBackendNativeDepth:
    """DEPTH-003: MemoryBackend.list_files(max_depth=N) prunes DFS."""

    @pytest.fixture
    def backend(self) -> MemoryBackend:
        b = MemoryBackend()
        _seed_backend(b)
        return b

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_none_ignores(self, backend: MemoryBackend) -> None:
        """max_depth=None preserves existing recursive behavior."""
        files = sorted(f.name for f in backend.list_files("d", recursive=True, max_depth=None))
        assert len(files) == 5

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_zero(self, backend: MemoryBackend) -> None:
        """max_depth=0 with recursive=True returns only immediate files."""
        files = sorted(f.name for f in backend.list_files("d", recursive=True, max_depth=0))
        assert files == ["a.txt"]

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_one(self, backend: MemoryBackend) -> None:
        """max_depth=1 includes files in immediate subfolders."""
        files = sorted(str(f.path) for f in backend.list_files("d", recursive=True, max_depth=1))
        assert files == ["d/a.txt", "d/sub1/b.txt", "d/sub2/c.txt"]

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_two(self, backend: MemoryBackend) -> None:
        """max_depth=2 includes files up to 2 levels deep."""
        files = sorted(str(f.path) for f in backend.list_files("d", recursive=True, max_depth=2))
        assert files == ["d/a.txt", "d/sub1/b.txt", "d/sub1/deep/d.txt", "d/sub2/c.txt"]

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_exceeds_tree(self, backend: MemoryBackend) -> None:
        """max_depth larger than tree returns all files."""
        files = sorted(f.name for f in backend.list_files("d", recursive=True, max_depth=100))
        assert len(files) == 5

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_without_recursive(self, backend: MemoryBackend) -> None:
        """max_depth has no effect when recursive=False."""
        files = sorted(f.name for f in backend.list_files("d", recursive=False, max_depth=5))
        assert files == ["a.txt"]


class TestSFTPBackendNativeDepth:
    """DEPTH-003: SFTPBackend._list_files_depth stops recursing at max_depth."""

    @staticmethod
    def _make_attr(filename: str, *, is_dir: bool = False) -> MagicMock:
        """Create a mock SFTPAttributes entry."""
        attr = MagicMock()
        attr.filename = filename
        mode = stat_module.S_IFDIR | 0o755 if is_dir else stat_module.S_IFREG | 0o644
        attr.st_mode = mode
        attr.st_size = 10
        attr.st_mtime = 1000000.0
        return attr

    @pytest.fixture
    def sftp_stub(self) -> MagicMock:
        """Build a mock SFTPBackend with a 3-level tree.

        Tree: d/a.txt, d/sub1/b.txt, d/sub1/deep/c.txt
        """
        from remote_store.backends._sftp import SFTPBackend

        backend = MagicMock(spec=SFTPBackend)
        backend.name = "sftp"
        backend._base_path = "/"

        # Bind the real methods so they use the mock's _sftp
        backend._sftp_path = SFTPBackend._sftp_path.__get__(backend)
        backend._stat_to_fileinfo = SFTPBackend._stat_to_fileinfo.__get__(backend)
        backend._list_files_depth = SFTPBackend._list_files_depth.__get__(backend)
        backend.list_files = SFTPBackend.list_files.__get__(backend)

        mk = self._make_attr

        def listdir_attr(path: str) -> list[MagicMock]:
            tree: dict[str, list[MagicMock]] = {
                "/d": [mk("a.txt"), mk("sub1", is_dir=True)],
                "/d/sub1": [mk("b.txt"), mk("deep", is_dir=True)],
                "/d/sub1/deep": [mk("c.txt")],
            }
            if path not in tree:
                raise OSError("not found")
            return tree[path]

        backend._sftp = MagicMock()
        backend._sftp.listdir_attr = MagicMock(side_effect=listdir_attr)
        return backend

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_zero_no_subdirs(self, sftp_stub: MagicMock) -> None:
        """max_depth=0 returns only files in 'd', no recursive calls."""
        files = list(sftp_stub.list_files("d", recursive=True, max_depth=0))
        assert [f.name for f in files] == ["a.txt"]
        # Only the root directory should be listed
        assert sftp_stub._sftp.listdir_attr.call_count == 1

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_one_stops_at_sub1(self, sftp_stub: MagicMock) -> None:
        """max_depth=1 lists d/ and d/sub1/ but not d/sub1/deep/."""
        files = sorted(f.name for f in sftp_stub.list_files("d", recursive=True, max_depth=1))
        assert files == ["a.txt", "b.txt"]
        # d/ and d/sub1/ listed, but d/sub1/deep/ skipped
        assert sftp_stub._sftp.listdir_attr.call_count == 2

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_none_lists_all(self, sftp_stub: MagicMock) -> None:
        """max_depth=None recurses fully."""
        files = sorted(f.name for f in sftp_stub.list_files("d", recursive=True, max_depth=None))
        assert files == ["a.txt", "b.txt", "c.txt"]
        assert sftp_stub._sftp.listdir_attr.call_count == 3

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_without_recursive(self, sftp_stub: MagicMock) -> None:
        """max_depth has no effect when recursive=False."""
        files = list(sftp_stub.list_files("d", recursive=False, max_depth=5))
        assert [f.name for f in files] == ["a.txt"]
        assert sftp_stub._sftp.listdir_attr.call_count == 1


@pytest.mark.os_sensitive
class TestLocalBackendNativeDepth:
    """DEPTH-003: LocalBackend.list_files(max_depth=N) uses os.walk depth cutoff."""

    @pytest.fixture
    def backend(self, tmp_path: Path) -> LocalBackend:
        b = LocalBackend(root=str(tmp_path))
        _seed_backend(b)
        return b

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_none_ignores(self, backend: LocalBackend) -> None:
        """max_depth=None preserves existing recursive behavior."""
        files = sorted(f.name for f in backend.list_files("d", recursive=True, max_depth=None))
        assert len(files) == 5

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_zero(self, backend: LocalBackend) -> None:
        """max_depth=0 with recursive=True returns only immediate files."""
        files = sorted(f.name for f in backend.list_files("d", recursive=True, max_depth=0))
        assert files == ["a.txt"]

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_one(self, backend: LocalBackend) -> None:
        """max_depth=1 includes files in immediate subfolders."""
        files = sorted(str(f.path) for f in backend.list_files("d", recursive=True, max_depth=1))
        assert files == ["d/a.txt", "d/sub1/b.txt", "d/sub2/c.txt"]

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_two(self, backend: LocalBackend) -> None:
        """max_depth=2 includes files up to 2 levels deep."""
        files = sorted(str(f.path) for f in backend.list_files("d", recursive=True, max_depth=2))
        assert files == ["d/a.txt", "d/sub1/b.txt", "d/sub1/deep/d.txt", "d/sub2/c.txt"]

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_exceeds_tree(self, backend: LocalBackend) -> None:
        """max_depth larger than tree returns all files."""
        files = sorted(f.name for f in backend.list_files("d", recursive=True, max_depth=100))
        assert len(files) == 5

    @pytest.mark.spec("DEPTH-003")
    def test_max_depth_without_recursive(self, backend: LocalBackend) -> None:
        """max_depth has no effect when recursive=False."""
        files = sorted(f.name for f in backend.list_files("d", recursive=False, max_depth=5))
        assert files == ["a.txt"]
