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


class TestChildBasics:
    """CHILD-001 / CHILD-002: Method signature and root composition."""

    @pytest.mark.spec("CHILD-001")
    @pytest.mark.parametrize(
        "subpath",
        [
            pytest.param("sub", id="simple"),
            pytest.param("reports/2026", id="nested"),
        ],
    )
    def test_child_returns_store(self, store: Store, subpath: str) -> None:
        assert isinstance(store.child(subpath), Store)

    @pytest.mark.spec("CHILD-002")
    @pytest.mark.parametrize(
        ("parent_root", "subpath", "expected"),
        [
            pytest.param("data", "sub", "data/sub", id="appends_to_parent"),
            pytest.param("", "sub", "sub", id="empty_parent_root"),
            pytest.param("data", "a/b/c", "data/a/b/c", id="nested_subpath"),
        ],
    )
    def test_child_root_composition(
        self, backend: MemoryBackend, parent_root: str, subpath: str, expected: str
    ) -> None:
        parent = Store(backend=backend, root_path=parent_root)
        assert parent.child(subpath) == Store(backend=backend, root_path=expected)


class TestChildValidation:
    """CHILD-003: Subpath validation via RemotePath."""

    @pytest.mark.spec("CHILD-003")
    @pytest.mark.parametrize(
        "bad_path",
        [
            pytest.param("", id="empty"),
            pytest.param("../escape", id="dotdot"),
            pytest.param("bad\x00path", id="null_byte"),
        ],
    )
    def test_invalid_subpath_rejected(self, store: Store, bad_path: str) -> None:
        with pytest.raises(InvalidPath):
            store.child(bad_path)


class TestChildSharingAndChaining:
    """CHILD-004 / CHILD-005: Backend sharing and chaining."""

    @pytest.mark.spec("CHILD-004")
    def test_child_shares_backend(self, store: Store, backend: MemoryBackend) -> None:
        store.write("sub/file.txt", b"shared")
        child = store.child("sub")
        assert child.read_bytes("file.txt") == b"shared"

    @pytest.mark.spec("CHILD-005")
    def test_chained_child_equals_single_child(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        chained = parent.child("a").child("b")
        single = parent.child("a/b")
        assert chained == single


class TestChildCloseSemantics:
    """CHILD-006 / CHILD-007: Close and context manager semantics."""

    @pytest.mark.spec("CHILD-006")
    def test_child_close_does_not_close_backend(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        parent.write("file.txt", b"hello")
        parent.child("sub").close()
        assert parent.exists("file.txt")

    @pytest.mark.spec("CHILD-007")
    def test_child_context_manager_safe(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        parent.write("file.txt", b"hello")
        with parent.child("sub"):
            pass
        assert parent.read_bytes("file.txt") == b"hello"


class TestChildEqualityAndRepr:
    """CHILD-008 / CHILD-011: Equality, hashing, and repr."""

    @pytest.mark.spec("CHILD-008")
    @pytest.mark.parametrize(
        "check",
        [
            pytest.param("eq", id="equality"),
            pytest.param("hash", id="hash"),
        ],
    )
    def test_child_equals_direct_construction(self, backend: MemoryBackend, check: str) -> None:
        parent = Store(backend=backend, root_path="data")
        child = parent.child("sub")
        direct = Store(backend=backend, root_path="data/sub")
        if check == "eq":
            assert child == direct
        else:
            assert hash(child) == hash(direct)

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


class TestChildPathRoundTrip:
    """CHILD-009: Path round-trip."""

    @pytest.mark.spec("CHILD-009")
    def test_list_files_returns_child_relative_paths(self, backend: MemoryBackend) -> None:
        child = Store(backend=backend, root_path="data").child("reports")
        child.write("jan.txt", b"jan data")
        child.write("feb.txt", b"feb data")
        paths = sorted(str(info.path) for info in child.list_files(""))
        assert paths == ["feb.txt", "jan.txt"]

    @pytest.mark.spec("CHILD-009")
    def test_listed_paths_usable_as_input(self, backend: MemoryBackend) -> None:
        child = Store(backend=backend, root_path="data").child("reports")
        child.write("report.txt", b"contents")
        infos = list(child.list_files(""))
        assert len(infos) == 1
        assert child.read_bytes(str(infos[0].path)) == b"contents"


class TestChildThreadSafety:
    """CHILD-010: Thread safety.

    Concurrent ``child()`` on one parent Store. CHILD-010 inherits STORE-007's
    share-across-threads guarantee; the backend-level generalisation lives in
    the BK-289 concurrency lane (``tests/backends/conformance/test_concurrency.py``).
    """

    @pytest.mark.spec("CHILD-010")
    def test_concurrent_child_creation(self, backend: MemoryBackend) -> None:
        parent = Store(backend=backend, root_path="data")
        results: list[Store] = []
        errors: list[Exception] = []

        def create_child(name: str) -> None:
            try:
                results.append(parent.child(name))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=create_child, args=(f"t{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 10
