# ext.observe

## observe

Observability hooks -- callback-based instrumentation for Store operations.

Wraps a Store in a proxy that fires user-defined callbacks before and after each operation, enabling logging, metrics, auditing, and tracing without modifying business code.

Example

```
from remote_store.ext.observe import observe

def on_write(event):
    print(f"Wrote {event.path} in {event.duration_ms:.1f}ms")

observed = observe(store, on_write=on_write)
observed.write("key.txt", b"hello")
```

### StoreEvent

```
StoreEvent(
    operation: str,
    path: str,
    backend: str,
    started_at: float,
    duration_ms: float,
    error: Exception | None,
    metadata: dict[str, Any],
    correlation_id: str | None,
)
```

Immutable record of a single Store operation.

### ObservedStore

```
ObservedStore(
    inner: Store,
    *,
    hooks: dict[str, Any],
    around: Any | None,
)
```

Bases: `ProxyStore`

Proxy Store that fires observation hooks on every public method.

All `Store` methods are delegated to the inner store. Only methods with additional behavior (`ping`, `close`, `child`) are documented individually below; the remaining overrides add hook dispatch and are otherwise transparent.

Do not construct directly -- use `observe()`.

#### ping

```
ping() -> None
```

Delegate ping to inner store.

#### close

```
close() -> None
```

Delegate close to inner store.

#### child

```
child(subpath: str) -> Store
```

Return an observed child store.

#### resolve

```
resolve(key: str) -> ResolutionPlan
```

Resolve a key to a `ResolutionPlan`, emitting observation events.

Event metadata is intentionally empty to prevent sensitive `details` from flowing through observation callbacks.

### BufferedObserver

```
BufferedObserver(
    handler: Callable[[list[StoreEvent]], None],
    *,
    max_queue: int = 1000,
    flush_interval: float = 5.0,
)
```

Collects events and flushes them in batches to a handler.

Parameters:

- **`handler`** (`Callable[[list[StoreEvent]], None]`) – Called with a list of events on each flush.
- **`max_queue`** (`int`, default: `1000` ) – Maximum queue size. Events are dropped when full.
- **`flush_interval`** (`float`, default: `5.0` ) – Seconds between automatic flushes.

#### on_event

```
on_event(event: StoreEvent) -> None
```

Enqueue an event. Drops and warns if queue is full.

#### flush

```
flush() -> None
```

Drain the queue and call the handler with collected events.

#### close

```
close() -> None
```

Stop the background thread and perform a final flush.

### set_correlation_id

```
set_correlation_id(cid: str | None) -> Token[str | None]
```

Set the correlation ID for the current context.

Returns a token that can be used to reset the value:

```
token = set_correlation_id("req-123")
# ... operations here will have correlation_id="req-123" ...
_correlation_id.reset(token)
```

Parameters:

- **`cid`** (`str | None`) – Correlation ID string, or None to clear.

Returns:

- `Token[str | None]` – A Token for resetting the value.

### observe

```
observe(
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
    around: Callable[
        [str, str, str], AbstractContextManager[None]
    ]
    | None = None,
) -> ObservedStore
```

Wrap a Store with observation hooks.

Parameters:

- **`store`** (`Store`) – The Store to observe.
- **`on_read`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after read/read_bytes/read_text.
- **`on_write`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after write/write_text/write_atomic/open_atomic.
- **`on_delete`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after delete/delete_folder.
- **`on_copy`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after copy.
- **`on_move`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after move.
- **`on_list`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after list_files/list_folders/iter_children/glob/ get_file_info/get_folder_info/exists/is_file/is_folder/ resolve.
- **`on_ping`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after ping.
- **`on_error`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires on any operation that raises an exception.
- **`on_any`** (`Callable[[StoreEvent], None] | None`, default: `None` ) – Fires after every operation (catch-all).
- **`around`** (`Callable[[str, str, str], AbstractContextManager[None]] | None`, default: `None` ) – Context-manager factory (op, path, backend) -> CM wrapping the entire operation.

Returns:

- `ObservedStore` – An ObservedStore proxy.

## See also

- [Observe](https://docs.remotestore.dev/stable/guides/observe/index.md) — guide to callback hooks for store operations
- [Observe Hooks example](https://docs.remotestore.dev/stable/tutorial/examples/observe-hooks/index.md) — observe hooks in action
