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


@pytest.fixture()
def local_store(tmp_path: Path) -> Store:
    """Return a LocalBackend-based Store (has GLOB) backed by tmp_path."""
    backend = LocalBackend(root=str(tmp_path))
    return Store(backend=backend, root_path="data")


def _memory_store() -> Store:
    """Return a MemoryBackend-based Store (no GLOB)."""
    return Store(backend=MemoryBackend(), root_path="data")


def _populate(store: Store) -> None:
    """Write a standard set of test files."""
    store.write("report.csv", b"r1")
    store.write("report.txt", b"r2")
    store.write("logs/app.log", b"l1")
    store.write("logs/error.log", b"l2")
    store.write("logs/archive/old.log", b"l3")
    store.write("docs/readme.md", b"d1")
    store.write("docs/guide.md", b"d2")
    store.write("docs/images/logo.png", b"i1")


# ===========================================================================
# Tier 1: list_files(pattern=...) -- GLOB-001, GLOB-017
# ===========================================================================


class TestListFilesPattern:
    """GLOB-001: list_files pattern parameter with fnmatch filtering."""

    @pytest.mark.spec("GLOB-001")
    @pytest.mark.parametrize(
        "folder,pattern,recursive,expected",
        [
            ("", "*.csv", False, ["report.csv"]),
            ("", "report.*", False, ["report.csv", "report.txt"]),
            ("docs", "*.md", False, ["docs/guide.md", "docs/readme.md"]),
            ("", "*.log", True, ["logs/app.log", "logs/archive/old.log", "logs/error.log"]),
            ("", "*.xyz", False, []),
        ],
        ids=["csv", "report_star", "docs_md", "recursive_log", "no_matches"],
    )
    def test_pattern_filtering(
        self,
        folder: str,
        pattern: str,
        recursive: bool,
        expected: list[str],
    ) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in store.list_files(folder, pattern=pattern, recursive=recursive))
        assert results == expected

    @pytest.mark.spec("GLOB-001")
    def test_pattern_none_returns_all(self) -> None:
        store = _memory_store()
        _populate(store)
        assert len(list(store.list_files("", pattern=None))) == len(list(store.list_files("")))

    @pytest.mark.spec("GLOB-001")
    def test_pattern_question_mark(self) -> None:
        store = _memory_store()
        store.write("a1.txt", b"x")
        store.write("a2.txt", b"y")
        store.write("abc.txt", b"z")
        results = sorted(str(f.path) for f in store.list_files("", pattern="a?.txt"))
        assert results == ["a1.txt", "a2.txt"]

    @pytest.mark.spec("GLOB-001")
    def test_pattern_character_class(self) -> None:
        store = _memory_store()
        store.write("a1.txt", b"x")
        store.write("a2.txt", b"y")
        store.write("a3.txt", b"z")
        results = sorted(str(f.path) for f in store.list_files("", pattern="a[12].txt"))
        assert results == ["a1.txt", "a2.txt"]

    @pytest.mark.spec("GLOB-001")
    def test_pattern_works_with_local_backend(self, local_store: Store) -> None:
        _populate(local_store)
        results = sorted(str(f.path) for f in local_store.list_files("", pattern="*.csv"))
        assert results == ["report.csv"]


# ===========================================================================
# Tier 2: Capability.GLOB, Backend.glob(), Store.glob() -- GLOB-002..008
# ===========================================================================


class TestGlobCapability:
    @pytest.mark.spec("GLOB-002")
    def test_glob_capability_exists(self) -> None:
        assert Capability.GLOB.value == "glob"

    @pytest.mark.spec("GLOB-002")
    def test_local_backend_has_glob(self, local_store: Store) -> None:
        assert local_store.supports(Capability.GLOB)

    @pytest.mark.spec("GLOB-002")
    def test_memory_backend_lacks_glob(self) -> None:
        assert not _memory_store().supports(Capability.GLOB)


class TestBackendGlobDefault:
    @pytest.mark.spec("GLOB-003")
    def test_default_raises_capability_not_supported(self) -> None:
        with pytest.raises(CapabilityNotSupported):
            list(MemoryBackend().glob("*.txt"))


