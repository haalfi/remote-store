"""Tests for glob — Store.glob() and ext.glob.glob_files().

Covers spec 018-glob.md (GLOB-001 through GLOB-016).
"""

from __future__ import annotations

import tempfile

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.glob import _extract_prefix, _needs_recursive, _pattern_to_regex, glob_files

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _local_store() -> tuple[Store, str]:
    """Return a LocalBackend-based Store (has GLOB) and temp dir path."""
    tmp = tempfile.mkdtemp()
    backend = LocalBackend(root=tmp)
    store = Store(backend=backend, root_path="data")
    return store, tmp


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


# ---------------------------------------------------------------------------
# GLOB-001: Capability.GLOB enum member
# ---------------------------------------------------------------------------


class TestGlobCapability:
    @pytest.mark.spec("GLOB-001")
    def test_glob_capability_exists(self) -> None:
        assert Capability.GLOB.value == "glob"

    @pytest.mark.spec("GLOB-001")
    def test_local_backend_has_glob(self) -> None:
        store, _ = _local_store()
        assert store.supports(Capability.GLOB)

    @pytest.mark.spec("GLOB-001")
    def test_memory_backend_lacks_glob(self) -> None:
        store = _memory_store()
        assert not store.supports(Capability.GLOB)


# ---------------------------------------------------------------------------
# GLOB-002, GLOB-003: Backend.glob() default
# ---------------------------------------------------------------------------


class TestBackendGlobDefault:
    @pytest.mark.spec("GLOB-002")
    def test_default_raises_capability_not_supported(self) -> None:
        backend = MemoryBackend()
        with pytest.raises(CapabilityNotSupported):
            list(backend.glob("*.txt"))


# ---------------------------------------------------------------------------
# GLOB-004: LocalBackend native glob
# ---------------------------------------------------------------------------


class TestLocalBackendGlob:
    @pytest.mark.spec("GLOB-004")
    def test_glob_star_csv(self) -> None:
        store, _ = _local_store()
        _populate(store)
        results = sorted(str(f.path) for f in store.glob("*.csv"))
        assert results == ["report.csv"]

    @pytest.mark.spec("GLOB-004")
    def test_glob_recursive(self) -> None:
        store, _ = _local_store()
        _populate(store)
        results = sorted(str(f.path) for f in store.glob("**/*.log"))
        assert results == ["logs/app.log", "logs/archive/old.log", "logs/error.log"]

    @pytest.mark.spec("GLOB-004")
    def test_glob_subdirectory(self) -> None:
        store, _ = _local_store()
        _populate(store)
        results = sorted(str(f.path) for f in store.glob("docs/*.md"))
        assert results == ["docs/guide.md", "docs/readme.md"]

    @pytest.mark.spec("GLOB-004")
    def test_glob_no_matches(self) -> None:
        store, _ = _local_store()
        _populate(store)
        results = list(store.glob("*.xyz"))
        assert results == []

    @pytest.mark.spec("GLOB-004")
    def test_glob_files_only(self) -> None:
        """glob() must return only files, not folders."""
        store, _ = _local_store()
        _populate(store)
        for info in store.glob("**/*"):
            # All results should be files
            assert store.is_file(str(info.path))


# ---------------------------------------------------------------------------
# GLOB-005 through GLOB-007: Store.glob()
# ---------------------------------------------------------------------------


