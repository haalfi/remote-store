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
# Helpers & fixtures
# ---------------------------------------------------------------------------

_FILES_ABC = ("a.txt", "b.txt", "c.txt")
_CONCURRENT = [pytest.param(False, id="sequential"), pytest.param(True, id="concurrent")]
_EMPTY_BR = lambda r: r.succeeded == () and r.failed == {} and r.total == 0  # noqa: E731


def _fresh(files: tuple[str, ...] = ()) -> Store:
    s = Store(backend=MemoryBackend())
    for f in files:
        s.write(f, b"data")
    return s


@pytest.fixture
def store() -> Store:
    return _fresh()


@pytest.fixture
def populated(store: Store) -> Store:
    for p in _FILES_ABC:
        store.write(p, b"data")
    return store


# ---------------------------------------------------------------------------
# BATCH-001: BatchResult dataclass
# ---------------------------------------------------------------------------


class TestBatchResult:
    @pytest.mark.spec("BATCH-001")
    def test_frozen(self) -> None:
        r = BatchResult(succeeded=("a",), failed={})
        with pytest.raises(AttributeError):
            r.succeeded = ("b",)  # type: ignore[misc]

    @pytest.mark.spec("BATCH-001")
    @pytest.mark.parametrize(
        ("succeeded", "failed", "expected_all", "expected_total"),
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


# ---------------------------------------------------------------------------
# BATCH-002: Signature / return types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("func", "args", "expected_type"),
    [
        pytest.param(batch_delete, [], BatchResult, id="delete"),
        pytest.param(batch_copy, [], BatchResult, id="copy"),
        pytest.param(batch_exists, [], dict, id="exists"),
    ],
)
@pytest.mark.spec("BATCH-002")
def test_signature_returns_type(
    store: Store,
    func: Any,
    args: list[Any],
    expected_type: type,
) -> None:
    result = func(store, args)
    assert isinstance(result, expected_type)
    if isinstance(result, BatchResult):
        assert result.all_succeeded is True
        assert result.total == 0
    elif isinstance(result, dict):
        assert result == {}


# ---------------------------------------------------------------------------
# BATCH-003 / BATCH-009: Success paths
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-003")
@pytest.mark.parametrize("concurrent", _CONCURRENT)
def test_delete_all(populated: Store, concurrent: bool) -> None:
    result = batch_delete(populated, list(_FILES_ABC), concurrent=concurrent)
    assert set(result.succeeded) == set(_FILES_ABC)
    assert result.all_succeeded
    for p in _FILES_ABC:
        assert not populated.exists(p)


@pytest.mark.spec("BATCH-009")
@pytest.mark.parametrize("concurrent", _CONCURRENT)
def test_copy_all(concurrent: bool) -> None:
    s = _fresh(("a.txt", "b.txt"))
    result = batch_copy(
        s,
        [("a.txt", "a_copy.txt"), ("b.txt", "b_copy.txt")],
        concurrent=concurrent,
    )
    assert result.all_succeeded
    assert s.read_bytes("a_copy.txt") == s.read_bytes("b_copy.txt") == b"data"


# ---------------------------------------------------------------------------
# BATCH-004 / BATCH-010: Error collection (continues on failure)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("concurrent", _CONCURRENT)
@pytest.mark.parametrize(
    ("func_factory", "expected_ok", "expected_fail_key"),
    [
        pytest.param(
            lambda: (batch_delete, _fresh(("a.txt", "c.txt")), ["a.txt", "b.txt", "c.txt"]),
            {"a.txt", "c.txt"},
            "b.txt",
            id="delete_continues",
        ),
        pytest.param(
            lambda: (batch_copy, _fresh(("a.txt",)), [("missing.txt", "x.txt"), ("a.txt", "a2.txt")]),
            {"a.txt"},
            "missing.txt",
            id="copy_continues",
        ),
    ],
)
@pytest.mark.spec("BATCH-004")
def test_error_continues(
    concurrent: bool,
    func_factory: Any,
    expected_ok: set[str],
    expected_fail_key: str,
) -> None:
    func, s, args = func_factory()
    result = func(s, args, concurrent=concurrent)
    assert set(result.succeeded) == expected_ok
    assert isinstance(result.failed[expected_fail_key], NotFound)


