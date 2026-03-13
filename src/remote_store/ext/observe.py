"""Observability hooks -- callback-based instrumentation for Store operations.

Wraps a Store in a proxy that fires user-defined callbacks before and after
each operation, enabling logging, metrics, auditing, and tracing without
modifying business code.

Usage:

```python
from remote_store.ext.observe import observe

def on_write(event):
    print(f"Wrote {event.path} in {event.duration_ms:.1f}ms")

observed = observe(store, on_write=on_write)
observed.write("key.txt", b"hello")
```
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import queue
import threading
import time
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar

from remote_store._store import Store

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from contextlib import AbstractContextManager

    from remote_store._capabilities import Capability
    from remote_store._models import FileInfo, FolderInfo
    from remote_store._types import WritableContent

T = TypeVar("T")

log = logging.getLogger(__name__)

__all__ = [
    "BufferedObserver",
    "ObservedStore",
    "StoreEvent",
    "observe",
    "set_correlation_id",
]

# ---------------------------------------------------------------------------
# Context variable for correlation IDs
# ---------------------------------------------------------------------------

_correlation_id: ContextVar[str | None] = ContextVar("_correlation_id", default=None)


def set_correlation_id(cid: str | None) -> Token[str | None]:
    """Set the correlation ID for the current context.

    Returns a token that can be used to reset the value:

    ```python
    token = set_correlation_id("req-123")
    # ... operations here will have correlation_id="req-123" ...
    _correlation_id.reset(token)
    ```

    :param cid: Correlation ID string, or ``None`` to clear.
    :returns: A ``Token`` for resetting the value.
    """
    return _correlation_id.set(cid)


# ---------------------------------------------------------------------------
# Hook type aliases (runtime-compatible, no TYPE_CHECKING guard)
# ---------------------------------------------------------------------------

# OnEvent = Callable[[StoreEvent], None]
# AroundHook = Callable[[str, str, str], AbstractContextManager[None]]

# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class StoreEvent:
    """Immutable record of a single Store operation."""

    operation: str
    path: str
    backend: str
    started_at: float
    duration_ms: float
    error: Exception | None
    metadata: dict[str, Any]
    correlation_id: str | None


# ---------------------------------------------------------------------------
# ObservedStore proxy
# ---------------------------------------------------------------------------

# Hook-to-operation mapping (OBS-003a)
_OP_HOOK_MAP: dict[str, str] = {
    "read": "on_read",
    "read_bytes": "on_read",
    "read_text": "on_read",
    "write": "on_write",
    "write_atomic": "on_write",
    "open_atomic": "on_write",
    "delete": "on_delete",
    "delete_folder": "on_delete",
    "copy": "on_copy",
    "move": "on_move",
    "iter_children": "on_list",
    "list_files": "on_list",
    "list_folders": "on_list",
    "glob": "on_list",
    "get_file_info": "on_list",
    "get_folder_info": "on_list",
    "exists": "on_list",
    "is_file": "on_list",
    "is_folder": "on_list",
    "ping": "on_ping",
}


class ObservedStore(Store):
    """Proxy Store that fires observation hooks on every public method.

    All ``Store`` methods are delegated to the inner store. Only methods
    with additional behavior (``ping``, ``close``, ``child``) are
    documented individually below; the remaining overrides add hook
    dispatch and are otherwise transparent.

    Do not construct directly -- use ``observe()``.
    """

    _inner: Store
    _hooks: dict[str, Any]
    _around: Any

    def __init__(
        self,
        inner: Store,
        *,
        hooks: dict[str, Any],
        around: Any | None,
    ) -> None:
        # Bypass Store.__init__ -- we delegate everything to inner.
        # We still need _backend and _root so inherited helpers work
        # if someone calls a dunder or property we didn't override.
        self._inner = inner
        self._hooks = hooks
        self._around = around
        self._backend = inner._backend
        self._root = inner._root
        self._owns_backend = False

    @property
    def inner(self) -> Store:
        """The wrapped Store instance."""
        return self._inner

    def __repr__(self) -> str:
        return f"ObservedStore(inner={self._inner!r})"

    # region: helpers
    def _fire(
        self,
        operation: str,
        path: str,
        metadata: dict[str, Any],
        started_at: float,
        duration_ms: float,
        error: Exception | None,
    ) -> None:
        """Construct a StoreEvent and dispatch to registered hooks."""
        event = StoreEvent(
            operation=operation,
            path=path,
            backend=self._inner._backend.name,
            started_at=started_at,
            duration_ms=duration_ms,
            error=error,
            metadata=metadata,
            correlation_id=_correlation_id.get(),
        )
        hooks: dict[str, Any] = self._hooks
        # Per-operation hook
        hook_name = _OP_HOOK_MAP.get(operation)
        if hook_name and hooks.get(hook_name) is not None:
            try:
                hooks[hook_name](event)
            except Exception:
                log.warning("Hook %s raised an exception", hook_name, exc_info=True)

        # Catch-all hook (fires before on_error per OBS-003 step 7)
        if hooks.get("on_any") is not None:
            try:
                hooks["on_any"](event)
            except Exception:
                log.warning("Hook on_any raised an exception", exc_info=True)

        # Error hook (OBS-003 step 8)
        if error is not None and hooks.get("on_error") is not None:
            try:
                hooks["on_error"](event)
            except Exception:
                log.warning("Hook on_error raised an exception", exc_info=True)

    @contextlib.contextmanager
    def _observe_op(
        self,
        operation: str,
        path: str,
        metadata: dict[str, Any],
    ) -> Iterator[None]:
        """Context manager wrapping an operation with timing and hooks."""
        around = self._around
        started_at = time.monotonic()
        backend_name = self._inner._backend.name
        around_cm: AbstractContextManager[None] | None = None
        if around is not None:
            around_cm = around(operation, path, backend_name)

        error: Exception | None = None
        try:
            if around_cm is not None:
                with around_cm:
                    yield
            else:
                yield
        except Exception as exc:
            error = exc
            raise
        finally:
            elapsed = (time.monotonic() - started_at) * 1000.0
            self._fire(operation, path, metadata, started_at, elapsed, error)

    # endregion

    # region: public method overrides
    def ping(self) -> None:  # noqa: D401
        """Delegate ping to inner store."""
        with self._observe_op("ping", "", {}):
            self._inner.ping()

    def close(self) -> None:  # noqa: D401
        """Delegate close to inner store."""
        with self._observe_op("close", "", {}):
            self._inner.close()

    def child(self, subpath: str) -> Store:
        """Return a child of the inner store (not observed)."""
        with self._observe_op("child", subpath, {}):
            return self._inner.child(subpath)

    def to_key(self, path: str) -> str:
        with self._observe_op("to_key", path, {}):
            return self._inner.to_key(path)

    def unwrap(self, type_hint: type[T]) -> T:
        with self._observe_op("unwrap", "", {"type_hint": str(type_hint)}):
            return self._inner.unwrap(type_hint)

    def native_path(self, key: str) -> str:
        with self._observe_op("native_path", key, {}):
            return self._inner.native_path(key)

    def supports(self, capability: Capability) -> bool:
        with self._observe_op("supports", "", {"capability": capability.name}):
            return self._inner.supports(capability)

    def exists(self, path: str) -> bool:
        with self._observe_op("exists", path, {}):
            return self._inner.exists(path)

    def is_file(self, path: str) -> bool:
        with self._observe_op("is_file", path, {}):
            return self._inner.is_file(path)

    def is_folder(self, path: str) -> bool:
        with self._observe_op("is_folder", path, {}):
            return self._inner.is_folder(path)

    def read(self, path: str) -> BinaryIO:
        with self._observe_op("read", path, {}):
            return self._inner.read(path)

    def read_bytes(self, path: str) -> bytes:
        with self._observe_op("read_bytes", path, {}):
            return self._inner.read_bytes(path)

    def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
        with self._observe_op("read_text", path, {"encoding": encoding}):
            return self._inner.read_text(path, encoding=encoding, errors=errors)

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._observe_op("write", path, {"overwrite": overwrite}):
            self._inner.write(path, content, overwrite=overwrite)

    def write_text(self, path: str, text: str, *, encoding: str = "utf-8", overwrite: bool = False) -> None:
        with self._observe_op("write", path, {"overwrite": overwrite}):
            self._inner.write_text(path, text, encoding=encoding, overwrite=overwrite)

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        with self._observe_op("write_atomic", path, {"overwrite": overwrite}):
            self._inner.write_atomic(path, content, overwrite=overwrite)

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        with (
            self._observe_op("open_atomic", path, {"overwrite": overwrite}),
            self._inner.open_atomic(path, overwrite=overwrite) as f,
        ):
            yield f

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._observe_op("delete", path, {"missing_ok": missing_ok}):
            self._inner.delete(path, missing_ok=missing_ok)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._observe_op("delete_folder", path, {"recursive": recursive, "missing_ok": missing_ok}):
            self._inner.delete_folder(path, recursive=recursive, missing_ok=missing_ok)

    def iter_children(self, path: str) -> Iterator[FileInfo | str]:
        # Materialize: see list_files comment.
        with self._observe_op("iter_children", path, {}):
            return iter(list(self._inner.iter_children(path)))

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        pattern: str | None = None,
    ) -> Iterator[FileInfo]:
        # Materialize: inner list_files() is a generator whose body runs lazily.
        # Collecting into a list ensures timing and error capture cover actual
        # I/O, not just generator creation.
        with self._observe_op("list_files", path, {"recursive": recursive, "pattern": pattern}):
            return iter(list(self._inner.list_files(path, recursive=recursive, pattern=pattern)))

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        # Materialize: see list_files comment.
        with self._observe_op("glob", pattern, {"pattern": pattern}):
            return iter(list(self._inner.glob(pattern)))

    def list_folders(self, path: str) -> Iterator[str]:
        # Materialize: see list_files comment.
        with self._observe_op("list_folders", path, {}):
            return iter(list(self._inner.list_folders(path)))

    def get_file_info(self, path: str) -> FileInfo:
        with self._observe_op("get_file_info", path, {}):
            return self._inner.get_file_info(path)

    def get_folder_info(self, path: str) -> FolderInfo:
        with self._observe_op("get_folder_info", path, {}):
            return self._inner.get_folder_info(path)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._observe_op("move", src, {"dst": dst, "overwrite": overwrite}):
            self._inner.move(src, dst, overwrite=overwrite)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._observe_op("copy", src, {"dst": dst, "overwrite": overwrite}):
            self._inner.copy(src, dst, overwrite=overwrite)

    # endregion


# ---------------------------------------------------------------------------
# observe() factory
# ---------------------------------------------------------------------------


def observe(
    store: Store,
    *,
    on_read: Callable[[StoreEvent], None] | None = None,
    on_write: Callable[[StoreEvent], None] | None = None,
    on_delete: Callable[[StoreEvent], None] | None = None,
    on_copy: Callable[[StoreEvent], None] | None = None,
    on_move: Callable[[StoreEvent], None] | None = None,
    on_list: Callable[[StoreEvent], None] | None = None,
    on_ping: Callable[[StoreEvent], None] | None = None,
    on_error: Callable[[StoreEvent], None] | None = None,
    on_any: Callable[[StoreEvent], None] | None = None,
    around: Callable[[str, str, str], AbstractContextManager[None]] | None = None,
) -> ObservedStore:
    """Wrap a Store with observation hooks.

    :param store: The Store to observe.
    :param on_read: Fires after read/read_bytes/read_text.
    :param on_write: Fires after write/write_atomic/open_atomic.
    :param on_delete: Fires after delete/delete_folder.
    :param on_copy: Fires after copy.
    :param on_move: Fires after move.
    :param on_list: Fires after list_files/list_folders/glob/get_file_info/
        get_folder_info/exists/is_file/is_folder.
    :param on_ping: Fires after ping.
    :param on_error: Fires on any operation that raises an exception.
    :param on_any: Fires after every operation (catch-all).
    :param around: Context-manager factory ``(op, path, backend) -> CM``
        wrapping the entire operation.
    :returns: An ``ObservedStore`` proxy.
    """
    hooks = {
        "on_read": on_read,
        "on_write": on_write,
        "on_delete": on_delete,
        "on_copy": on_copy,
        "on_move": on_move,
        "on_list": on_list,
        "on_ping": on_ping,
        "on_error": on_error,
        "on_any": on_any,
    }
    return ObservedStore(store, hooks=hooks, around=around)


# ---------------------------------------------------------------------------
# BufferedObserver
# ---------------------------------------------------------------------------


class BufferedObserver:
    """Collects events and flushes them in batches to a handler.

    :param handler: Called with a list of events on each flush.
    :param max_queue: Maximum queue size. Events are dropped when full.
    :param flush_interval: Seconds between automatic flushes.
    """

    def __init__(
        self,
        handler: Callable[[list[StoreEvent]], None],
        *,
        max_queue: int = 1000,
        flush_interval: float = 5.0,
    ) -> None:
        self._handler = handler
        self._queue: queue.Queue[StoreEvent] = queue.Queue(maxsize=max_queue)
        self._flush_interval = flush_interval
        self._closed = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def on_event(self, event: StoreEvent) -> None:
        """Enqueue an event. Drops and warns if queue is full."""
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            log.warning(
                "BufferedObserver queue full, dropping event op=%s path=%s",
                event.operation,
                event.path,
            )

    def flush(self) -> None:
        """Drain the queue and call the handler with collected events."""
        events: list[StoreEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if events:
            self._handler(events)

    def close(self) -> None:
        """Stop the background thread and perform a final flush."""
        self._closed = True
        self._stop.set()
        self._thread.join(timeout=2.0)
        self.flush()

    def _run(self) -> None:
        """Background loop: flush periodically until closed."""
        while not self._closed:
            self._stop.wait(timeout=self._flush_interval)
            self.flush()
