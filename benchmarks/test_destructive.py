"""Destructive operation benchmarks.

Comparative: single-file delete via ``bench_target``.
Remote-store only: copy, move, directory-scale destructive ops via ``bench_backend``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from benchmarks.targets._protocol import BenchTarget
    from remote_store._backend import Backend


def _unique(prefix: str = "bench") -> str:
    return f"{prefix}/{uuid.uuid4().hex[:12]}.bin"


# ---------------------------------------------------------------------------
# Comparative: delete single file
# ---------------------------------------------------------------------------


class TestDeletePerformance:
    """Comparative delete latency (bench_target)."""

    def test_delete(self, bench_target: BenchTarget, benchmark: Any) -> None:
        pool_size = 200
        paths: list[str] = []
        for _ in range(pool_size):
            p = _unique("del")
            bench_target.write(p, b"y")
            paths.append(p)
        counter = [0]

        def _delete() -> None:
            i = counter[0]
            counter[0] += 1
            if i < len(paths):
                bench_target.delete(paths[i])

        benchmark.pedantic(_delete, rounds=pool_size, iterations=1, warmup_rounds=0)


# ---------------------------------------------------------------------------
# Remote-store only: copy / move
# ---------------------------------------------------------------------------


class TestCopyMovePerformance:
    """Copy and move latency — remote-store only."""

    def test_copy(self, bench_backend: Backend, benchmark: Any) -> None:
        src = _unique("cpsrc")
        bench_backend.write(src, b"Z" * 4096)

        def _copy() -> None:
            bench_backend.copy(src, _unique("cpdst"), overwrite=True)

        benchmark(_copy)

    def test_move(self, bench_backend: Backend, benchmark: Any) -> None:
        pool_size = 200
        paths: list[str] = []
        for _ in range(pool_size):
            p = _unique("mvsrc")
            bench_backend.write(p, b"Z" * 4096)
            paths.append(p)
        counter = [0]

        def _move() -> None:
            i = counter[0]
            counter[0] += 1
            if i < len(paths):
                bench_backend.move(paths[i], _unique("mvdst"))

        benchmark.pedantic(_move, rounds=pool_size, iterations=1, warmup_rounds=0)


# ---------------------------------------------------------------------------
# Remote-store only: directory-scale destructive operations
# ---------------------------------------------------------------------------


class TestDirectoryDestructivePerformance:
    """Destructive directory-scale operations — remote-store only."""

    @pytest.fixture(autouse=True)
    def _populate_hierarchy(self, bench_backend: Backend) -> None:
        self._root = f"scale/{uuid.uuid4().hex[:8]}"
        for i in range(20):
            bench_backend.write(f"{self._root}/lvl0_{i:02d}.txt", b"x")
        for d in range(5):
            for i in range(20):
                bench_backend.write(f"{self._root}/sub_{d}/lvl1_{i:02d}.txt", b"x")
            for i in range(16):
                bench_backend.write(f"{self._root}/sub_{d}/deep/lvl2_{i:02d}.txt", b"x")

    def test_copy_across_subtrees(self, bench_backend: Backend, benchmark: Any) -> None:
        """Copy a file from one subtree to another."""
        src = f"{self._root}/sub_0/lvl1_00.txt"

        def _copy() -> None:
            bench_backend.copy(src, f"{self._root}/sub_4/{_unique('cp')}", overwrite=True)

        benchmark(_copy)

    def test_move_across_subtrees(self, bench_backend: Backend, benchmark: Any) -> None:
        """Move files from one subtree to another (pre-created pool)."""
        pool_size = 100
        paths: list[str] = []
        for i in range(pool_size):
            p = f"{self._root}/mvpool/f_{i:04d}.txt"
            bench_backend.write(p, b"m")
            paths.append(p)
        counter = [0]

        def _move() -> None:
            i = counter[0]
            counter[0] += 1
            if i < len(paths):
                bench_backend.move(paths[i], f"{self._root}/sub_3/{_unique('mv')}")

        benchmark.pedantic(_move, rounds=pool_size, iterations=1, warmup_rounds=0)

    def test_delete_folder_recursive(self, bench_backend: Backend, benchmark: Any) -> None:
        """Delete an entire subtree (36 files) recursively."""
        pool_size = 30
        subtrees: list[str] = []
        for t in range(pool_size):
            base = f"{self._root}/delfolder_{t}"
            for i in range(20):
                bench_backend.write(f"{base}/f_{i:02d}.txt", b"d")
            for i in range(16):
                bench_backend.write(f"{base}/nested/f_{i:02d}.txt", b"d")
            subtrees.append(base)
        counter = [0]

        def _delete() -> None:
            i = counter[0]
            counter[0] += 1
            if i < len(subtrees):
                bench_backend.delete_folder(subtrees[i], recursive=True)

        benchmark.pedantic(_delete, rounds=pool_size, iterations=1, warmup_rounds=0)