@pytest.mark.parametrize("concurrent", _CONCURRENT)
@pytest.mark.parametrize(
    ("func", "args"),
    [
        pytest.param(batch_delete, ["x.txt", "y.txt"], id="delete"),
        pytest.param(batch_copy, [("x.txt", "x2.txt"), ("y.txt", "y2.txt")], id="copy"),
    ],
)
@pytest.mark.spec("BATCH-004")
def test_multiple_failures(store: Store, func: Any, args: list[Any], concurrent: bool) -> None:
    result = func(store, args, concurrent=concurrent)
    assert len(result.failed) == 2
    assert result.succeeded == ()


# ---------------------------------------------------------------------------
# BATCH-005 / BATCH-011 / BATCH-022: stop_on_error
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-005")
def test_delete_stop() -> None:
    s = _fresh(("a.txt", "c.txt"))
    result = batch_delete(s, ["a.txt", "b.txt", "c.txt"], stop_on_error=True)
    assert result.succeeded == ("a.txt",)
    assert "b.txt" in result.failed
    assert result.total == 2
    assert s.exists("c.txt")


@pytest.mark.spec("BATCH-011")
def test_copy_stop() -> None:
    s = _fresh(("b.txt",))
    result = batch_copy(s, [("missing.txt", "x.txt"), ("b.txt", "b2.txt")], stop_on_error=True)
    assert "missing.txt" in result.failed
    assert result.total == 1
    assert not s.exists("b2.txt")


@pytest.mark.spec("BATCH-022")
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda s: batch_delete(s, ["a.txt"], concurrent=True, stop_on_error=True), id="delete"),
        pytest.param(lambda s: batch_copy(s, [("a.txt", "b.txt")], concurrent=True, stop_on_error=True), id="copy"),
    ],
)
def test_concurrent_stop_on_error_raises(store: Store, call: Any) -> None:
    with pytest.raises(ValueError, match="stop_on_error"):
        call(store)


# ---------------------------------------------------------------------------
# BATCH-006 / BATCH-020: missing_ok
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-006")
def test_missing_ok_false() -> None:
    s = _fresh(("a.txt",))
    result = batch_delete(s, ["nope.txt"], missing_ok=False)
    assert not result.all_succeeded
    assert isinstance(result.failed["nope.txt"], NotFound)


@pytest.mark.spec("BATCH-020")
@pytest.mark.parametrize("concurrent", _CONCURRENT)
def test_delete_missing_ok(concurrent: bool) -> None:
    s = _fresh(("a.txt",))
    result = batch_delete(s, ["a.txt", "gone.txt"], missing_ok=True, concurrent=concurrent)
    assert result.all_succeeded
    assert set(result.succeeded) == {"a.txt", "gone.txt"}


# ---------------------------------------------------------------------------
# BATCH-007: Empty paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("concurrent", _CONCURRENT)
@pytest.mark.parametrize(
    ("func", "args", "check"),
    [
        pytest.param(batch_delete, [], _EMPTY_BR, id="delete"),
        pytest.param(batch_copy, [], _EMPTY_BR, id="copy"),
        pytest.param(batch_exists, [], lambda r: r == {}, id="exists"),
    ],
)
@pytest.mark.spec("BATCH-007")
def test_empty_paths(store: Store, func: Any, args: list[Any], check: Any, concurrent: bool) -> None:
    assert check(func(store, args, concurrent=concurrent))


# ---------------------------------------------------------------------------
# BATCH-012: Overwrite for copy
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-012")
@pytest.mark.parametrize(
    ("overwrite", "concurrent"),
    [
        pytest.param(False, False, id="no_overwrite"),
        pytest.param(True, False, id="overwrite"),
        pytest.param(True, True, id="overwrite_concurrent"),
    ],
)
def test_copy_overwrite(overwrite: bool, concurrent: bool) -> None:
    s = _fresh(("src.txt", "dst.txt"))
    result = batch_copy(s, [("src.txt", "dst.txt")], overwrite=overwrite, concurrent=concurrent)
    if overwrite:
        assert result.all_succeeded
    else:
        assert isinstance(result.failed["src.txt"], AlreadyExists)


# ---------------------------------------------------------------------------
# BATCH-015 / BATCH-020: batch_exists
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-015")
@pytest.mark.parametrize(
    ("files", "paths", "expected"),
    [
        (["a.txt", "b.txt"], ["a.txt", "b.txt", "c.txt"], {"a.txt": True, "b.txt": True, "c.txt": False}),
        (["x.txt"], ["x.txt"], {"x.txt": True}),
        ([], ["nope.txt"], {"nope.txt": False}),
    ],
    ids=["mixed", "all_exist", "none_exist"],
)
def test_exists_checks(files: list[str], paths: list[str], expected: dict[str, bool]) -> None:
    assert batch_exists(_fresh(tuple(files)), paths) == expected


