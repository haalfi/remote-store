"""Tests for remote_store.ext.batch -- batch delete, copy, and exists."""

from __future__ import annotations

from typing import Any

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    NotFound,
    RemoteStoreError,
)
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.batch import BatchResult, batch_copy, batch_delete, batch_exists

from .conftest import RestrictedBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store() -> Store:
    return Store(backend=MemoryBackend())


def _populated_store(*paths: str) -> Store:
    store = _make_store()
    for p in paths:
        store.write(p, b"data")
    return store


# ===========================================================================
# BATCH-001: BatchResult dataclass
# ===========================================================================


class TestBatchResult:
    @pytest.mark.spec("BATCH-001")
    def test_frozen(self) -> None:
        r = BatchResult(succeeded=("a",), failed={})
        with pytest.raises(AttributeError):
            r.succeeded = ("b",)  # type: ignore[misc]

    @pytest.mark.spec("BATCH-001")
    @pytest.mark.parametrize(
        "succeeded,failed,expected_all,expected_total",
        [
            (("a", "b"), {}, True, 2),
            (("a",), {"b": NotFound("b")}, False, 2),
            ((), {}, True, 0),
        ],
        ids=["all_ok", "one_failed", "empty"],
    )
    def test_properties(
        self,
        succeeded: tuple[str, ...],
        failed: dict[str, Exception],
        expected_all: bool,
        expected_total: int,
    ) -> None:
        r = BatchResult(succeeded=succeeded, failed=failed)
        assert r.all_succeeded is expected_all
        assert r.total == expected_total


# ===========================================================================
# BATCH-002 through BATCH-007: batch_delete
# ===========================================================================


class TestBatchDelete:
    @pytest.mark.spec("BATCH-002")
    def test_signature_returns_batch_result(self) -> None:
        assert isinstance(batch_delete(_make_store(), []), BatchResult)

    @pytest.mark.spec("BATCH-003")
    def test_sequential_deletes_all(self) -> None:
        store = _populated_store("a.txt", "b.txt", "c.txt")
        result = batch_delete(store, ["a.txt", "b.txt", "c.txt"])
        assert result.succeeded == ("a.txt", "b.txt", "c.txt")
        assert result.all_succeeded
        for p in ("a.txt", "b.txt", "c.txt"):
            assert not store.exists(p)

    @pytest.mark.spec("BATCH-004")
    def test_error_collection_continues(self) -> None:
        store = _populated_store("a.txt", "c.txt")
        result = batch_delete(store, ["a.txt", "b.txt", "c.txt"])
        assert "a.txt" in result.succeeded and "c.txt" in result.succeeded
        assert isinstance(result.failed["b.txt"], NotFound)

    @pytest.mark.spec("BATCH-004")
    def test_error_collection_multiple_failures(self) -> None:
        result = batch_delete(_make_store(), ["x.txt", "y.txt"])
        assert len(result.failed) == 2 and result.succeeded == ()

    @pytest.mark.spec("BATCH-005")
    def test_stop_on_error(self) -> None:
        store = _populated_store("a.txt", "c.txt")
        result = batch_delete(store, ["a.txt", "b.txt", "c.txt"], stop_on_error=True)
        assert result.succeeded == ("a.txt",)
        assert "b.txt" in result.failed
        assert result.total == 2
        assert store.exists("c.txt")

    @pytest.mark.spec("BATCH-006")
    def test_missing_ok_true(self) -> None:
        store = _populated_store("a.txt")
        result = batch_delete(store, ["a.txt", "gone.txt"], missing_ok=True)
        assert result.all_succeeded
        assert result.succeeded == ("a.txt", "gone.txt")

    @pytest.mark.spec("BATCH-006")
    def test_missing_ok_false(self) -> None:
        store = _populated_store("a.txt")
        result = batch_delete(store, ["nope.txt"], missing_ok=False)
        assert not result.all_succeeded
        assert isinstance(result.failed["nope.txt"], NotFound)

    @pytest.mark.spec("BATCH-007")
    def test_empty_paths(self) -> None:
        result = batch_delete(_make_store(), [])
        assert result.succeeded == () and result.failed == {} and result.total == 0


# ===========================================================================
# BATCH-008 through BATCH-013: batch_copy
# ===========================================================================


