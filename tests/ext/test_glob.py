"""Tests for ext.glob -- portable Tier 3 fallback for glob_files().

Tier 3 surface: ``glob_files`` signature, native delegation when the
backend declares ``Capability.GLOB``, client-side fallback patterns, and
capability-gating propagation. The ``@pytest.mark.spec`` markers below
record the precise spec IDs each test pins.

Companion to ``tests/test_glob.py``, which covers the internal helpers
in ``_glob.py`` (extract_prefix / needs_recursive / pattern_to_regex)
and the Tier 2 native path through ``Store.glob`` / ``Backend.glob``.

Covers spec 018-glob.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.glob import glob_files

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.os_sensitive

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TREE_FILES: dict[str, bytes] = {
    "report.csv": b"r1",
    "report.txt": b"r2",
    "logs/app.log": b"l1",
    "logs/error.log": b"l2",
    "logs/archive/old.log": b"l3",
    "docs/readme.md": b"d1",
    "docs/guide.md": b"d2",
    "docs/images/logo.png": b"i1",
}


def _populate(store: Store) -> None:
    """Write a standard set of test files."""
    for path, data in _TREE_FILES.items():
        store.write(path, data)


@pytest.fixture
def local_store(tmp_path: Path) -> Store:
    """Return a LocalBackend-based Store (has GLOB) backed by tmp_path."""
    backend = LocalBackend(root=str(tmp_path))
    return Store(backend=backend, root_path="data")


@pytest.fixture
def mem_store() -> Store:
    """Return a populated MemoryBackend-based Store (no GLOB)."""
    store = Store(backend=MemoryBackend(), root_path="data")
    _populate(store)
    return store


@pytest.fixture
def pop_local(local_store: Store) -> Store:
    """Return a populated LocalBackend-based Store."""
    _populate(local_store)
    return local_store


# ===========================================================================
# Tier 3: ext.glob -- GLOB-009..017
# ===========================================================================


class TestGlobFiles:
    """glob_files() -- native delegation and fallback paths."""

    @pytest.mark.spec("GLOB-010")
    @pytest.mark.parametrize(
        ("pattern", "expected"),
        [
            pytest.param("*.csv", ["report.csv"], id="star_csv"),
            pytest.param("**/*.md", ["docs/guide.md", "docs/readme.md"], id="recursive_md"),
        ],
    )
    def test_delegates_to_native(self, pop_local: Store, pattern: str, expected: list[str]) -> None:
        results = sorted(str(f.path) for f in glob_files(pop_local, pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-011")
    @pytest.mark.parametrize(
        ("pattern", "expected"),
        [
            pytest.param("*.csv", ["report.csv"], id="star_csv"),
            pytest.param("*.txt", ["report.txt"], id="star_txt"),
            pytest.param("docs/*.md", ["docs/guide.md", "docs/readme.md"], id="subdirectory"),
            pytest.param("**/*.log", ["logs/app.log", "logs/archive/old.log", "logs/error.log"], id="recursive"),
            pytest.param(
                "logs/**/*.log", ["logs/app.log", "logs/archive/old.log", "logs/error.log"], id="double_star_middle"
            ),
            pytest.param("*.xyz", [], id="no_matches"),
        ],
    )
    def test_fallback_patterns(self, mem_store: Store, pattern: str, expected: list[str]) -> None:
        results = sorted(str(f.path) for f in glob_files(mem_store, pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-011")
    @pytest.mark.parametrize(
        ("pattern", "count"),
        [
            pytest.param("**/*", 8, id="double_star_all"),
            pytest.param("**", 8, id="bare_double_star"),
        ],
    )
    def test_double_star_matches_all(self, mem_store: Store, pattern: str, count: int) -> None:
        assert len(list(glob_files(mem_store, pattern))) == count

    @pytest.mark.spec("GLOB-011")
    def test_question_mark_wildcard(self) -> None:
        store = Store(backend=MemoryBackend(), root_path="data")
        for name, data in [("a1.txt", b"x"), ("a2.txt", b"y"), ("ab.txt", b"z")]:
            store.write(name, data)
        results = sorted(str(f.path) for f in glob_files(store, "a?.txt"))
        assert results == ["a1.txt", "a2.txt", "ab.txt"]

    @pytest.mark.spec("GLOB-016")
    def test_list_capability_propagates(self) -> None:
        class _NoListBackend(MemoryBackend):
            @property
            def capabilities(self) -> CapabilitySet:
                return CapabilitySet({Capability.READ, Capability.WRITE, Capability.DELETE})

        store = Store(backend=_NoListBackend())
        with pytest.raises(CapabilityNotSupported):
            list(glob_files(store, "*.txt"))

    @pytest.mark.spec("GLOB-009")
    @pytest.mark.parametrize(
        ("child_path", "pattern", "expected"),
        [
            pytest.param("docs", "*.md", ["guide.md", "readme.md"], id="child_docs"),
            pytest.param("logs", "**/*.log", ["app.log", "archive/old.log", "error.log"], id="child_logs_recursive"),
        ],
    )
    def test_glob_files_with_child_store(
        self, mem_store: Store, child_path: str, pattern: str, expected: list[str]
    ) -> None:
        # GLOB-009: ``glob_files(store, pattern)`` accepts any ``Store``,
        # including a child wrapper. Also exercises GLOB-015 (no backend
        # coupling — operates only through the public Store API).
        child = mem_store.child(child_path)
        results = sorted(str(f.path) for f in glob_files(child, pattern))
        assert results == expected
