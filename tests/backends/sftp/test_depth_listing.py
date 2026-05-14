"""SFTPBackend native depth-limited listing -- DEPTH-003.

The cross-protocol depth-filtering invariant (`list_files(max_depth=N)`
returns files at depth <= N, identical native or client-side) is owned by
`tests/backends/conformance/test_listing.py::TestListFilesCompleteness`,
which parametrizes over the full fixture registry. This file pins what is
SFTP-specific: `SFTPBackend._list_files_depth` *prunes* the recursion --
it stops issuing `listdir_attr` round-trips once the depth limit is
reached. That pruning is observable only by counting SDK calls, so it
needs the mocked SDK client; it is not a result-correctness assertion.

Migrated from tests/test_depth_listing.py (BK-218 / BK-191 slice 3/6).
"""

from __future__ import annotations

import stat as stat_module
from unittest.mock import MagicMock

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("paramiko", reason="paramiko not installed")


class TestSFTPBackendNativeDepth:
    """DEPTH-003: SFTPBackend._list_files_depth stops recursing at max_depth."""

    @staticmethod
    def _make_attr(filename: str, *, is_dir: bool = False) -> MagicMock:
        """Create a mock SFTPAttributes entry."""
        from paramiko import SFTPAttributes

        attr = MagicMock(spec=SFTPAttributes)
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

        from paramiko import SFTPClient

        backend._sftp = MagicMock(spec=SFTPClient)
        backend._sftp.listdir_attr = MagicMock(spec=SFTPClient.listdir_attr, side_effect=listdir_attr)
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
