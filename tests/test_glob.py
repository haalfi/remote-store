"""Tests for glob -- three-tier pattern matching.

Tier 1: Store.list_files(pattern=...) -- fnmatch name filtering (GLOB-001)
Tier 2: Store.glob() / Backend.glob() -- native glob (GLOB-002 through GLOB-008)
Tier 3: ext.glob.glob_files() -- portable fallback (GLOB-009 through GLOB-017)

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
from remote_store.ext.glob import _extract_prefix, _needs_recursive, _pattern_to_regex, glob_files

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


@pytest.fixture()
def local_store(tmp_path: Path) -> Store:
    """Return a LocalBackend-based Store (has GLOB) backed by tmp_path."""
    backend = LocalBackend(root=str(tmp_path))
    return Store(backend=backend, root_path="data")


@pytest.fixture()
def mem_store() -> Store:
    """Return a populated MemoryBackend-based Store (no GLOB)."""
    store = Store(backend=MemoryBackend(), root_path="data")
    _populate(store)
    return store


@pytest.fixture()
def pop_local(local_store: Store) -> Store:
    """Return a populated LocalBackend-based Store."""
    _populate(local_store)
    return local_store


# ===========================================================================
# Tier 1: list_files(pattern=...) -- GLOB-001
# ===========================================================================


class TestListFilesPattern:
    """GLOB-001: list_files pattern parameter with fnmatch filtering."""

    @pytest.mark.spec("GLOB-001")
    @pytest.mark.parametrize(
        "folder,pattern,recursive,expected",
        [
            pytest.param("", "*.csv", False, ["report.csv"], id="csv"),
            pytest.param("", "report.*", False, ["report.csv", "report.txt"], id="report_star"),
            pytest.param("docs", "*.md", False, ["docs/guide.md", "docs/readme.md"], id="docs_md"),
            pytest.param(
                "", "*.log", True, ["logs/app.log", "logs/archive/old.log", "logs/error.log"], id="recursive_log"
            ),
            pytest.param("", "*.xyz", False, [], id="no_matches"),
        ],
    )
    def test_pattern_filtering(
        self,
        mem_store: Store,
        folder: str,
        pattern: str,
        recursive: bool,
        expected: list[str],
    ) -> None:
        results = sorted(str(f.path) for f in mem_store.list_files(folder, pattern=pattern, recursive=recursive))
        assert results == expected

    @pytest.mark.spec("GLOB-001")
    def test_pattern_none_returns_all(self, mem_store: Store) -> None:
        assert len(list(mem_store.list_files("", pattern=None))) == len(list(mem_store.list_files("")))

    @pytest.mark.spec("GLOB-001")
    @pytest.mark.parametrize(
        "files,pattern,expected",
        [
            pytest.param(
                {"a1.txt": b"x", "a2.txt": b"y", "abc.txt": b"z"}, "a?.txt", ["a1.txt", "a2.txt"], id="question_mark"
            ),
            pytest.param(
                {"a1.txt": b"x", "a2.txt": b"y", "a3.txt": b"z"}, "a[12].txt", ["a1.txt", "a2.txt"], id="char_class"
            ),
        ],
    )
    def test_special_wildcards(self, files: dict[str, bytes], pattern: str, expected: list[str]) -> None:
        store = Store(backend=MemoryBackend(), root_path="data")
        for p, d in files.items():
            store.write(p, d)
        results = sorted(str(f.path) for f in store.list_files("", pattern=pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-001")
    def test_pattern_works_with_local_backend(self, pop_local: Store) -> None:
        results = sorted(str(f.path) for f in pop_local.list_files("", pattern="*.csv"))
        assert results == ["report.csv"]


# ===========================================================================
# Tier 2: Capability.GLOB, Backend.glob(), Store.glob() -- GLOB-002..008
# ===========================================================================


class TestTier2NativeGlob:
    """GLOB-002 through GLOB-008: capability checks, backend glob, store glob."""

    @pytest.mark.spec("GLOB-002")
    def test_glob_capability_exists(self) -> None:
        assert Capability.GLOB.value == "glob"

    @pytest.mark.spec("GLOB-002")
    def test_local_backend_has_glob(self, local_store: Store) -> None:
        assert local_store.supports(Capability.GLOB)

    @pytest.mark.spec("GLOB-002")
    def test_memory_backend_lacks_glob(self, mem_store: Store) -> None:
        assert not mem_store.supports(Capability.GLOB)

    @pytest.mark.spec("GLOB-003")
    def test_default_raises_capability_not_supported(self) -> None:
        with pytest.raises(CapabilityNotSupported):
            list(MemoryBackend().glob("*.txt"))

    @pytest.mark.spec("GLOB-005")
    @pytest.mark.parametrize(
        "pattern,expected",
        [
            pytest.param("*.csv", ["report.csv"], id="star_csv"),
            pytest.param("**/*.log", ["logs/app.log", "logs/archive/old.log", "logs/error.log"], id="recursive_log"),
            pytest.param("docs/*.md", ["docs/guide.md", "docs/readme.md"], id="subdirectory_md"),
            pytest.param("*.xyz", [], id="no_matches"),
        ],
    )
    def test_local_glob_patterns(self, pop_local: Store, pattern: str, expected: list[str]) -> None:
        results = sorted(str(f.path) for f in pop_local.glob(pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-004")
    def test_glob_files_only(self, pop_local: Store) -> None:
        """glob() must return only files, not folders."""
        for info in pop_local.glob("**/*"):
            assert pop_local.is_file(str(info.path))

    @pytest.mark.spec("GLOB-006")
    def test_store_glob_returns_iterator(self, pop_local: Store) -> None:
        result = pop_local.glob("*.csv")
        assert hasattr(result, "__iter__") and hasattr(result, "__next__")

    @pytest.mark.spec("GLOB-007")
    def test_store_glob_returns_store_relative_paths(self, pop_local: Store) -> None:
        for info in pop_local.glob("**/*"):
            assert not str(info.path).startswith("data/")

    @pytest.mark.spec("GLOB-007")
    def test_store_glob_round_trip(self, pop_local: Store) -> None:
        for info in pop_local.glob("**/*.csv"):
            assert len(pop_local.read_bytes(str(info.path))) > 0

    @pytest.mark.spec("GLOB-008")
    def test_store_glob_raises_without_capability(self, mem_store: Store) -> None:
        with pytest.raises(CapabilityNotSupported) as exc_info:
            list(mem_store.glob("*.csv"))
        assert exc_info.value.capability == "glob"


# ===========================================================================
# Tier 3: ext.glob -- GLOB-009..017
# ===========================================================================


class TestGlobFiles:
    """glob_files() -- native delegation and fallback paths."""

    @pytest.mark.spec("GLOB-010")
    @pytest.mark.parametrize(
        "pattern,expected",
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
        "pattern,expected",
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
        "pattern,count",
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

    @pytest.mark.spec("GLOB-007")
    @pytest.mark.parametrize(
        "child_path,pattern,expected",
        [
            pytest.param("docs", "*.md", ["guide.md", "readme.md"], id="child_docs"),
            pytest.param("logs", "**/*.log", ["app.log", "archive/old.log", "error.log"], id="child_logs_recursive"),
        ],
    )
    def test_glob_files_with_child_store(
        self, mem_store: Store, child_path: str, pattern: str, expected: list[str]
    ) -> None:
        child = mem_store.child(child_path)
        results = sorted(str(f.path) for f in glob_files(child, pattern))
        assert results == expected


# ===========================================================================
# GLOB-012, GLOB-013, GLOB-014: Internal helpers
# ===========================================================================


@pytest.mark.spec("GLOB-012")
@pytest.mark.parametrize(
    "pattern,expected",
    [
        pytest.param("data/2024/*.csv", "data/2024", id="data/2024/*.csv"),
        pytest.param("**/*.csv", "", id="**/*.csv"),
        pytest.param("*.txt", "", id="*.txt"),
        pytest.param("a/b/c/*.log", "a/b/c", id="a/b/c/*.log"),
        pytest.param("data/file.csv", "data", id="data/file.csv"),
    ],
)
def test_extract_prefix(pattern: str, expected: str) -> None:
    assert _extract_prefix(pattern) == expected


@pytest.mark.spec("GLOB-013")
@pytest.mark.parametrize(
    "pattern,expected",
    [
        pytest.param("**/*.csv", True, id="**/*.csv"),
        pytest.param("*.csv", False, id="*.csv"),
        pytest.param("data/*.csv", False, id="data/*.csv"),
        pytest.param("*/sub/*.csv", True, id="*/sub/*.csv"),
        pytest.param("log?/*.csv", True, id="log?/*.csv"),
    ],
)
def test_needs_recursive(pattern: str, expected: bool) -> None:
    assert _needs_recursive(pattern) is expected


@pytest.mark.spec("GLOB-014")
@pytest.mark.parametrize(
    "pattern,should_match,should_not_match",
    [
        pytest.param("*.csv", ["report.csv", ".csv"], ["dir/report.csv"], id="*.csv"),
        pytest.param("**/*.csv", ["report.csv", "dir/report.csv", "a/b/c/report.csv"], [], id="**/*.csv"),
        pytest.param("data/**", ["data/file.csv", "data/sub/file.csv"], [], id="data/**"),
        pytest.param("a?.txt", ["a1.txt", "ab.txt"], ["abc.txt", "a/.txt"], id="a?.txt"),
        pytest.param("data/file.csv", ["data/file.csv"], ["data/filexcsv"], id="data/file.csv"),
        pytest.param(
            "logs/**/*.log",
            ["logs/app.log", "logs/archive/old.log", "logs/a/b/c.log"],
            ["other/app.log"],
            id="logs/**/*.log",
        ),
        pytest.param("[abc].txt", ["a.txt", "b.txt"], ["d.txt"], id="[abc].txt"),
        pytest.param("[!abc].txt", ["d.txt", "x.txt"], ["a.txt"], id="[!abc].txt"),
    ],
)
def test_pattern_to_regex(pattern: str, should_match: list[str], should_not_match: list[str]) -> None:
    r = _pattern_to_regex(pattern)
    for path in should_match:
        assert r.match(path), f"{pattern!r} should match {path!r}"
    for path in should_not_match:
        assert not r.match(path), f"{pattern!r} should NOT match {path!r}"


@pytest.mark.spec("GLOB-014")
def test_unclosed_bracket_treated_as_literal() -> None:
    r = _pattern_to_regex("[abc.txt")
    assert r.match("[abc.txt")
    assert not r.match("a.txt")


@pytest.mark.spec("GLOB-014")
def test_double_star_non_segment_raises() -> None:
    with pytest.raises(ValueError, match="must be a complete path segment"):
        _pattern_to_regex("logs/**error.log")


@pytest.mark.spec("GLOB-014")
def test_double_star_valid_segments() -> None:
    for pattern in ("**/error.log", "logs/**", "a/**/b.txt", "**"):
        _pattern_to_regex(pattern)  # should not raise
