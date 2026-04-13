"""Tests for remote_store.ext.observe -- observability hooks."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import CapabilityNotSupported, NotFound
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend
from remote_store.ext.observe import (
    BufferedObserver,
    ObservedStore,
    StoreEvent,
    observe,
    set_correlation_id,
)

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


def _collect_events() -> tuple[list[StoreEvent], dict[str, Any]]:
    events: list[StoreEvent] = []
    return events, {"on_any": events.append}


def _make_event(**overrides: Any) -> StoreEvent:
    defaults = dict(
        operation="read",
        path="a.txt",
        backend="memory",
        started_at=0.0,
        duration_ms=1.0,
        error=None,
        metadata={},
        correlation_id=None,
    )
    defaults.update(overrides)
    return StoreEvent(**defaults)


# ---------------------------------------------------------------------------
# OBS-001: StoreEvent dataclass
# ---------------------------------------------------------------------------


class TestStoreEvent:
    @pytest.mark.spec("OBS-001")
    def test_store_event_is_frozen(self) -> None:
        event = _make_event()
        with pytest.raises(AttributeError):
            event.operation = "write"  # type: ignore[misc]

    @pytest.mark.spec("OBS-001")
    def test_store_event_fields(self) -> None:
        err = ValueError("boom")
        event = _make_event(
            operation="write",
            path="b.txt",
            backend="s3",
            started_at=100.0,
            duration_ms=5.5,
            error=err,
            metadata={"overwrite": True},
            correlation_id="abc-123",
        )
        assert event.operation == "write"
        assert event.path == "b.txt"
        assert event.backend == "s3"
        assert event.started_at == 100.0
        assert event.duration_ms == 5.5
        assert event.error is err
        assert event.metadata == {"overwrite": True}
        assert event.correlation_id == "abc-123"


# ---------------------------------------------------------------------------
# OBS-002: observe() factory
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-002")
def test_observe_returns_observed_store() -> None:
    store = _make_store()
    observed = observe(store)
    assert isinstance(observed, ObservedStore)
    assert isinstance(observed, Store)


@pytest.mark.spec("OBS-002")
def test_observe_inner_property() -> None:
    store = _make_store()
    assert observe(store).inner is store


# ---------------------------------------------------------------------------
# OBS-003: ObservedStore proxy -- hook-to-operation mapping (unified)
# ---------------------------------------------------------------------------

_ALL_HOOK_CASES = [
    # (hook, setup_files_or_fn, call, expected_op)
    pytest.param("on_write", [], lambda o: o.write("a.txt", b"hello"), "write", id="write"),
    pytest.param("on_read", ["a.txt"], lambda o: o.read("a.txt"), "read", id="read"),
    pytest.param("on_read", ["a.txt"], lambda o: o.read_bytes("a.txt"), "read_bytes", id="read_bytes"),
    pytest.param("on_read", ["a.txt"], lambda o: o.read_seekable("a.txt"), "read_seekable", id="read_seekable"),
    pytest.param("on_read", ["a.txt"], lambda o: o.read_text("a.txt"), "read_text", id="read_text"),
    pytest.param("on_write", [], lambda o: o.write_text("wt.txt", "hi"), "write_text", id="write_text"),
    pytest.param("on_delete", ["a.txt"], lambda o: o.delete("a.txt"), "delete", id="delete"),
    pytest.param("on_copy", ["a.txt"], lambda o: o.copy("a.txt", "b.txt"), "copy", id="copy"),
    pytest.param("on_move", ["a.txt"], lambda o: o.move("a.txt", "b.txt"), "move", id="move"),
    pytest.param("on_list", [], lambda o: o.exists("a.txt"), "exists", id="exists"),
    pytest.param("on_list", ["a.txt"], lambda o: list(o.list_files("")), "list_files", id="list_files"),
    pytest.param("on_list", ["a.txt"], lambda o: list(o.iter_children("")), "iter_children", id="iter_children"),
    pytest.param("on_write", [], lambda o: o.write_atomic("a.txt", b"atomic"), "write_atomic", id="write_atomic"),
    pytest.param(
        "on_delete",
        ["sub/a.txt"],
        lambda o: o.delete_folder("sub", recursive=True),
        "delete_folder",
        id="delete_folder",
    ),
    pytest.param("on_list", ["a.txt"], lambda o: o.get_file_info("a.txt"), "get_file_info", id="get_file_info"),
    pytest.param("on_list", [], lambda o: o.is_file("x"), "is_file", id="is_file"),
    pytest.param("on_list", [], lambda o: o.is_folder("x"), "is_folder", id="is_folder"),
]


@pytest.mark.spec("OBS-003")
@pytest.mark.parametrize(("hook", "setup_files", "call", "expected_op"), _ALL_HOOK_CASES)
def test_hook_fires_for_operation(
    hook: str,
    setup_files: list[str],
    call: Any,
    expected_op: str,
) -> None:
    store = _make_store()
    for f in setup_files:
        store.write(f, b"data")
    events: list[StoreEvent] = []
    observed = observe(store, **{hook: events.append})
    call(observed)
    assert len(events) == 1
    assert events[0].operation == expected_op


# ---------------------------------------------------------------------------
# OBS-003: Metadata dst for copy/move
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-003")
@pytest.mark.parametrize(
    ("hook", "op"),
    [
        pytest.param("on_copy", "copy", id="copy"),
        pytest.param("on_move", "move", id="move"),
    ],
)
def test_metadata_includes_dst(hook: str, op: str) -> None:
    store = _populated_store("a.txt")
    events: list[StoreEvent] = []
    observed = observe(store, **{hook: events.append})
    getattr(observed, op)("a.txt", "b.txt")
    assert events[0].metadata["dst"] == "b.txt"


# ---------------------------------------------------------------------------
# OBS-003: on_any, error events, proxy transparency, backend name
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-003")
def test_on_any_catches_all() -> None:
    store = _populated_store("a.txt")
    events, kwargs = _collect_events()
    observed = observe(store, **kwargs)
    observed.exists("a.txt")
    observed.read_bytes("a.txt")
    assert len(events) == 2
    assert events[0].operation == "exists"
    assert events[1].operation == "read_bytes"


@pytest.mark.spec("OBS-003")
def test_on_any_receives_error_events() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    with pytest.raises(NotFound):
        observed.read("nonexistent.txt")
    assert len(events) == 1
    assert events[0].error is not None
    assert events[0].operation == "read"


@pytest.mark.spec("WTXT-004")
def test_write_text_event_metadata() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_write=events.append)
    observed.write_text("wt.txt", "hello", encoding="latin-1", overwrite=True)
    assert len(events) == 1
    assert events[0].operation == "write_text"
    assert events[0].path == "wt.txt"
    assert events[0].metadata["encoding"] == "latin-1"
    assert events[0].metadata["overwrite"] is True


@pytest.mark.spec("OBS-003")
def test_proxy_does_not_modify_results() -> None:
    store = _populated_store("a.txt")
    observed = observe(store, on_any=lambda e: None)
    assert observed.read_bytes("a.txt") == b"data"
    assert observed.exists("a.txt") is True
    assert observed.is_file("a.txt") is True


@pytest.mark.spec("OBS-003")
@pytest.mark.parametrize(
    "hook_name",
    [
        pytest.param("on_write", id="per_op"),
        pytest.param("on_any", id="on_any"),
        pytest.param("on_error", id="on_error"),
    ],
)
def test_hook_exception_suppressed(hook_name: str) -> None:
    """Hook exceptions must not break the operation (OBS-009)."""
    store = _make_store()

    def bad_hook(event: StoreEvent) -> None:
        raise RuntimeError("hook boom")

    observed = observe(store, **{hook_name: bad_hook})
    if hook_name == "on_error":
        with pytest.raises(NotFound):
            observed.read("nonexistent.txt")
    else:
        observed.write("a.txt", b"hello")
        assert store.exists("a.txt")


@pytest.mark.spec("OBS-003")
def test_backend_name_in_event() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    observed.exists("x")
    assert events[0].backend == "memory"


# ---------------------------------------------------------------------------
# OBS-004: After-only hooks
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-004")
def test_hook_fires_after_operation() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_write=events.append)
    observed.write("a.txt", b"data")
    assert events[0].duration_ms >= 0.0
    assert events[0].error is None


# ---------------------------------------------------------------------------
# OBS-005: Around hook
# ---------------------------------------------------------------------------


class TestAroundHook:
    @pytest.mark.spec("OBS-005")
    def test_around_hook_wraps_operation(self) -> None:
        store = _make_store()
        order: list[str] = []

        @contextlib.contextmanager
        def around(op: str, path: str, backend: str) -> Iterator[None]:
            order.append(f"before-{op}")
            yield
            order.append(f"after-{op}")

        events: list[StoreEvent] = []
        observed = observe(store, on_any=events.append, around=around)
        observed.write("a.txt", b"data")
        assert order == ["before-write", "after-write"]
        assert len(events) == 1

    @pytest.mark.spec("OBS-005")
    def test_around_enter_raises_skips_operation(self) -> None:
        store = _make_store()

        @contextlib.contextmanager
        def bad_around(op: str, path: str, backend: str) -> Iterator[None]:
            raise RuntimeError("around __enter__ fail")
            yield  # pragma: no cover

        observed = observe(store, around=bad_around)
        with pytest.raises(RuntimeError, match="around __enter__ fail"):
            observed.write("a.txt", b"data")
        assert not store.exists("a.txt")


# ---------------------------------------------------------------------------
# OBS-006: BufferedObserver
# ---------------------------------------------------------------------------


class TestBufferedObserver:
    @pytest.mark.spec("OBS-006")
    def test_on_event_and_flush(self) -> None:
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, flush_interval=60.0)
        try:
            event = _make_event()
            observer.on_event(event)
            observer.flush()
            assert len(batches) == 1
            assert batches[0][0] is event
        finally:
            observer.close()

    @pytest.mark.spec("OBS-006")
    def test_close_flushes_remaining(self) -> None:
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, flush_interval=60.0)
        event = _make_event(operation="write", path="b.txt")
        observer.on_event(event)
        observer.close()
        all_events = [e for batch in batches for e in batch]
        assert event in all_events

    @pytest.mark.spec("OBS-006")
    def test_full_queue_drops_events(self) -> None:
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, max_queue=2, flush_interval=60.0)
        try:
            for i in range(5):
                observer.on_event(_make_event(path=f"file{i}.txt"))
            observer.flush()
            all_events = [e for batch in batches for e in batch]
            assert len(all_events) == 2
        finally:
            observer.close()

    @pytest.mark.spec("OBS-006")
    def test_integration_with_observed_store(self) -> None:
        store = _populated_store("a.txt")
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, flush_interval=60.0)
        try:
            observed = observe(store, on_any=observer.on_event)
            observed.read_bytes("a.txt")
            observer.flush()
            assert batches[0][0].operation == "read_bytes"
        finally:
            observer.close()

    @pytest.mark.spec("OBS-006")
    def test_on_event_after_close_is_noop(self) -> None:
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, flush_interval=60.0)
        observer.close()
        event = _make_event(path="late.txt")
        observer.on_event(event)
        all_events = [e for batch in batches for e in batch]
        assert event not in all_events


# ---------------------------------------------------------------------------
# OBS-007: Drift-protection test
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-007")
def test_observed_store_overrides_all_public_methods() -> None:
    """ObservedStore must override every public Store method itself."""
    store_public = {name for name, val in vars(Store).items() if not name.startswith("_") and callable(val)}
    overridden = set(vars(ObservedStore)) & store_public
    missing = store_public - overridden
    assert not missing, f"ObservedStore missing overrides for: {sorted(missing)}"


# ---------------------------------------------------------------------------
# OBS-008: Intrinsic logging
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-008")
def test_null_handler_registered() -> None:
    root_logger = logging.getLogger("remote_store")
    assert logging.NullHandler in [type(h) for h in root_logger.handlers]


@pytest.mark.spec("OBS-008")
def test_store_module_has_logger() -> None:
    from remote_store import _store

    assert hasattr(_store, "log")
    assert isinstance(_store.log, logging.Logger)
    assert _store.log.name == "remote_store._store"


@pytest.mark.spec("OBS-008")
def test_store_write_emits_log_records(caplog: pytest.LogCaptureFixture) -> None:
    store = _make_store()
    with caplog.at_level(logging.DEBUG, logger="remote_store._store"):
        store.write("a.txt", b"data")
    messages = [r.message for r in caplog.records]
    assert any("write" in m and "a.txt" in m for m in messages)


@pytest.mark.spec("OBS-008")
def test_log_extra_fields(caplog: pytest.LogCaptureFixture) -> None:
    store = _make_store()
    with caplog.at_level(logging.DEBUG, logger="remote_store._store"):
        store.exists("x.txt")
    record = caplog.records[0]
    assert record.op == "exists"  # type: ignore[attr-defined]
    assert record.path == "x.txt"  # type: ignore[attr-defined]
    assert record.backend == "memory"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# OBS-009: Error propagation
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-009")
def test_operation_error_propagates() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_error=events.append, on_any=lambda e: None)
    with pytest.raises(NotFound):
        observed.read("nonexistent.txt")
    assert len(events) == 1
    assert events[0].error is not None
    assert events[0].operation == "read"


@pytest.mark.spec("OBS-009")
def test_on_error_fires_with_event() -> None:
    store = _make_store()
    errors: list[StoreEvent] = []
    observed = observe(store, on_error=errors.append)
    with pytest.raises(NotFound):
        observed.delete("missing.txt")
    assert len(errors) == 1
    assert isinstance(errors[0].error, NotFound)


@pytest.mark.spec("OBS-009")
def test_per_operation_hook_fires_on_error() -> None:
    store = _make_store()
    read_events: list[StoreEvent] = []
    error_events: list[StoreEvent] = []
    observed = observe(store, on_read=read_events.append, on_error=error_events.append)
    with pytest.raises(NotFound):
        observed.read("nonexistent.txt")
    assert len(read_events) == 1
    assert read_events[0].error is not None
    assert len(error_events) == 1
    assert error_events[0].error is not None


# ---------------------------------------------------------------------------
# OBS-010: No lifecycle ownership
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-010")
def test_close_delegates_to_inner() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    observed.close()
    assert events[0].operation == "close"


@pytest.mark.spec("OBS-010")
def test_context_manager() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    with observed:
        observed.write("a.txt", b"data")
    ops = [e.operation for e in events]
    assert "write" in ops
    assert "close" in ops


# ---------------------------------------------------------------------------
# Correlation ID
# ---------------------------------------------------------------------------


def test_correlation_id_propagates() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    set_correlation_id("test-corr-123")
    try:
        observed.write("a.txt", b"data")
    finally:
        set_correlation_id(None)
    assert events[0].correlation_id == "test-corr-123"


def test_no_correlation_id_by_default() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    observed.exists("a.txt")
    assert events[0].correlation_id is None


# ---------------------------------------------------------------------------
# Additional proxy coverage (parametrized)
# ---------------------------------------------------------------------------

_PROXY_CASES = [
    pytest.param([], lambda o: o.to_key("a.txt"), "to_key", id="to_key"),
    pytest.param([], lambda o: o.supports(Capability.READ), "supports", id="supports"),
    pytest.param([], lambda o: o.child("sub"), "child", id="child"),
    pytest.param(["sub/a.txt"], lambda o: list(o.list_folders("")), "list_folders", id="list_folders"),
    pytest.param(["sub/a.txt"], lambda o: o.get_folder_info("sub"), "get_folder_info", id="get_folder_info"),
]


@pytest.mark.parametrize(("setup_files", "call", "expected_op"), _PROXY_CASES)
def test_proxy_coverage(setup_files: list[str], call: Any, expected_op: str) -> None:
    store = _make_store()
    for f in setup_files:
        store.write(f, b"data")
    events, kwargs = _collect_events()
    observed = observe(store, **kwargs)
    call(observed)
    assert any(e.operation == expected_op for e in events)


def test_proxy_glob(tmp_path: Any) -> None:
    store = Store(backend=LocalBackend(root=str(tmp_path)))
    store.write("a.txt", b"data")
    store.write("b.csv", b"data")
    events, kwargs = _collect_events()
    observed = observe(store, **kwargs)
    results = list(observed.glob("*.txt"))
    assert len(results) == 1
    assert results[0].name == "a.txt"
    assert any(e.operation == "glob" for e in events)


def test_proxy_unwrap() -> None:
    store = _make_store()
    events, kwargs = _collect_events()
    observed = observe(store, **kwargs)
    with pytest.raises(CapabilityNotSupported):
        observed.unwrap(MemoryBackend)
    assert any(e.operation == "unwrap" for e in events)
    assert events[-1].error is not None


def test_proxy_repr() -> None:
    assert "ObservedStore" in repr(observe(_make_store()))


# ---------------------------------------------------------------------------
# BUG-003: child() propagation
# ---------------------------------------------------------------------------


def test_child_returns_observed_store() -> None:
    store = _make_store()
    observed = observe(store, on_any=lambda e: None)
    child = observed.child("sub")
    assert isinstance(child, ObservedStore)


# ---------------------------------------------------------------------------
# ObservedStore __eq__, __hash__, native_path, resolve
# ---------------------------------------------------------------------------


def test_observed_store_eq_different_type_returns_not_implemented() -> None:
    observed = observe(_make_store())
    assert observed.__eq__("not-a-store") is NotImplemented


def test_observed_store_hash_is_stable() -> None:
    observed = observe(_make_store())
    assert hash(observed) == hash(observed)


def test_observed_native_path_fires_event() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    result = observed.native_path("a.txt")
    assert isinstance(result, str)
    assert any(e.operation == "native_path" for e in events)


def test_observed_resolve_fires_event() -> None:
    store = _make_store()
    events: list[StoreEvent] = []
    observed = observe(store, on_any=events.append)
    plan = observed.resolve("a.txt")
    assert plan is not None
    assert any(e.operation == "resolve" for e in events)


def test_child_fires_hooks() -> None:
    store = _make_store()
    store.write("sub/file.txt", b"data")
    events: list[StoreEvent] = []
    observed = observe(store, on_read=events.append)
    child = observed.child("sub")
    child.read_bytes("file.txt")
    assert any(e.operation == "read_bytes" for e in events)
