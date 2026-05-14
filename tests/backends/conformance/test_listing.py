"""Listing conformance: list_files, list_folders, iter_children, glob, completeness.

Class-level filters apply ``Capability.LIST``; tests requiring additional
capabilities (WRITE for seeding, GLOB for pattern matching) keep their
defensive ``_require()`` calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._models import FileInfo, FolderEntry
from tests.backends.conformance._helpers import _require, _seed
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(Capability.LIST, Capability.WRITE), indirect=True)
class TestBackendListing:
    """BE-014 through BE-015: listing operations."""

    @pytest.mark.spec("BE-014")
    @pytest.mark.parametrize(
        ("prefix", "seeds", "recursive", "expected_names"),
        [
            pytest.param(
                "lf",
                {"lf/a.txt": b"a", "lf/b.txt": b"b", "lf/sub/c.txt": b"c"},
                False,
                {"a.txt", "b.txt"},
                id="non_recursive",
            ),
            pytest.param(
                "lfr",
                {"lfr/a.txt": b"a", "lfr/sub/b.txt": b"b"},
                True,
                {"a.txt", "b.txt"},
                id="recursive",
            ),
        ],
    )
    def test_list_files(
        self,
        backend: Backend,
        prefix: str,
        seeds: dict[str, bytes],
        recursive: bool,
        expected_names: set[str],
    ) -> None:
        _seed(backend, seeds)
        files = list(backend.list_files(prefix, recursive=recursive))
        assert {f.name for f in files} == expected_names
        for f in files:
            assert isinstance(f, FileInfo)

    @pytest.mark.spec("BE-015")
    def test_list_folders(self, backend: Backend) -> None:
        _seed(backend, {"lfd/sub1/a.txt": b"a", "lfd/sub2/b.txt": b"b", "lfd/file.txt": b"f"})
        folders = list(backend.list_folders("lfd"))
        assert all(isinstance(f, FolderEntry) for f in folders)
        assert {f.name for f in folders} == {"sub1", "sub2"}
        assert {str(f.path) for f in folders} == {"lfd/sub1", "lfd/sub2"}


@pytest.mark.parametrize("backend", fixture_params(Capability.LIST), indirect=True)
class TestBackendIterChildren:
    """ITER-004, ITER-005: iter_children() combined file and folder listing."""

    @pytest.mark.spec("ITER-004")
    def test_iter_children(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        _seed(backend, {"ic/a.txt": b"a", "ic/b.txt": b"b", "ic/sub/c.txt": b"c"})
        children = list(backend.iter_children("ic"))
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        assert {f.name for f in folders} == {"sub"}
        assert {str(f.path) for f in folders} == {"ic/sub"}

    @pytest.mark.spec("ITER-004")
    def test_iter_children_empty_or_nonexistent(self, backend: Backend) -> None:
        assert list(backend.iter_children("nonexistent")) == []

    @pytest.mark.spec("ITER-004")
    @pytest.mark.parametrize(
        ("prefix", "file_path", "expect_files", "expect_folders"),
        [
            pytest.param("icf", "icf/x.txt", {"x.txt"}, set(), id="only_files"),
            pytest.param("ico", "ico/sub/y.txt", set(), {"sub"}, id="only_folders"),
        ],
    )
    def test_iter_children_single_type(
        self,
        backend: Backend,
        prefix: str,
        file_path: str,
        expect_files: set[str],
        expect_folders: set[str],
    ) -> None:
        _require(backend, Capability.WRITE)
        backend.write(file_path, b"x")
        children = list(backend.iter_children(prefix))
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == expect_files
        assert {f.name for f in folders} == expect_folders


@pytest.mark.parametrize("backend", fixture_params(Capability.GLOB, Capability.WRITE), indirect=True)
class TestBackendGlob:
    """GLOB-004/018/019/020: glob conformance across backends."""

    @pytest.mark.spec("GLOB-018")
    @pytest.mark.parametrize(
        ("seeds", "pattern", "expected"),
        [
            pytest.param(
                {"g/a.txt": b"a", "g/b.csv": b"b"},
                "g/*.txt",
                ["g/a.txt"],
                id="basic",
            ),
            pytest.param(
                {"gr/a.txt": b"a"},
                "gr/**/*.txt",
                ["gr/a.txt"],
                id="recursive-zero-seg",
            ),
            pytest.param(
                {"gr/sub/b.txt": b"b", "gr/sub/c.csv": b"c"},
                "gr/**/*.txt",
                ["gr/sub/b.txt"],
                id="recursive-one-seg",
            ),
        ],
    )
    def test_glob(
        self,
        backend: Backend,
        request: pytest.FixtureRequest,
        seeds: dict[str, bytes],
        pattern: str,
        expected: list[str],
    ) -> None:
        _seed(backend, seeds)
        assert sorted(str(f.path) for f in backend.glob(pattern)) == expected

    @pytest.mark.spec("GLOB-004")
    def test_glob_yields_fileinfo_only(self, backend: Backend) -> None:
        _seed(
            backend,
            {
                "gf/a.txt": b"a",
                "gf/sub/b.txt": b"b",
                "gf/sub/deep/c.txt": b"c",
            },
        )
        results = list(backend.glob("gf/**/*"))
        assert len(results) == 3, f"expected 3 files from gf/**/*, got {len(results)}"
        for info in results:
            assert isinstance(info, FileInfo), f"glob returned {type(info).__name__}, expected FileInfo (GLOB-004)"
            assert str(info.path).startswith("gf/")


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.LIST, Capability.WRITE), indirect=True)
class TestListFilesCompleteness:
    """ListFiles completeness postcondition: every matching file MUST appear."""

    DEPTH_TREE: dict[str, bytes] = {
        "pc/a.txt": b"a",
        "pc/d1/b.txt": b"b",
        "pc/d1/c.txt": b"c",
        "pc/d1/d2/d.txt": b"d",
        "pc/d1/d2/d3/e.txt": b"e",
    }

    @pytest.mark.spec("BE-014")
    def test_list_files_non_recursive(self, backend: Backend) -> None:
        """recursive=false -> only immediate children (depth 0)."""
        _seed(backend, self.DEPTH_TREE)
        files = list(backend.list_files("pc", recursive=False))
        assert {f.name for f in files} == {"a.txt"}

    @pytest.mark.spec("BE-014")
    @pytest.mark.spec("DEPTH-003")
    @pytest.mark.parametrize(
        ("max_depth", "expected_names"),
        [
            pytest.param(0, {"a.txt"}, id="depth0"),
            pytest.param(1, {"a.txt", "b.txt", "c.txt"}, id="depth1"),
            pytest.param(2, {"a.txt", "b.txt", "c.txt", "d.txt"}, id="depth2"),
            pytest.param(3, {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}, id="depth3"),
        ],
    )
    def test_list_files_recursive_max_depth(self, backend: Backend, max_depth: int, expected_names: set[str]) -> None:
        """Depth filtering is inclusive (Dafny DepthFilterBoundaryInclusive).

        This is the cross-protocol DEPTH-003 invariant: the depth cutoff
        yields identical results whether a backend prunes natively or the
        Store filters client-side. Auto-parametrised over the full fixture
        registry by tests/backends/conformance/conftest.py.
        """
        _seed(backend, self.DEPTH_TREE)
        files = list(backend.list_files("pc", recursive=True, max_depth=max_depth))
        assert {f.name for f in files} == expected_names

    @pytest.mark.spec("BE-014")
    @pytest.mark.spec("DEPTH-003")
    def test_list_files_unlimited_depth(self, backend: Backend) -> None:
        """max_depth=None -> all files returned (DEPTH-003: defers to recursive)."""
        _seed(backend, self.DEPTH_TREE)
        files = list(backend.list_files("pc", recursive=True))
        assert {f.name for f in files} == {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}

    @pytest.mark.spec("BE-014")
    def test_list_files_missing_path_yields_empty(self, backend: Backend) -> None:
        """Dafny: !PathExists ==> r.value == [].  Never raises NotFound."""
        files = list(backend.list_files("ec_nonexistent_listing"))
        assert files == []

    @pytest.mark.spec("BE-014")
    def test_list_files_all_results_are_children(self, backend: Backend) -> None:
        """All returned files must be children of the listed path."""
        _seed(backend, {"lfc/a.txt": b"a", "lfc/sub/b.txt": b"b", "other/c.txt": b"c"})
        files = list(backend.list_files("lfc", recursive=True))
        for f in files:
            assert str(f.path).startswith("lfc/"), f"Unexpected path: {f.path}"


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.LIST), indirect=True)
class TestListFoldersCompleteness:
    """ListFolders completeness: every immediate child dir MUST appear."""

    @pytest.mark.spec("BE-015")
    def test_list_folders_missing_path_yields_empty(self, backend: Backend) -> None:
        """Dafny: !PathExists ==> r.value == [].  Never raises NotFound."""
        folders = list(backend.list_folders("ec_nonexistent_folders"))
        assert folders == []

    @pytest.mark.spec("BE-015")
    def test_list_folders_completeness(self, backend: Backend) -> None:
        """All immediate child directories appear."""
        _require(backend, Capability.WRITE)
        _seed(
            backend,
            {
                "lfc2/s1/a.txt": b"a",
                "lfc2/s2/b.txt": b"b",
                "lfc2/s3/c.txt": b"c",
                "lfc2/top.txt": b"t",
            },
        )
        folders = list(backend.list_folders("lfc2"))
        assert {f.name for f in folders} == {"s1", "s2", "s3"}