class TestLocalBackendGlob:
    @pytest.mark.spec("GLOB-005")
    @pytest.mark.parametrize(
        "pattern,expected",
        [
            ("*.csv", ["report.csv"]),
            ("**/*.log", ["logs/app.log", "logs/archive/old.log", "logs/error.log"]),
            ("docs/*.md", ["docs/guide.md", "docs/readme.md"]),
            ("*.xyz", []),
        ],
        ids=["star_csv", "recursive_log", "subdirectory_md", "no_matches"],
    )
    def test_glob_patterns(self, local_store: Store, pattern: str, expected: list[str]) -> None:
        _populate(local_store)
        results = sorted(str(f.path) for f in local_store.glob(pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-004")
    def test_glob_files_only(self, local_store: Store) -> None:
        """glob() must return only files, not folders."""
        _populate(local_store)
        for info in local_store.glob("**/*"):
            assert local_store.is_file(str(info.path))


class TestStoreGlob:
    @pytest.mark.spec("GLOB-006")
    def test_store_glob_returns_iterator(self, local_store: Store) -> None:
        _populate(local_store)
        result = local_store.glob("*.csv")
        assert hasattr(result, "__iter__") and hasattr(result, "__next__")

    @pytest.mark.spec("GLOB-007")
    def test_store_glob_returns_store_relative_paths(self, local_store: Store) -> None:
        _populate(local_store)
        for info in local_store.glob("**/*"):
            assert not str(info.path).startswith("data/")

    @pytest.mark.spec("GLOB-007")
    def test_store_glob_round_trip(self, local_store: Store) -> None:
        _populate(local_store)
        for info in local_store.glob("**/*.csv"):
            assert len(local_store.read_bytes(str(info.path))) > 0

    @pytest.mark.spec("GLOB-008")
    def test_store_glob_raises_without_capability(self) -> None:
        store = _memory_store()
        _populate(store)
        with pytest.raises(CapabilityNotSupported) as exc_info:
            list(store.glob("*.csv"))
        assert exc_info.value.capability == "glob"


# ===========================================================================
# Tier 3: ext.glob -- GLOB-009..017
# ===========================================================================


class TestGlobFilesNative:
    """glob_files() with GLOB-capable backend (LocalBackend)."""

    @pytest.mark.spec("GLOB-010")
    @pytest.mark.parametrize(
        "pattern,expected",
        [
            ("*.csv", ["report.csv"]),
            ("**/*.md", ["docs/guide.md", "docs/readme.md"]),
        ],
        ids=["star_csv", "recursive_md"],
    )
    def test_delegates_to_native(self, local_store: Store, pattern: str, expected: list[str]) -> None:
        _populate(local_store)
        results = sorted(str(f.path) for f in glob_files(local_store, pattern))
        assert results == expected


class TestGlobFilesFallback:
    """glob_files() with non-GLOB backend (MemoryBackend)."""

    @pytest.mark.spec("GLOB-011")
    @pytest.mark.parametrize(
        "pattern,expected",
        [
            ("*.csv", ["report.csv"]),
            ("*.txt", ["report.txt"]),
            ("docs/*.md", ["docs/guide.md", "docs/readme.md"]),
            ("**/*.log", ["logs/app.log", "logs/archive/old.log", "logs/error.log"]),
            ("logs/**/*.log", ["logs/app.log", "logs/archive/old.log", "logs/error.log"]),
            ("*.xyz", []),
        ],
        ids=["star_csv", "star_txt", "subdirectory", "recursive", "double_star_middle", "no_matches"],
    )
    def test_fallback_patterns(self, pattern: str, expected: list[str]) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-011")
    def test_recursive_double_star_all(self) -> None:
        store = _memory_store()
        _populate(store)
        assert len(list(glob_files(store, "**/*"))) == 8

    @pytest.mark.spec("GLOB-011")
    def test_question_mark_wildcard(self) -> None:
        store = _memory_store()
        store.write("a1.txt", b"x")
        store.write("a2.txt", b"y")
        store.write("ab.txt", b"z")
        results = sorted(str(f.path) for f in glob_files(store, "a?.txt"))
        assert results == ["a1.txt", "a2.txt", "ab.txt"]


# ===========================================================================
# GLOB-012: Prefix extraction (parametrized)
# ===========================================================================

_PREFIX_CASES = [
    ("data/2024/*.csv", "data/2024"),
    ("**/*.csv", ""),
    ("*.txt", ""),
    ("a/b/c/*.log", "a/b/c"),
    ("data/file.csv", "data"),
]


@pytest.mark.spec("GLOB-012")
@pytest.mark.parametrize("pattern,expected", _PREFIX_CASES, ids=[p for p, _ in _PREFIX_CASES])
def test_extract_prefix(pattern: str, expected: str) -> None:
    assert _extract_prefix(pattern) == expected


# ===========================================================================
# GLOB-013: Recursive detection (parametrized)
# ===========================================================================

_RECURSIVE_CASES = [
    ("**/*.csv", True),
    ("*.csv", False),
    ("data/*.csv", False),
    ("*/sub/*.csv", True),
    ("log?/*.csv", True),
]


@pytest.mark.spec("GLOB-013")
@pytest.mark.parametrize("pattern,expected", _RECURSIVE_CASES, ids=[p for p, _ in _RECURSIVE_CASES])
def test_needs_recursive(pattern: str, expected: bool) -> None:
    assert _needs_recursive(pattern) is expected


# ===========================================================================
# GLOB-014: Pattern-to-regex conversion (parametrized)
# ===========================================================================

_REGEX_CASES: list[tuple[str, list[str], list[str]]] = [
    ("*.csv", ["report.csv", ".csv"], ["dir/report.csv"]),
    ("**/*.csv", ["report.csv", "dir/report.csv", "a/b/c/report.csv"], []),
    ("data/**", ["data/file.csv", "data/sub/file.csv"], []),
    ("a?.txt", ["a1.txt", "ab.txt"], ["abc.txt", "a/.txt"]),
    ("data/file.csv", ["data/file.csv"], ["data/filexcsv"]),
    ("logs/**/*.log", ["logs/app.log", "logs/archive/old.log", "logs/a/b/c.log"], ["other/app.log"]),
    ("[abc].txt", ["a.txt", "b.txt"], ["d.txt"]),
    ("[!abc].txt", ["d.txt", "x.txt"], ["a.txt"]),
]


@pytest.mark.spec("GLOB-014")
@pytest.mark.parametrize(
    "pattern,should_match,should_not_match",
    _REGEX_CASES,
    ids=[p for p, _, _ in _REGEX_CASES],
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


# ===========================================================================
# GLOB-015, GLOB-016: No backend coupling, capability propagation
# ===========================================================================


class TestGlobFilesContract:
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
            ("docs", "*.md", ["guide.md", "readme.md"]),
            ("logs", "**/*.log", ["app.log", "archive/old.log", "error.log"]),
        ],
        ids=["child_docs", "child_logs_recursive"],
    )
    def test_glob_files_with_child_store(self, child_path: str, pattern: str, expected: list[str]) -> None:
        store = _memory_store()
        _populate(store)
        child = store.child(child_path)
        results = sorted(str(f.path) for f in glob_files(child, pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-011")
    def test_bare_double_star_matches_all(self) -> None:
        store = _memory_store()
        _populate(store)
        assert len(list(glob_files(store, "**"))) == 8
