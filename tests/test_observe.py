"""Tests for remote_store.ext.observe -- observability hooks."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest

from remote_store._store import Store
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
    """Return a Store backed by MemoryBackend."""
    return Store(backend=MemoryBackend())


def _populated_store(*paths: str) -> Store:
    """Return a Store with files written at the given paths."""
    store = _make_store()
    for p in paths:
        store.write(p, b"data")
    return store


def _collect_events() -> tuple[list[StoreEvent], dict[str, Any]]:
    """Return (events_list, kwargs_for_observe)."""
    events: list[StoreEvent] = []

    def on_any(event: StoreEvent) -> None:
        events.append(event)

    return events, {"on_any": on_any}


# ---------------------------------------------------------------------------
# OBS-001: StoreEvent dataclass
# ---------------------------------------------------------------------------


class TestStoreEvent:
    @pytest.mark.spec("OBS-001")
    def test_store_event_is_frozen(self) -> None:
        event = StoreEvent(
            operation="read",
            path="a.txt",
            backend="memory",
            started_at=0.0,
            duration_ms=1.0,
            error=None,
            metadata={},
            correlation_id=None,
        )
        with pytest.raises(AttributeError):
            event.operation = "write"  # type: ignore[misc]

    @pytest.mark.spec("OBS-001")
    def test_store_event_fields(self) -> None:
        err = ValueError("boom")
        event = StoreEvent(
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


class TestObserveFactory:
    @pytest.mark.spec("OBS-002")
    def test_observe_returns_observed_store(self) -> None:
        store = _make_store()
        observed = observe(store)
        assert isinstance(observed, ObservedStore)
        assert isinstance(observed, Store)

    @pytest.mark.spec("OBS-002")
    def test_observe_inner_property(self) -> None:
        store = _make_store()
        observed = observe(store)
        assert observed.inner is store


# ---------------------------------------------------------------------------
# OBS-003: ObservedStore proxy
# ---------------------------------------------------------------------------


class TestObservedStoreProxy:
    @pytest.mark.spec("OBS-003")
    def test_write_fires_on_write(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_write=events.append)
        observed.write("a.txt", b"hello")
        assert len(events) == 1
        assert events[0].operation == "write"
        assert events[0].path == "a.txt"
        assert events[0].error is None
        assert events[0].duration_ms >= 0.0

    @pytest.mark.spec("OBS-003")
    def test_read_fires_on_read(self) -> None:
        store = _populated_store("a.txt")
        events: list[StoreEvent] = []
        observed = observe(store, on_read=events.append)
        observed.read("a.txt")
        assert len(events) == 1
        assert events[0].operation == "read"

    @pytest.mark.spec("OBS-003")
    def test_read_bytes_fires_on_read(self) -> None:
        store = _populated_store("a.txt")
        events: list[StoreEvent] = []
        observed = observe(store, on_read=events.append)
        data = observed.read_bytes("a.txt")
        assert data == b"data"
        assert len(events) == 1
        assert events[0].operation == "read_bytes"

    @pytest.mark.spec("OBS-003")
    def test_delete_fires_on_delete(self) -> None:
        store = _populated_store("a.txt")
        events: list[StoreEvent] = []
        observed = observe(store, on_delete=events.append)
        observed.delete("a.txt")
        assert len(events) == 1
        assert events[0].operation == "delete"

    @pytest.mark.spec("OBS-003")
    def test_copy_fires_on_copy(self) -> None:
        store = _populated_store("a.txt")
        events: list[StoreEvent] = []
        observed = observe(store, on_copy=events.append)
        observed.copy("a.txt", "b.txt")
        assert len(events) == 1
        assert events[0].operation == "copy"
        assert events[0].metadata["dst"] == "b.txt"

    @pytest.mark.spec("OBS-003")
    def test_move_fires_on_move(self) -> None:
        store = _populated_store("a.txt")
        events: list[StoreEvent] = []
        observed = observe(store, on_move=events.append)
        observed.move("a.txt", "b.txt")
        assert len(events) == 1
        assert events[0].operation == "move"
        assert events[0].metadata["dst"] == "b.txt"

    @pytest.mark.spec("OBS-003")
    def test_exists_fires_on_list(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_list=events.append)
        observed.exists("a.txt")
        assert len(events) == 1
        assert events[0].operation == "exists"

    @pytest.mark.spec("OBS-003")
    def test_list_files_fires_on_list(self) -> None:
        store = _populated_store("a.txt")
        events: list[StoreEvent] = []
        observed = observe(store, on_list=events.append)
        # list_files returns an iterator; consume it
        list(observed.list_files(""))
        assert len(events) == 1
        assert events[0].operation == "list_files"

    @pytest.mark.spec("OBS-003")
    def test_on_any_catches_all(self) -> None:
        store = _populated_store("a.txt")
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        observed.exists("a.txt")
        observed.read_bytes("a.txt")
        assert len(events) == 2
        assert events[0].operation == "exists"
        assert events[1].operation == "read_bytes"

    @pytest.mark.spec("OBS-003")
    def test_on_any_receives_error_events(self) -> None:
        """on_any must receive events with error set when operations fail."""
        from remote_store._errors import NotFound

        store = _make_store()
        any_events: list[StoreEvent] = []
        observed = observe(store, on_any=any_events.append)
        with pytest.raises(NotFound):
            observed.read("nonexistent.txt")
        assert len(any_events) == 1
        assert any_events[0].error is not None
        assert any_events[0].operation == "read"

    @pytest.mark.spec("OBS-003")
    def test_proxy_does_not_modify_results(self) -> None:
        store = _populated_store("a.txt")
        observed = observe(store, on_any=lambda e: None)
        assert observed.read_bytes("a.txt") == b"data"
        assert observed.exists("a.txt") is True
        assert observed.is_file("a.txt") is True

    @pytest.mark.spec("OBS-003")
    def test_hook_exception_suppressed(self) -> None:
        """Hook exceptions must not break the operation (OBS-009)."""
        store = _make_store()

        def bad_hook(event: StoreEvent) -> None:
            raise RuntimeError("hook boom")

        observed = observe(store, on_write=bad_hook)
        # Should not raise -- hook exception is suppressed
        observed.write("a.txt", b"hello")
        assert store.exists("a.txt")

    @pytest.mark.spec("OBS-003")
    def test_backend_name_in_event(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_any=events.append)
        observed.exists("x")
        assert events[0].backend == "memory"


# ---------------------------------------------------------------------------
# OBS-003a: Hook-to-operation mapping
# ---------------------------------------------------------------------------


class TestHookMapping:
    @pytest.mark.spec("OBS-003a")
    def test_write_atomic_fires_on_write(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_write=events.append)
        observed.write_atomic("a.txt", b"atomic")
        assert len(events) == 1
        assert events[0].operation == "write_atomic"

    @pytest.mark.spec("OBS-003a")
    def test_delete_folder_fires_on_delete(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_delete=events.append)
        # Create folder content then delete
        store.write("sub/a.txt", b"data")
        observed.delete_folder("sub", recursive=True)
        assert len(events) == 1
        assert events[0].operation == "delete_folder"

    @pytest.mark.spec("OBS-003a")
    def test_get_file_info_fires_on_list(self) -> None:
        store = _populated_store("a.txt")
        events: list[StoreEvent] = []
        observed = observe(store, on_list=events.append)
        observed.get_file_info("a.txt")
        assert len(events) == 1
        assert events[0].operation == "get_file_info"

    @pytest.mark.spec("OBS-003a")
    def test_is_file_fires_on_list(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_list=events.append)
        observed.is_file("x")
        assert events[0].operation == "is_file"

    @pytest.mark.spec("OBS-003a")
    def test_is_folder_fires_on_list(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_list=events.append)
        observed.is_folder("x")
        assert events[0].operation == "is_folder"


# ---------------------------------------------------------------------------
# OBS-004: After-only hooks
# ---------------------------------------------------------------------------


class TestAfterOnlyHooks:
    @pytest.mark.spec("OBS-004")
    def test_hook_fires_after_operation(self) -> None:
        """Verify the hook fires after the operation completes."""
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_write=events.append)
        observed.write("a.txt", b"data")
        # Event should have positive duration
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
        # File should NOT have been written
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
            event = StoreEvent(
                operation="read",
                path="a.txt",
                backend="memory",
                started_at=0.0,
                duration_ms=1.0,
                error=None,
                metadata={},
                correlation_id=None,
            )
            observer.on_event(event)
            observer.flush()
            assert len(batches) == 1
            assert len(batches[0]) == 1
            assert batches[0][0] is event
        finally:
            observer.close()

    @pytest.mark.spec("OBS-006")
    def test_close_flushes_remaining(self) -> None:
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, flush_interval=60.0)
        event = StoreEvent(
            operation="write",
            path="b.txt",
            backend="memory",
            started_at=0.0,
            duration_ms=2.0,
            error=None,
            metadata={},
            correlation_id=None,
        )
        observer.on_event(event)
        observer.close()
        assert len(batches) >= 1
        all_events = [e for batch in batches for e in batch]
        assert event in all_events

    @pytest.mark.spec("OBS-006")
    def test_full_queue_drops_events(self) -> None:
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, max_queue=2, flush_interval=60.0)
        try:
            for i in range(5):
                observer.on_event(
                    StoreEvent(
                        operation="read",
                        path=f"file{i}.txt",
                        backend="memory",
                        started_at=0.0,
                        duration_ms=0.0,
                        error=None,
                        metadata={},
                        correlation_id=None,
                    )
                )
            observer.flush()
            all_events = [e for batch in batches for e in batch]
            # Only 2 should have made it through
            assert len(all_events) == 2
        finally:
            observer.close()

    @pytest.mark.spec("OBS-006")
    def test_integration_with_observed_store(self) -> None:
        """BufferedObserver.on_event can be used as an on_any hook."""
        store = _populated_store("a.txt")
        batches: list[list[StoreEvent]] = []
        observer = BufferedObserver(batches.append, flush_interval=60.0)
        try:
            observed = observe(store, on_any=observer.on_event)
            observed.read_bytes("a.txt")
            observer.flush()
            assert len(batches) == 1
            assert batches[0][0].operation == "read_bytes"
        finally:
            observer.close()


# ---------------------------------------------------------------------------
# OBS-007: Drift-protection test
# ---------------------------------------------------------------------------


@pytest.mark.spec("OBS-007")
def test_observed_store_overrides_all_public_methods() -> None:
    """ObservedStore must override every public method of Store.

    This prevents new Store methods from silently bypassing observation.
    See ADR-0010.
    """
    store_public = {name for name, val in vars(Store).items() if not name.startswith("_") and callable(val)}
    observed_overrides = set(vars(ObservedStore)) & store_public
    missing = store_public - observed_overrides
    assert not missing, f"ObservedStore missing overrides for: {sorted(missing)}"


# ---------------------------------------------------------------------------
# OBS-008: Intrinsic logging
# ---------------------------------------------------------------------------


class TestIntrinsicLogging:
    @pytest.mark.spec("OBS-008")
    def test_null_handler_registered(self) -> None:
        """The top-level 'remote_store' logger has a NullHandler."""
        root_logger = logging.getLogger("remote_store")
        handler_types = [type(h) for h in root_logger.handlers]
        assert logging.NullHandler in handler_types

    @pytest.mark.spec("OBS-008")
    def test_store_module_has_logger(self) -> None:
        from remote_store import _store

        assert hasattr(_store, "log")
        assert isinstance(_store.log, logging.Logger)
        assert _store.log.name == "remote_store._store"

    @pytest.mark.spec("OBS-008")
    def test_store_write_emits_log_records(self, caplog: pytest.LogCaptureFixture) -> None:
        store = _make_store()
        with caplog.at_level(logging.DEBUG, logger="remote_store._store"):
            store.write("a.txt", b"data")
        # Should have DEBUG (entry) and INFO (completion) records
        messages = [r.message for r in caplog.records]
        assert any("write" in m and "a.txt" in m for m in messages)

    @pytest.mark.spec("OBS-008")
    def test_log_extra_fields(self, caplog: pytest.LogCaptureFixture) -> None:
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


class TestErrorPropagation:
    @pytest.mark.spec("OBS-009")
    def test_operation_error_propagates(self) -> None:
        """Errors from the inner store must propagate through the proxy."""
        from remote_store._errors import NotFound

        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_error=events.append, on_any=lambda e: None)
        with pytest.raises(NotFound):
            observed.read("nonexistent.txt")
        assert len(events) == 1
        assert events[0].error is not None
        assert events[0].operation == "read"

    @pytest.mark.spec("OBS-009")
    def test_on_error_fires_with_event(self) -> None:
        from remote_store._errors import NotFound

        store = _make_store()
        errors: list[StoreEvent] = []
        observed = observe(store, on_error=errors.append)
        with pytest.raises(NotFound):
            observed.delete("missing.txt")
        assert len(errors) == 1
        assert isinstance(errors[0].error, NotFound)

    @pytest.mark.spec("OBS-009")
    def test_per_operation_hook_fires_on_error(self) -> None:
        """Per-op hook and on_error both fire when an operation fails."""
        from remote_store._errors import NotFound

        store = _make_store()
        read_events: list[StoreEvent] = []
        error_events: list[StoreEvent] = []
        observed = observe(store, on_read=read_events.append, on_error=error_events.append)
        with pytest.raises(NotFound):
            observed.read("nonexistent.txt")
        # on_read fires with error set
        assert len(read_events) == 1
        assert read_events[0].error is not None
        assert read_events[0].operation == "read"
        # on_error also fires
        assert len(error_events) == 1
        assert error_events[0].error is not None


# ---------------------------------------------------------------------------
# OBS-010: No lifecycle ownership
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.spec("OBS-010")
    def test_close_delegates_to_inner(self) -> None:
        """ObservedStore.close() delegates to the inner store."""
        backend = MemoryBackend()
        store = Store(backend=backend)
        events: list[StoreEvent] = []
        observed = observe(store, on_any=events.append)
        observed.close()
        assert len(events) == 1
        assert events[0].operation == "close"

    @pytest.mark.spec("OBS-010")
    def test_context_manager(self) -> None:
        """ObservedStore works as a context manager."""
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_any=events.append)
        with observed:
            observed.write("a.txt", b"data")
        # Should have write + close events
        ops = [e.operation for e in events]
        assert "write" in ops
        assert "close" in ops


# ---------------------------------------------------------------------------
# Correlation ID
# ---------------------------------------------------------------------------


class TestCorrelationId:
    def test_correlation_id_propagates(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_any=events.append)
        set_correlation_id("test-corr-123")
        try:
            observed.write("a.txt", b"data")
        finally:
            set_correlation_id(None)
        assert events[0].correlation_id == "test-corr-123"

    def test_no_correlation_id_by_default(self) -> None:
        store = _make_store()
        events: list[StoreEvent] = []
        observed = observe(store, on_any=events.append)
        observed.exists("a.txt")
        assert events[0].correlation_id is None


# ---------------------------------------------------------------------------
# Additional proxy coverage
# ---------------------------------------------------------------------------


class TestProxyCoverage:
    """Cover remaining proxy methods not covered by specific hook tests."""

    def test_to_key(self) -> None:
        store = _populated_store("a.txt")
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        # to_key on a memory backend -- path should pass through
        result = observed.to_key("a.txt")
        assert result == "a.txt"
        assert any(e.operation == "to_key" for e in events)

    def test_supports(self) -> None:
        from remote_store._capabilities import Capability

        store = _make_store()
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        result = observed.supports(Capability.READ)
        assert result is True
        assert any(e.operation == "supports" for e in events)

    def test_child(self) -> None:
        store = _make_store()
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        child = observed.child("sub")
        assert isinstance(child, Store)
        assert any(e.operation == "child" for e in events)

    def test_list_folders(self) -> None:
        store = _make_store()
        store.write("sub/a.txt", b"data")
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        list(observed.list_folders(""))
        assert any(e.operation == "list_folders" for e in events)

    def test_get_folder_info(self) -> None:
        store = _make_store()
        store.write("sub/a.txt", b"data")
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        observed.get_folder_info("sub")
        assert any(e.operation == "get_folder_info" for e in events)

    def test_glob(self, tmp_path: Any) -> None:
        from remote_store.backends._local import LocalBackend

        store = Store(backend=LocalBackend(root=str(tmp_path)))
        store.write("a.txt", b"data")
        store.write("b.csv", b"data")
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        results = list(observed.glob("*.txt"))
        assert len(results) == 1
        assert results[0].name == "a.txt"
        assert any(e.operation == "glob" for e in events)

    def test_unwrap(self) -> None:
        from remote_store._errors import CapabilityNotSupported

        store = _make_store()
        events, kwargs = _collect_events()
        observed = observe(store, **kwargs)
        # MemoryBackend doesn't implement unwrap, so it raises
        with pytest.raises(CapabilityNotSupported):
            observed.unwrap(MemoryBackend)
        assert any(e.operation == "unwrap" for e in events)
        assert events[-1].error is not None

    def test_repr(self) -> None:
        store = _make_store()
        observed = observe(store)
        assert "ObservedStore" in repr(observed)