class TestBatchCopy:
    @pytest.mark.spec("BATCH-008")
    def test_signature_returns_batch_result(self) -> None:
        assert isinstance(batch_copy(_make_store(), []), BatchResult)

    @pytest.mark.spec("BATCH-009")
    def test_sequential_copies_all(self) -> None:
        store = _populated_store("a.txt", "b.txt")
        result = batch_copy(store, [("a.txt", "a_copy.txt"), ("b.txt", "b_copy.txt")])
        assert result.all_succeeded
        assert store.read_bytes("a_copy.txt") == b"data"

    @pytest.mark.spec("BATCH-010")
    def test_error_collection_continues(self) -> None:
        store = _populated_store("a.txt")
        result = batch_copy(store, [("missing.txt", "x.txt"), ("a.txt", "a2.txt")])
        assert "a.txt" in result.succeeded
        assert isinstance(result.failed["missing.txt"], NotFound)

    @pytest.mark.spec("BATCH-010")
    def test_error_collection_multiple_failures(self) -> None:
        result = batch_copy(_make_store(), [("x.txt", "x2.txt"), ("y.txt", "y2.txt")])
        assert len(result.failed) == 2 and result.succeeded == ()

    @pytest.mark.spec("BATCH-011")
    def test_stop_on_error(self) -> None:
        store = _populated_store("b.txt")
        result = batch_copy(store, [("missing.txt", "x.txt"), ("b.txt", "b2.txt")], stop_on_error=True)
        assert "missing.txt" in result.failed and result.total == 1
        assert not store.exists("b2.txt")

    @pytest.mark.spec("BATCH-012")
    @pytest.mark.parametrize("overwrite", [False, True], ids=["no_overwrite", "overwrite"])
    def test_overwrite(self, overwrite: bool) -> None:
        store = _populated_store("src.txt", "dst.txt")
        result = batch_copy(store, [("src.txt", "dst.txt")], overwrite=overwrite)
        if overwrite:
            assert result.all_succeeded
        else:
            assert isinstance(result.failed["src.txt"], AlreadyExists)

    @pytest.mark.spec("BATCH-013")
    def test_empty_pairs(self) -> None:
        result = batch_copy(_make_store(), [])
        assert result.succeeded == () and result.failed == {} and result.total == 0


# ===========================================================================
# BATCH-014 through BATCH-017: batch_exists
# ===========================================================================


class TestBatchExists:
    @pytest.mark.spec("BATCH-014")
    def test_signature_returns_dict(self) -> None:
        assert isinstance(batch_exists(_make_store(), []), dict)

    @pytest.mark.spec("BATCH-015")
    @pytest.mark.parametrize(
        "files,paths,expected",
        [
            (["a.txt", "b.txt"], ["a.txt", "b.txt", "c.txt"], {"a.txt": True, "b.txt": True, "c.txt": False}),
            (["x.txt"], ["x.txt"], {"x.txt": True}),
            ([], ["nope.txt"], {"nope.txt": False}),
        ],
        ids=["mixed", "all_exist", "none_exist"],
    )
    def test_checks(self, files: list[str], paths: list[str], expected: dict[str, bool]) -> None:
        store = _populated_store(*files) if files else _make_store()
        assert batch_exists(store, paths) == expected

    @pytest.mark.spec("BATCH-016")
    def test_error_propagates(self) -> None:
        store = _make_store()
        original_exists = store.exists

        def boom(path: str) -> bool:
            if path == "bad":
                raise RemoteStoreError("backend failure")
            return original_exists(path)

        store.exists = boom  # type: ignore[assignment]
        with pytest.raises(RemoteStoreError, match="backend failure"):
            batch_exists(store, ["ok.txt", "bad"])

    @pytest.mark.spec("BATCH-017")
    def test_empty_paths(self) -> None:
        assert batch_exists(_make_store(), []) == {}


# ===========================================================================
# BATCH-018: No backend coupling
# ===========================================================================


class TestNoBackendCoupling:
    @pytest.mark.spec("BATCH-018")
    def test_works_with_child_store(self) -> None:
        store = _populated_store("sub/a.txt", "sub/b.txt")
        child = store.child("sub")
        assert batch_exists(child, ["a.txt", "b.txt", "c.txt"]) == {"a.txt": True, "b.txt": True, "c.txt": False}
        assert batch_copy(child, [("a.txt", "a_copy.txt")]).all_succeeded
        assert batch_delete(child, ["a.txt", "b.txt"]).all_succeeded
        assert not child.exists("a.txt")


