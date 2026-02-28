"""Tests for remote_store.ext.batch — batch delete, copy, and exists."""

from __future__ import annotations

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    NotFound,
    RemoteStoreError,
)
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.batch import BatchResult, batch_copy, batch_delete, batch_exists

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store() -> Store:
    """Return a Store backed by MemoryBackend."""
    return Store(backend=MemoryBackend())


def _populated_store(*paths: str) -> Store:
    """Return a Store with files written at the given paths."""
    store = _make_store()
    for p in paths:
        store.write(p, b"data")
    return store


class _NoCopyBackend(MemoryBackend):
    """MemoryBackend with COPY capability removed."""

    @property
    def capabilities(self) -> CapabilitySet:
        caps = set(super().capabilities._caps)
        caps.discard(Capability.COPY)
        return CapabilitySet(frozenset(caps))


class _NoDeleteBackend(MemoryBackend):
    """MemoryBackend with DELETE capability removed."""

    @property
    def capabilities(self) -> CapabilitySet:
        caps = set(super().capabilities._caps)
        caps.discard(Capability.DELETE)
        return CapabilitySet(frozenset(caps))


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
    def test_all_succeeded_true(self) -> None:
        r = BatchResult(succeeded=("a", "b"), failed={})
        assert r.all_succeeded is True

    @pytest.mark.spec("BATCH-001")
    def test_all_succeeded_false(self) -> None:
        r = BatchResult(succeeded=("a",), failed={"b": NotFound("b")})
        assert r.all_succeeded is False

    @pytest.mark.spec("BATCH-001")
    def test_total(self) -> None:
        r = BatchResult(succeeded=("a",), failed={"b": NotFound("b")})
        assert r.total == 2

    @pytest.mark.spec("BATCH-001")
    def test_total_empty(self) -> None:
        r = BatchResult(succeeded=(), failed={})
        assert r.total == 0


# ===========================================================================
# BATCH-002 through BATCH-007: batch_delete
# ===========================================================================


class TestBatchDelete:
    @pytest.mark.spec("BATCH-002")
    def test_signature_returns_batch_result(self) -> None:
        store = _make_store()
        result = batch_delete(store, [])
        assert isinstance(result, BatchResult)

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
        # b.txt does not exist → NotFound collected, c.txt still deleted
        result = batch_delete(store, ["a.txt", "b.txt", "c.txt"])
        assert "a.txt" in result.succeeded
        assert "c.txt" in result.succeeded
        assert "b.txt" in result.failed
        assert isinstance(result.failed["b.txt"], NotFound)

    @pytest.mark.spec("BATCH-004")
    def test_error_collection_multiple_failures(self) -> None:
        store = _make_store()
        result = batch_delete(store, ["x.txt", "y.txt"])
        assert len(result.failed) == 2
        assert result.succeeded == ()

    @pytest.mark.spec("BATCH-005")
    def test_stop_on_error(self) -> None:
        store = _populated_store("a.txt", "c.txt")
        # b.txt missing → error → stop → c.txt never attempted
        result = batch_delete(store, ["a.txt", "b.txt", "c.txt"], stop_on_error=True)
        assert result.succeeded == ("a.txt",)
        assert "b.txt" in result.failed
        assert result.total == 2  # a succeeded, b failed, c not attempted
        assert store.exists("c.txt")  # c was never touched

    @pytest.mark.spec("BATCH-006")
    def test_missing_ok(self) -> None:
        store = _populated_store("a.txt")
        result = batch_delete(store, ["a.txt", "gone.txt"], missing_ok=True)
        assert result.all_succeeded
        assert result.succeeded == ("a.txt", "gone.txt")

    @pytest.mark.spec("BATCH-006")
    def test_missing_ok_false_default(self) -> None:
        store = _make_store()
        result = batch_delete(store, ["nope.txt"])
        assert not result.all_succeeded
        assert isinstance(result.failed["nope.txt"], NotFound)

    @pytest.mark.spec("BATCH-007")
    def test_empty_paths(self) -> None:
        store = _make_store()
        result = batch_delete(store, [])
        assert result.succeeded == ()
        assert result.failed == {}
        assert result.total == 0


# ===========================================================================
# BATCH-008 through BATCH-013: batch_copy
# ===========================================================================


class TestBatchCopy:
    @pytest.mark.spec("BATCH-008")
    def test_signature_returns_batch_result(self) -> None:
        store = _make_store()
        result = batch_copy(store, [])
        assert isinstance(result, BatchResult)

    @pytest.mark.spec("BATCH-009")
    def test_sequential_copies_all(self) -> None:
        store = _populated_store("a.txt", "b.txt")
        result = batch_copy(store, [("a.txt", "a_copy.txt"), ("b.txt", "b_copy.txt")])
        assert result.all_succeeded
        assert store.read_bytes("a_copy.txt") == b"data"
        assert store.read_bytes("b_copy.txt") == b"data"

    @pytest.mark.spec("BATCH-010")
    def test_error_collection_continues(self) -> None:
        store = _populated_store("a.txt")
        # missing.txt doesn't exist → NotFound, a.txt copies fine
        result = batch_copy(store, [("missing.txt", "x.txt"), ("a.txt", "a2.txt")])
        assert "a.txt" in result.succeeded
        assert "missing.txt" in result.failed
        assert isinstance(result.failed["missing.txt"], NotFound)

    @pytest.mark.spec("BATCH-010")
    def test_error_collection_multiple_failures(self) -> None:
        store = _make_store()
        result = batch_copy(store, [("x.txt", "x2.txt"), ("y.txt", "y2.txt")])
        assert len(result.failed) == 2
        assert result.succeeded == ()

    @pytest.mark.spec("BATCH-011")
    def test_stop_on_error(self) -> None:
        store = _populated_store("b.txt")
        result = batch_copy(
            store,
            [("missing.txt", "x.txt"), ("b.txt", "b2.txt")],
            stop_on_error=True,
        )
        assert "missing.txt" in result.failed
        assert result.total == 1  # only the failure
        assert not store.exists("b2.txt")  # b was never attempted

    @pytest.mark.spec("BATCH-012")
    def test_overwrite_false_default(self) -> None:
        store = _populated_store("src.txt", "dst.txt")
        result = batch_copy(store, [("src.txt", "dst.txt")])
        assert not result.all_succeeded
        assert isinstance(result.failed["src.txt"], AlreadyExists)

    @pytest.mark.spec("BATCH-012")
    def test_overwrite_true(self) -> None:
        store = _populated_store("src.txt", "dst.txt")
        result = batch_copy(store, [("src.txt", "dst.txt")], overwrite=True)
        assert result.all_succeeded

    @pytest.mark.spec("BATCH-013")
    def test_empty_pairs(self) -> None:
        store = _make_store()
        result = batch_copy(store, [])
        assert result.succeeded == ()
        assert result.failed == {}
        assert result.total == 0


