"""Metadata conformance: get_file_info, get_folder_info, aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import NotFound
from remote_store._models import FileInfo, FolderInfo
from tests.backends.conformance._helpers import _seed
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendMetadata:
    """BE-016 through BE-017: metadata operations."""

    @pytest.mark.spec("BE-016")
    def test_get_file_info(self, backend: Backend) -> None:
        backend.write("info.txt", b"hello world")
        fi = backend.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "info.txt"
        assert fi.size == 11

    @pytest.mark.spec("BE-017")
    @pytest.mark.spec("AZ-024")
    def test_get_folder_info(self, backend: Backend) -> None:
        _seed(backend, {"fi/a.txt": b"aaa", "fi/b.txt": b"bb"})
        fi = backend.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_excludes_subdirs(self, backend: Backend) -> None:
        _seed(backend, {"mix/a.txt": b"aaa", "mix/sub/b.txt": b"bb"})
        fi = backend.get_folder_info("mix")
        # ChildFiles counts all files recursively under path, including sub/b.txt.
        assert fi.file_count == 2
        assert fi.total_size == 5
        # DirEntry nodes (mix/sub/) must not be counted.

    @pytest.mark.spec("BE-016")
    def test_file_info_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.get_file_info("missing_target")

    @pytest.mark.spec("BE-017")
    def test_folder_info_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.get_folder_info("missing_target")


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestGetFolderInfoAggregates:
    """BackendContract.GetFolderInfo aggregate postconditions (ID-134).

    Dafny: IsDir(path) ==>
      r.Ok?
      && r.value.file_count == |ChildFiles(fs, path)|
      && r.value.total_size == SumSizes(fs, ChildFiles(fs, path))

    Proved in MemoryBackend.dfy via ghost set tracking and SumSizesAddOne
    induction at each loop iteration.
    """

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_file_count_and_total_size(self, backend: Backend) -> None:
        """IsDir ==> file_count == |ChildFiles|, total_size == SumSizes."""
        _seed(backend, {"gfa/a.txt": b"aaa", "gfa/b.txt": b"bb"})
        fi = backend.get_folder_info("gfa")
        assert fi.file_count == 2
        assert fi.total_size == 5

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_counts_recursive_children(self, backend: Backend) -> None:
        """ChildFiles is the full recursive set: subdirectory files are counted."""
        _seed(backend, {"gfr/a.txt": b"aaa", "gfr/sub/b.txt": b"bb"})
        fi = backend.get_folder_info("gfr")
        assert fi.file_count == 2
        assert fi.total_size == 5
