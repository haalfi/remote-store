"""Listing benchmarks — flat, recursive, and directory-scale.

Comparative tests use ``bench_target`` (flat listing).
Directory-scale tests stay ``bench_backend``-only (complex multi-op).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from benchmarks.targets._protocol import BenchTarget
    from remote_store._backend import Backend


# ---------------------------------------------------------------------------
# Comparative: flat and recursive listing (50 files)
# ---------------------------------------------------------------------------


class TestListPerformance:
    """Comparative listing speed (bench_target)."""

    @pytest.fixture(autouse=True)
    def _populate(self, bench_target: BenchTarget) -> None:
        self._dir = f"listbench/{uuid.uuid4().hex[:8]}"
        for i in range(50):
            bench_target.write(f"{self._dir}/file_{i:04d}.txt", b"x")

    def test_list_files(self, bench_target: BenchTarget, benchmark: Any) -> None:
        def _list() -> None:
            bench_target.list_files(self._dir)

        benchmark(_list)


# ---------------------------------------------------------------------------
# Remote-store only: directory-scale operations
# ---------------------------------------------------------------------------


class TestDirectoryScalePerformance:
    """Measure directory operations at scale — remote-store only.

    The hierarchy has 3 levels of nesting with 200 files total::

        scale/{tag}/lvl0_NN.txt            (20 files)
        scale/{tag}/sub_N/lvl1_NN.txt      (5 dirs x 20 files = 100 files)
        scale/{tag}/sub_N/deep/lvl2_NN.txt (5 dirs x 1 deep x 16 files = 80 files)

    Total: 200 files across 11 folders.
    """

    @pytest.fixture(autouse=True)
    def _populate_hierarchy(self, bench_backend: Backend) -> None:
        self._root = f"scale/{uuid.uuid4().hex[:8]}"
        # Level 0: 20 files in root
        for i in range(20):
            bench_backend.write(f"{self._root}/lvl0_{i:02d}.txt", b"x")
        # Level 1: 5 subdirectories x 20 files each
        for d in range(5):
            for i in range(20):
                bench_backend.write(f"{self._root}/sub_{d}/lvl1_{i:02d}.txt", b"x")
            # Level 2: 1 nested dir x 16 files
            for i in range(16):
                bench_backend.write(f"{self._root}/sub_{d}/deep/lvl2_{i:02d}.txt", b"x")

    def test_list_200_files_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        """List all 200 files recursively from root."""

        def _list() -> None:
            files = list(bench_backend.list_files(self._root, recursive=True))
            assert len(files) == 200

        benchmark(_list)

    def test_list_200_files_non_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        """List only top-level files (20 of 200)."""

        def _list() -> None:
            files = list(bench_backend.list_files(self._root))
            assert len(files) == 20

        benchmark(_list)

    def test_list_folders_at_root(self, bench_backend: Backend, benchmark: Any) -> None:
        """List the 5 immediate subdirectories."""

        def _list() -> None:
            folders = list(bench_backend.list_folders(self._root))
            assert len(folders) == 5

        benchmark(_list)

    def test_exists_deep_path(self, bench_backend: Backend, benchmark: Any) -> None:
        """Check existence of a file at the deepest nesting level."""
        path = f"{self._root}/sub_2/deep/lvl2_07.txt"
        benchmark(bench_backend.exists, path)

    def test_get_folder_info_large_dir(self, bench_backend: Backend, benchmark: Any) -> None:
        """get_folder_info on the root (aggregates all 200 files)."""
        benchmark(bench_backend.get_folder_info, self._root)