# ===========================================================================
# BATCH-019: Capability gating propagation
# ===========================================================================

_CAP_GATING_CASES = [
    pytest.param(
        Capability.DELETE,
        lambda s: batch_delete(s, ["a.txt"]),
        id="delete",
    ),
    pytest.param(
        Capability.DELETE,
        lambda s: batch_delete(s, ["a.txt"], stop_on_error=False),
        id="delete_no_stop",
    ),
    pytest.param(
        Capability.COPY,
        lambda s: batch_copy(s, [("a.txt", "b.txt")]),
        id="copy",
    ),
    pytest.param(
        Capability.COPY,
        lambda s: batch_copy(s, [("a.txt", "b.txt")], stop_on_error=False),
        id="copy_no_stop",
    ),
]


@pytest.mark.spec("BATCH-019")
@pytest.mark.parametrize("excluded_cap,call", _CAP_GATING_CASES)
def test_capability_gating(excluded_cap: Capability, call: Any) -> None:
    backend = MemoryBackend()
    backend.write("a.txt", b"data")
    restricted = RestrictedBackend(backend, exclude={excluded_cap})
    store = Store(backend=restricted, root_path="")  # type: ignore[arg-type]
    with pytest.raises(CapabilityNotSupported):
        call(store)


# ===========================================================================
# BATCH-020 through BATCH-025: Concurrent execution (ID-035)
# ===========================================================================


class TestConcurrentDelete:
    @pytest.mark.spec("BATCH-020")
    def test_concurrent_deletes_all(self) -> None:
        store = _populated_store("a.txt", "b.txt", "c.txt")
        result = batch_delete(store, ["a.txt", "b.txt", "c.txt"], concurrent=True)
        assert result.all_succeeded
        assert set(result.succeeded) == {"a.txt", "b.txt", "c.txt"}
        for p in ("a.txt", "b.txt", "c.txt"):
            assert not store.exists(p)

    @pytest.mark.spec("BATCH-024")
    def test_concurrent_error_collection(self) -> None:
        store = _populated_store("a.txt", "c.txt")
        result = batch_delete(store, ["a.txt", "b.txt", "c.txt"], concurrent=True)
        assert set(result.succeeded) == {"a.txt", "c.txt"}
        assert isinstance(result.failed["b.txt"], NotFound)

    @pytest.mark.spec("BATCH-022")
    def test_concurrent_stop_on_error_raises(self) -> None:
        with pytest.raises(ValueError, match="stop_on_error"):
            batch_delete(_make_store(), ["a.txt"], concurrent=True, stop_on_error=True)

    @pytest.mark.spec("BATCH-020")
    def test_concurrent_missing_ok(self) -> None:
        store = _populated_store("a.txt")
        result = batch_delete(store, ["a.txt", "gone.txt"], missing_ok=True, concurrent=True)
        assert result.all_succeeded
        assert set(result.succeeded) == {"a.txt", "gone.txt"}

    @pytest.mark.spec("BATCH-025")
    def test_concurrent_empty(self) -> None:
        result = batch_delete(_make_store(), [], concurrent=True)
        assert result.succeeded == () and result.failed == {} and result.total == 0

    @pytest.mark.spec("BATCH-021")
    def test_concurrent_max_workers(self) -> None:
        store = _populated_store("a.txt", "b.txt")
        result = batch_delete(store, ["a.txt", "b.txt"], concurrent=True, max_workers=1)
        assert result.all_succeeded