class TestStoreGlob:
    @pytest.mark.spec("GLOB-005")
    def test_store_glob_returns_iterator(self) -> None:
        store, _ = _local_store()
        _populate(store)
        result = store.glob("*.csv")
        # Should be an iterator/generator
        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")

    @pytest.mark.spec("GLOB-006")
    def test_store_glob_returns_store_relative_paths(self) -> None:
        """Paths in results are store-relative, not backend-relative."""
        store, _ = _local_store()
        _populate(store)
        for info in store.glob("**/*"):
            # No path should start with "data/" (the root_path)
            assert not str(info.path).startswith("data/")

    @pytest.mark.spec("GLOB-006")
    def test_store_glob_round_trip(self) -> None:
        """Glob results can be fed back to Store methods."""
        store, _ = _local_store()
        _populate(store)
        for info in store.glob("**/*.csv"):
            data = store.read_bytes(str(info.path))
            assert len(data) > 0

    @pytest.mark.spec("GLOB-007")
    def test_store_glob_raises_without_capability(self) -> None:
        store = _memory_store()
        _populate(store)
        with pytest.raises(CapabilityNotSupported) as exc_info:
            list(store.glob("*.csv"))
        assert exc_info.value.capability == "glob"


# ---------------------------------------------------------------------------
# GLOB-008, GLOB-009: ext.glob native delegation
# ---------------------------------------------------------------------------


class TestGlobFilesNative:
    """glob_files() with GLOB-capable backend (LocalBackend)."""

    @pytest.mark.spec("GLOB-009")
    def test_delegates_to_native(self) -> None:
        store, _ = _local_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "*.csv"))
        assert results == ["report.csv"]

    @pytest.mark.spec("GLOB-009")
    def test_recursive_native(self) -> None:
        store, _ = _local_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "**/*.md"))
        assert results == ["docs/guide.md", "docs/readme.md"]


# ---------------------------------------------------------------------------
# GLOB-010 through GLOB-013: ext.glob client-side fallback
# ---------------------------------------------------------------------------


class TestGlobFilesFallback:
    """glob_files() with non-GLOB backend (MemoryBackend)."""

    @pytest.mark.spec("GLOB-010")
    def test_star_pattern(self) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "*.csv"))
        assert results == ["report.csv"]

    @pytest.mark.spec("GLOB-010")
    def test_star_pattern_txt(self) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "*.txt"))
        assert results == ["report.txt"]

    @pytest.mark.spec("GLOB-010")
    def test_subdirectory_pattern(self) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "docs/*.md"))
        assert results == ["docs/guide.md", "docs/readme.md"]

    @pytest.mark.spec("GLOB-010")
    def test_recursive_double_star(self) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "**/*.log"))
        assert results == ["logs/app.log", "logs/archive/old.log", "logs/error.log"]

    @pytest.mark.spec("GLOB-010")
    def test_recursive_double_star_all(self) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "**/*"))
        assert len(results) == 8  # all files

    @pytest.mark.spec("GLOB-010")
    def test_double_star_in_middle(self) -> None:
        store = _memory_store()
        _populate(store)
        results = sorted(str(f.path) for f in glob_files(store, "logs/**/*.log"))
        assert results == ["logs/app.log", "logs/archive/old.log", "logs/error.log"]

    @pytest.mark.spec("GLOB-010")
    def test_question_mark_wildcard(self) -> None:
        store = _memory_store()
        store.write("a1.txt", b"x")
        store.write("a2.txt", b"y")
        store.write("ab.txt", b"z")
        results = sorted(str(f.path) for f in glob_files(store, "a?.txt"))
        assert results == ["a1.txt", "a2.txt", "ab.txt"]

    @pytest.mark.spec("GLOB-016")
    def test_no_matches_returns_empty(self) -> None:
        store = _memory_store()
        _populate(store)
        results = list(glob_files(store, "*.xyz"))
        assert results == []


# ---------------------------------------------------------------------------
# GLOB-011: Prefix extraction
# ---------------------------------------------------------------------------