# ===========================================================================
# BATCH-014 through BATCH-017: batch_exists
# ===========================================================================


class TestBatchExists:
    @pytest.mark.spec("BATCH-014")
    def test_signature_returns_dict(self) -> None:
        store = _make_store()
        result = batch_exists(store, [])
        assert isinstance(result, dict)

    @pytest.mark.spec("BATCH-015")
    def test_sequential_checks(self) -> None:
        store = _populated_store("a.txt", "b.txt")
        result = batch_exists(store, ["a.txt", "b.txt", "c.txt"])
        assert result == {"a.txt": True, "b.txt": True, "c.txt": False}

    @pytest.mark.spec("BATCH-015")
    def test_all_exist(self) -> None:
        store = _populated_store("x.txt")
        result = batch_exists(store, ["x.txt"])
        assert result == {"x.txt": True}

    @pytest.mark.spec("BATCH-015")
    def test_none_exist(self) -> None:
        store = _make_store()
        result = batch_exists(store, ["nope.txt"])
        assert result == {"nope.txt": False}

    @pytest.mark.spec("BATCH-016")
    def test_error_propagates(self) -> None:
        """Backend errors in exists() propagate immediately."""
        store = _make_store()
        # Patch store.exists to raise
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
        store = _make_store()
        result = batch_exists(store, [])
        assert result == {}


# ===========================================================================
# BATCH-018: No backend coupling
# ===========================================================================


class TestNoBackendCoupling:
    @pytest.mark.spec("BATCH-018")
    def test_works_with_child_store(self) -> None:
        """Batch functions work through Store.child() — proving no _backend access."""
        store = _populated_store("sub/a.txt", "sub/b.txt")
        child = store.child("sub")

        # batch_exists through child
        exists = batch_exists(child, ["a.txt", "b.txt", "c.txt"])
        assert exists == {"a.txt": True, "b.txt": True, "c.txt": False}

        # batch_copy through child
        result = batch_copy(child, [("a.txt", "a_copy.txt")])
        assert result.all_succeeded
        assert child.read_bytes("a_copy.txt") == b"data"

        # batch_delete through child
        result = batch_delete(child, ["a.txt", "b.txt"])
        assert result.all_succeeded
        assert not child.exists("a.txt")


# ===========================================================================
# BATCH-019: Capability gating propagation
# ===========================================================================


class TestCapabilityGating:
    @pytest.mark.spec("BATCH-019")
    def test_delete_capability_not_supported_propagates(self) -> None:
        store = Store(backend=_NoDeleteBackend())
        store.write("a.txt", b"data")
        with pytest.raises(CapabilityNotSupported):
            batch_delete(store, ["a.txt"])

    @pytest.mark.spec("BATCH-019")
    def test_delete_capability_ignores_stop_on_error(self) -> None:
        """CapabilityNotSupported propagates even with stop_on_error=False."""
        store = Store(backend=_NoDeleteBackend())
        store.write("a.txt", b"data")
        with pytest.raises(CapabilityNotSupported):
            batch_delete(store, ["a.txt"], stop_on_error=False)

    @pytest.mark.spec("BATCH-019")
    def test_copy_capability_not_supported_propagates(self) -> None:
        store = Store(backend=_NoCopyBackend())
        store.write("a.txt", b"data")
        with pytest.raises(CapabilityNotSupported):
            batch_copy(store, [("a.txt", "b.txt")])

    @pytest.mark.spec("BATCH-019")
    def test_copy_capability_ignores_stop_on_error(self) -> None:
        """CapabilityNotSupported propagates even with stop_on_error=False."""
        store = Store(backend=_NoCopyBackend())
        store.write("a.txt", b"data")
        with pytest.raises(CapabilityNotSupported):
            batch_copy(store, [("a.txt", "b.txt")], stop_on_error=False)


# ===========================================================================
# Module exports
# ===========================================================================


class TestModuleExports:
    def test_all_exports(self) -> None:
        from remote_store.ext import batch

        assert set(batch.__all__) == {
            "BatchResult",
            "batch_copy",
            "batch_delete",
            "batch_exists",
        }

    def test_top_level_import(self) -> None:
        """Batch exports are available from the top-level package."""
        from remote_store import BatchResult, batch_copy, batch_delete, batch_exists

        assert BatchResult is not None
        assert batch_delete is not None
        assert batch_copy is not None
        assert batch_exists is not None