class TestConcurrentCopy:
    @pytest.mark.spec("BATCH-020")
    def test_concurrent_copies_all(self) -> None:
        store = _populated_store("a.txt", "b.txt")
        result = batch_copy(
            store,
            [("a.txt", "a_copy.txt"), ("b.txt", "b_copy.txt")],
            concurrent=True,
        )
        assert result.all_succeeded
        assert store.read_bytes("a_copy.txt") == b"data"
        assert store.read_bytes("b_copy.txt") == b"data"

    @pytest.mark.spec("BATCH-024")
    def test_concurrent_error_collection(self) -> None:
        store = _populated_store("a.txt")
        result = batch_copy(
            store,
            [("missing.txt", "x.txt"), ("a.txt", "a2.txt")],
            concurrent=True,
        )
        assert "a.txt" in result.succeeded
        assert isinstance(result.failed["missing.txt"], NotFound)

    @pytest.mark.spec("BATCH-022")
    def test_concurrent_stop_on_error_raises(self) -> None:
        with pytest.raises(ValueError, match="stop_on_error"):
            batch_copy(
                _make_store(),
                [("a.txt", "b.txt")],
                concurrent=True,
                stop_on_error=True,
            )

    @pytest.mark.spec("BATCH-020")
    def test_concurrent_overwrite(self) -> None:
        store = _populated_store("src.txt", "dst.txt")
        result = batch_copy(store, [("src.txt", "dst.txt")], overwrite=True, concurrent=True)
        assert result.all_succeeded

    @pytest.mark.spec("BATCH-025")
    def test_concurrent_empty(self) -> None:
        result = batch_copy(_make_store(), [], concurrent=True)
        assert result.succeeded == () and result.failed == {} and result.total == 0

    @pytest.mark.spec("BATCH-021")
    def test_concurrent_max_workers(self) -> None:
        store = _populated_store("a.txt")
        result = batch_copy(store, [("a.txt", "a2.txt")], concurrent=True, max_workers=1)
        assert result.all_succeeded


class TestConcurrentExists:
    @pytest.mark.spec("BATCH-020")
    def test_concurrent_checks(self) -> None:
        store = _populated_store("a.txt", "b.txt")
        result = batch_exists(store, ["a.txt", "b.txt", "c.txt"], concurrent=True)
        assert result == {"a.txt": True, "b.txt": True, "c.txt": False}

    @pytest.mark.spec("BATCH-024")
    def test_concurrent_error_propagates(self) -> None:
        store = _make_store()
        original_exists = store.exists

        def boom(path: str) -> bool:
            if path == "bad":
                raise RemoteStoreError("backend failure")
            return original_exists(path)

        store.exists = boom  # type: ignore[assignment]
        with pytest.raises(RemoteStoreError, match="backend failure"):
            batch_exists(store, ["ok.txt", "bad"], concurrent=True)

    @pytest.mark.spec("BATCH-025")
    def test_concurrent_empty(self) -> None:
        assert batch_exists(_make_store(), [], concurrent=True) == {}

    @pytest.mark.spec("BATCH-021")
    def test_concurrent_max_workers(self) -> None:
        store = _populated_store("a.txt")
        result = batch_exists(store, ["a.txt"], concurrent=True, max_workers=1)
        assert result == {"a.txt": True}


class TestConcurrentCapabilityGating:
    @pytest.mark.spec("BATCH-024")
    @pytest.mark.parametrize(
        "excluded_cap,call",
        [
            pytest.param(
                Capability.DELETE,
                lambda s: batch_delete(s, ["a.txt"], concurrent=True),
                id="delete_concurrent",
            ),
            pytest.param(
                Capability.COPY,
                lambda s: batch_copy(s, [("a.txt", "b.txt")], concurrent=True),
                id="copy_concurrent",
            ),
        ],
    )
    def test_capability_gating_concurrent(self, excluded_cap: Capability, call: Any) -> None:
        backend = MemoryBackend()
        backend.write("a.txt", b"data")
        restricted = RestrictedBackend(backend, exclude={excluded_cap})
        store = Store(backend=restricted, root_path="")  # type: ignore[arg-type]
        with pytest.raises(CapabilityNotSupported):
            call(store)


class TestConcurrentChildStore:
    @pytest.mark.spec("BATCH-018")
    def test_concurrent_with_child_store(self) -> None:
        store = _populated_store("sub/a.txt", "sub/b.txt")
        child = store.child("sub")
        assert batch_exists(child, ["a.txt", "b.txt", "c.txt"], concurrent=True) == {
            "a.txt": True,
            "b.txt": True,
            "c.txt": False,
        }
        assert batch_copy(child, [("a.txt", "a_copy.txt")], concurrent=True).all_succeeded
        assert batch_delete(child, ["a.txt", "b.txt"], concurrent=True).all_succeeded
        assert not child.exists("a.txt")


# ===========================================================================
# Module exports
# ===========================================================================


class TestModuleExports:
    def test_all_exports(self) -> None:
        from remote_store.ext import batch

        assert set(batch.__all__) == {"BatchResult", "batch_copy", "batch_delete", "batch_exists"}

    def test_top_level_import(self) -> None:
        from remote_store import BatchResult, batch_copy, batch_delete, batch_exists

        assert all(x is not None for x in (BatchResult, batch_delete, batch_copy, batch_exists))
