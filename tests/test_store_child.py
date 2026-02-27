"""Tests for Store.child() — derived from sdd/specs/015-store-child.md."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import InvalidPath
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


@pytest.fixture
def store(backend: MemoryBackend) -> Iterator[Store]:
    s = Store(backend=backend, root_path="data")
    yield s
    s.close()


class TestChildSignature:
    """CHILD-001: Method signature."""

    @pytest.mark.spec("CHILD-001")
    def test_child_returns_store(self, store: Store) -> None:
        child = store.child("sub")
        assert isinstance(child, Store)

    @pytest.mark.spec("CHILD-001")
    def test_child_accepts_string(self, store: Store) -> None:
        child = store.child("reports/2026")
        assert isinstance(child, Store)


class TestChildRootComposition:
    """CHILD-002: Root composition."""

    @pytest.mark.spec("CHILD-002")
    def test_child_appends_to_parent_root(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("sub")
        assert child._root == "data/sub"

    @pytest.mark.spec("CHILD-002")
    def test_child_with_empty_parent_root(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="")
        child = parent.child("sub")
        assert child._root == "sub"

    @pytest.mark.spec("CHILD-002")
    def test_child_with_nested_subpath(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("a/b/c")
        assert child._root == "data/a/b/c"


class TestChildSubpathValidation:
    """CHILD-003: Subpath validation via RemotePath."""

    @pytest.mark.spec("CHILD-003")
    def test_empty_subpath_rejected(self, store: Store) -> None:
        with pytest.raises(InvalidPath):
            store.child("")

    @pytest.mark.spec("CHILD-003")
    def test_dotdot_subpath_rejected(self, store: Store) -> None:
        with pytest.raises(InvalidPath):
            store.child("../escape")

    @pytest.mark.spec("CHILD-003")
    def test_null_byte_rejected(self, store: Store) -> None:
        with pytest.raises(InvalidPath):
            store.child("bad\x00path")


class TestChildBackendSharing:
    """CHILD-004: Backend sharing (identity)."""

    @pytest.mark.spec("CHILD-004")
    def test_child_shares_backend_identity(self, store: Store, backend: MemoryBackend) -> None:
        child = store.child("sub")
        assert child._backend is backend


class TestChildChaining:
    """CHILD-005: Chaining."""

    @pytest.mark.spec("CHILD-005")
    def test_chained_child_equals_single_child(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        chained = parent.child("a").child("b")
        single = parent.child("a/b")
        assert chained == single
        assert chained._root == single._root
        assert chained._backend is single._backend


class TestChildCloseSemantics:
    """CHILD-006 / CHILD-007: Close and context manager semantics."""

    @pytest.mark.spec("CHILD-006")
    def test_child_close_does_not_close_backend(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        parent.write("file.txt", b"hello")
        child = parent.child("sub")
        child.close()
        # Backend still usable — parent can still read
        assert parent.exists("file.txt")

    @pytest.mark.spec("CHILD-007")
    def test_child_context_manager_safe(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        parent.write("file.txt", b"hello")
        with parent.child("sub"):
            pass
        # Backend still usable after child context manager exits
        assert parent.read_bytes("file.txt") == b"hello"

    @pytest.mark.spec("CHILD-006")
    def test_parent_owns_backend(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("sub")
        assert parent._owns_backend is True
        assert child._owns_backend is False


class TestChildEquality:
    """CHILD-008: Equality and hashing."""

    @pytest.mark.spec("CHILD-008")
    def test_child_equals_direct_construction(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("sub")
        direct = Store(backend=backend, root_path="data/sub")
        assert child == direct

    @pytest.mark.spec("CHILD-008")
    def test_child_hash_matches_direct_construction(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("sub")
        direct = Store(backend=backend, root_path="data/sub")
        assert hash(child) == hash(direct)


class TestChildPathRoundTrip:
    """CHILD-009: Path round-trip."""

    @pytest.mark.spec("CHILD-009")
    def test_list_files_returns_child_relative_paths(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("reports")
        child.write("jan.txt", b"jan data")
        child.write("feb.txt", b"feb data")

        paths = [str(info.path) for info in child.list_files("")]
        assert sorted(paths) == ["feb.txt", "jan.txt"]

    @pytest.mark.spec("CHILD-009")
    def test_listed_paths_usable_as_input(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("reports")
        child.write("report.txt", b"contents")

        infos = list(child.list_files(""))
        assert len(infos) == 1
        # The listed path should work as input to read_bytes
        assert child.read_bytes(str(infos[0].path)) == b"contents"


class TestChildRepr:
    """CHILD-011: Repr shows combined root."""

    @pytest.mark.spec("CHILD-011")
    def test_repr_shows_combined_root(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("sub")
        direct = Store(backend=backend, root_path="data/sub")
        assert repr(child) == repr(direct)

    @pytest.mark.spec("CHILD-011")
    def test_repr_indistinguishable(self, backend: MemoryBackend) -> None:
        child = Store(backend=backend, root_path="").child("top")
        assert "top" in repr(child)
        assert "child" not in repr(child).lower()


class TestChildThreadSafety:
    """CHILD-010: Thread safety."""

    @pytest.mark.spec("CHILD-010")
    def test_concurrent_child_creation(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        results: list[Store] = []
        errors: list[Exception] = []

        def create_child(name: str) -> None:
            try:
                results.append(parent.child(name))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=create_child, args=(f"t{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 10