@pytest.mark.spec("BATCH-020")
def test_exists_concurrent() -> None:
    assert batch_exists(_fresh(("a.txt", "b.txt")), ["a.txt", "b.txt", "c.txt"], concurrent=True) == {
        "a.txt": True,
        "b.txt": True,
        "c.txt": False,
    }


# ---------------------------------------------------------------------------
# BATCH-016: batch_exists error propagation
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-016")
@pytest.mark.parametrize("concurrent", _CONCURRENT)
def test_exists_error_propagates(store: Store, concurrent: bool) -> None:
    original_exists = store.exists

    def boom(path: str) -> bool:
        if path == "bad":
            raise RemoteStoreError("backend failure")
        return original_exists(path)

    store.exists = boom  # type: ignore[assignment]
    with pytest.raises(RemoteStoreError, match="backend failure"):
        batch_exists(store, ["ok.txt", "bad"], **{"concurrent": True} if concurrent else {})


# ---------------------------------------------------------------------------
# BATCH-018: child store
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-018")
@pytest.mark.parametrize("concurrent", _CONCURRENT)
def test_child_store(concurrent: bool) -> None:
    child = _fresh(("sub/a.txt", "sub/b.txt")).child("sub")
    kw: dict[str, Any] = {"concurrent": True} if concurrent else {}
    assert batch_exists(child, ["a.txt", "b.txt", "c.txt"], **kw) == {
        "a.txt": True,
        "b.txt": True,
        "c.txt": False,
    }
    assert batch_copy(child, [("a.txt", "a_copy.txt")], **kw).all_succeeded
    assert batch_delete(child, ["a.txt", "b.txt"], **kw).all_succeeded
    assert not child.exists("a.txt")


# ---------------------------------------------------------------------------
# BATCH-019: Capability gating
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-019")
@pytest.mark.parametrize(
    ("excluded_cap", "call"),
    [
        pytest.param(Capability.DELETE, lambda s: batch_delete(s, ["a.txt"]), id="delete"),
        pytest.param(Capability.DELETE, lambda s: batch_delete(s, ["a.txt"], stop_on_error=False), id="delete_no_stop"),
        pytest.param(Capability.COPY, lambda s: batch_copy(s, [("a.txt", "b.txt")]), id="copy"),
        pytest.param(
            Capability.COPY, lambda s: batch_copy(s, [("a.txt", "b.txt")], stop_on_error=False), id="copy_no_stop"
        ),
        pytest.param(Capability.DELETE, lambda s: batch_delete(s, ["a.txt"], concurrent=True), id="delete_concurrent"),
        pytest.param(
            Capability.COPY, lambda s: batch_copy(s, [("a.txt", "b.txt")], concurrent=True), id="copy_concurrent"
        ),
    ],
)
def test_capability_gating(excluded_cap: Capability, call: Any) -> None:
    backend = MemoryBackend()
    backend.write("a.txt", b"data")
    restricted = RestrictedBackend(backend, exclude={excluded_cap})
    with pytest.raises(CapabilityNotSupported):
        call(Store(backend=restricted, root_path=""))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# BATCH-021: max_workers
# ---------------------------------------------------------------------------


@pytest.mark.spec("BATCH-021")
@pytest.mark.parametrize(
    ("func", "setup", "args"),
    [
        pytest.param(batch_delete, ("a.txt", "b.txt"), ["a.txt", "b.txt"], id="delete"),
        pytest.param(batch_copy, ("a.txt",), [("a.txt", "a2.txt")], id="copy"),
        pytest.param(batch_exists, ("a.txt",), ["a.txt"], id="exists"),
    ],
)
def test_max_workers(func: Any, setup: tuple[str, ...], args: list[Any]) -> None:
    result = func(_fresh(setup), args, concurrent=True, max_workers=1)
    if isinstance(result, dict):
        assert result == {"a.txt": True}
    else:
        assert result.all_succeeded


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


def test_module_exports() -> None:
    from remote_store.ext import batch

    assert set(batch.__all__) == {"BatchResult", "batch_copy", "batch_delete", "batch_exists"}
    from remote_store import BatchResult as BR
    from remote_store import batch_copy as bc
    from remote_store import batch_delete as bd
    from remote_store import batch_exists as be

    assert all(x is not None for x in (BR, bd, bc, be))
