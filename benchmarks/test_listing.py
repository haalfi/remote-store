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
# Comparative: flat listing (50 files)
# ---------------------------------------------------------------------------


class TestListPerformance:
    """Comparative listing speed with 50 files (bench_target)."""

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
# Comparative: large listing (1000 files)
# ---------------------------------------------------------------------------


class TestListPerformanceLarge:
    """Comparative listing speed with 1000 files (bench_target)."""

    @pytest.fixture(autouse=True)
    def _populate(self, bench_target: BenchTarget) -> None:
        self._dir = f"listlarge/{uuid.uuid4().hex[:8]}"
        for i in range(1000):
            bench_target.write(f"{self._dir}/file_{i:06d}.txt", b"x")

    def test_list_1000_files(self, bench_target: BenchTarget, benchmark: Any) -> None:
        def _list() -> None:
            bench_target.list_files(self._dir)

        benchmark(_list)


# ---------------------------------------------------------------------------
# Remote-store only: 10k listing (slow)
# ---------------------------------------------------------------------------


class TestListPerformance10k:
    """Listing 10k files -- for cloud runs."""

    @pytest.fixture(autouse=True)
    def _populate(self, bench_backend: Backend) -> None:
        self._dir = f"list10k/{uuid.uuid4().hex[:8]}"
        for i in range(10_000):
            bench_backend.write(f"{self._dir}/file_{i:06d}.txt", b"x")

    @pytest.mark.full
    def test_list_10k_files(self, bench_backend: Backend, benchmark: Any) -> None:
        """List 10,000 files recursively."""

        def _list() -> None:
            files = list(bench_backend.list_files(self._dir, recursive=True))
            assert len(files) == 10_000

        benchmark.pedantic(_list, rounds=3, warmup_rounds=0)


# ---------------------------------------------------------------------------
# Remote-store only: deep hierarchy (5 levels, branching factor 5, 1562 files)
# ---------------------------------------------------------------------------


class TestDeepHierarchyPerformance:
    """List files in a deep hierarchy: 5 levels, branching factor 5, 1562 files."""

    @pytest.fixture(autouse=True)
    def _populate_deep(self, bench_backend: Backend) -> None:
        self._root = f"deep/{uuid.uuid4().hex[:8]}"
        self._count = 0
        self._build_tree(bench_backend, self._root, depth=5, breadth=5)
        self._expected = self._count

    def _build_tree(self, backend: Backend, prefix: str, depth: int, breadth: int) -> None:
        if depth == 0:
            return
        # Write 2 files at this level
        for i in range(2):
            backend.write(f"{prefix}/f_{i}.txt", b"x")
            self._count += 1
        # Recurse into subdirectories
        for d in range(breadth):
            self._build_tree(backend, f"{prefix}/d{d}", depth - 1, breadth)

    @pytest.mark.standard
    def test_list_deep_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        """Recursively list all files in the deep hierarchy."""

        def _list() -> None:
            files = list(bench_backend.list_files(self._root, recursive=True))
            assert len(files) == self._expected

        benchmark.pedantic(_list, rounds=3, warmup_rounds=0)


# ---------------------------------------------------------------------------
# Remote-store only: per-folder stats (real-world use case)
# ---------------------------------------------------------------------------


class TestPerFolderStats:
    """Iterate list_folders + get_folder_info per subfolder -- the real-world
    scenario of summing files/sizes per hierarchy level."""

    @pytest.fixture(autouse=True)
    def _populate_hierarchy(self, bench_backend: Backend) -> None:
        self._root = f"folderstats/{uuid.uuid4().hex[:8]}"
        # Create 10 folders with varying file counts
        for d in range(10):
            for i in range(d * 5 + 5):  # 5, 10, 15, ... 50 files
                bench_backend.write(f"{self._root}/folder_{d:02d}/file_{i:04d}.txt", b"x" * 100)

    def test_per_folder_stats(self, bench_backend: Backend, benchmark: Any) -> None:
        """Iterate folders and gather info for each."""

        def _stats() -> None:
            folders = list(bench_backend.list_folders(self._root))
            for folder in folders:
                bench_backend.get_folder_info(f"{self._root}/{folder}")

        benchmark(_stats)


# ---------------------------------------------------------------------------
# Remote-store only: directory-scale operations (200 files)
# ---------------------------------------------------------------------------


class TestDirectoryScalePerformance:
    """Measure directory operations at scale -- remote-store only.

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