class TestPrefixExtraction:
    @pytest.mark.spec("GLOB-011")
    def test_simple_prefix(self) -> None:
        assert _extract_prefix("data/2024/*.csv") == "data/2024"

    @pytest.mark.spec("GLOB-011")
    def test_no_prefix(self) -> None:
        assert _extract_prefix("**/*.csv") == ""

    @pytest.mark.spec("GLOB-011")
    def test_star_at_root(self) -> None:
        assert _extract_prefix("*.txt") == ""

    @pytest.mark.spec("GLOB-011")
    def test_deep_prefix(self) -> None:
        assert _extract_prefix("a/b/c/*.log") == "a/b/c"

    @pytest.mark.spec("GLOB-011")
    def test_literal_pattern_uses_parent(self) -> None:
        """A literal pattern (no wildcards) uses parent as prefix."""
        assert _extract_prefix("data/file.csv") == "data"


# ---------------------------------------------------------------------------
# GLOB-012: Recursive detection
# ---------------------------------------------------------------------------


class TestRecursiveDetection:
    @pytest.mark.spec("GLOB-012")
    def test_double_star_is_recursive(self) -> None:
        assert _needs_recursive("**/*.csv") is True

    @pytest.mark.spec("GLOB-012")
    def test_star_only_is_not_recursive(self) -> None:
        assert _needs_recursive("*.csv") is False

    @pytest.mark.spec("GLOB-012")
    def test_subdirectory_star_is_not_recursive(self) -> None:
        assert _needs_recursive("data/*.csv") is False

    @pytest.mark.spec("GLOB-012")
    def test_wildcard_in_middle_segment(self) -> None:
        assert _needs_recursive("*/sub/*.csv") is True

    @pytest.mark.spec("GLOB-012")
    def test_question_in_middle_segment(self) -> None:
        assert _needs_recursive("log?/*.csv") is True


# ---------------------------------------------------------------------------
# GLOB-013: Pattern-to-regex conversion
# ---------------------------------------------------------------------------


class TestPatternToRegex:
    @pytest.mark.spec("GLOB-013")
    def test_star(self) -> None:
        r = _pattern_to_regex("*.csv")
        assert r.match("report.csv")
        assert r.match(".csv")
        assert not r.match("dir/report.csv")

    @pytest.mark.spec("GLOB-013")
    def test_double_star_slash(self) -> None:
        r = _pattern_to_regex("**/*.csv")
        assert r.match("report.csv")
        assert r.match("dir/report.csv")
        assert r.match("a/b/c/report.csv")

    @pytest.mark.spec("GLOB-013")
    def test_double_star_at_end(self) -> None:
        r = _pattern_to_regex("data/**")
        assert r.match("data/file.csv")
        assert r.match("data/sub/file.csv")

    @pytest.mark.spec("GLOB-013")
    def test_question_mark(self) -> None:
        r = _pattern_to_regex("a?.txt")
        assert r.match("a1.txt")
        assert r.match("ab.txt")
        assert not r.match("abc.txt")
        assert not r.match("a/.txt")

    @pytest.mark.spec("GLOB-013")
    def test_escaped_special_chars(self) -> None:
        r = _pattern_to_regex("data/file.csv")
        assert r.match("data/file.csv")
        assert not r.match("data/filexcsv")

    @pytest.mark.spec("GLOB-013")
    def test_complex_pattern(self) -> None:
        r = _pattern_to_regex("logs/**/*.log")
        assert r.match("logs/app.log")
        assert r.match("logs/archive/old.log")
        assert r.match("logs/a/b/c.log")
        assert not r.match("other/app.log")


# ---------------------------------------------------------------------------
# GLOB-014, GLOB-015: No backend coupling, capability propagation
# ---------------------------------------------------------------------------


class TestGlobFilesContract:
    @pytest.mark.spec("GLOB-015")
    def test_list_capability_propagates(self) -> None:
        """glob_files propagates CapabilityNotSupported from list_files."""

        class _NoListBackend(MemoryBackend):
            @property
            def capabilities(self) -> CapabilitySet:
                return CapabilitySet({Capability.READ, Capability.WRITE, Capability.DELETE})

        store = Store(backend=_NoListBackend())
        with pytest.raises(CapabilityNotSupported):
            list(glob_files(store, "*.txt"))
