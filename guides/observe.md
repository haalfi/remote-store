# Observability Hooks

The `ext.observe` extension wraps a Store in a proxy that fires
user-defined callbacks after each operation. This enables logging,
metrics collection, auditing, and tracing without modifying business
code.

## Quick Start

```python
from remote_store import observe

def on_write(event):
    print(f"Wrote {event.path} in {event.duration_ms:.1f}ms")

observed = observe(store, on_write=on_write)
observed.write("data/report.csv", csv_bytes)
# prints: Wrote data/report.csv in 12.3ms
```

The returned `ObservedStore` is a full `Store` subclass -- it passes
`isinstance(observed, Store)` and works everywhere a Store is expected.

## Hook Types

### Per-operation hooks (after-only)

Each hook fires **after** the operation completes (success or failure):

| Hook | Operations |
|------|-----------|
| `on_read` | `read`, `read_bytes` |
| `on_write` | `write`, `write_atomic` |
| `on_delete` | `delete`, `delete_folder` |
| `on_copy` | `copy` |
| `on_move` | `move` |
| `on_list` | `list_files`, `list_folders`, `glob`, `get_file_info`, `get_folder_info`, `exists`, `is_file`, `is_folder` |
| `on_error` | Any operation that raises an exception |
| `on_any` | Every operation (catch-all) |

### Around hook (context manager)

The `around` parameter accepts a factory that returns a context manager
wrapping the entire operation:

```python
import contextlib

@contextlib.contextmanager
def trace_span(op, path, backend):
    span = tracer.start_span(f"store.{op}")
    span.set_attribute("path", path)
    try:
        yield
    finally:
        span.end()

observed = observe(store, around=trace_span)
```

## StoreEvent

Every hook receives a `StoreEvent` frozen dataclass:

```python
@dataclasses.dataclass(frozen=True)
class StoreEvent:
    operation: str           # "read", "write", "delete", ...
    path: str                # store-relative key
    backend: str             # backend name
    started_at: float        # time.monotonic()
    duration_ms: float       # elapsed milliseconds
    error: Exception | None  # None on success
    metadata: dict[str, Any] # op-specific: overwrite, dst, recursive, ...
    correlation_id: str | None  # from contextvars, None if not set
```

## BufferedObserver

For high-throughput scenarios, `BufferedObserver` collects events in a
thread-safe queue and flushes them in batches:

```python
from remote_store import BufferedObserver, observe

def send_to_analytics(events):
    for event in events:
        analytics.track("store_op", {
            "op": event.operation,
            "path": event.path,
            "duration_ms": event.duration_ms,
        })

observer = BufferedObserver(send_to_analytics, flush_interval=10.0)
observed = observe(store, on_any=observer.on_event)

# ... use observed store ...

observer.close()  # final flush + stop background thread
```

Parameters:
- `max_queue` (default 1000): events are dropped when the queue is full.
- `flush_interval` (default 5.0): seconds between automatic flushes.

## Intrinsic Logging

The library also provides built-in stdlib logging. Enable it in your
application:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# All remote_store operations now log to stderr:
# DEBUG remote_store._store: read path='data/file.csv'
# INFO  remote_store._store: write complete path='output.csv'
```

Log records include structured `extra` fields (`op`, `path`, `backend`)
accessible via custom formatters or structlog processors.

## Error Handling

- **Operation errors always propagate.** The proxy catches exceptions only
  to build the `StoreEvent` (with `error` set) and fire hooks, then
  re-raises.
- **Hook exceptions are suppressed.** A failing hook never breaks the
  observed operation. Hook errors are logged at WARNING level.

## Composing with Other Extensions

`ext.observe` wraps at the Store level, so it composes naturally with
other extensions:

```python
from remote_store import observe, batch_delete

observed = observe(store, on_any=print_event)

# batch_delete calls observed.delete() for each path --
# each individual delete fires hooks
batch_delete(observed, ["a.txt", "b.txt", "c.txt"])
```

The `ext.transfer` `on_progress` callback remains separate (different
concern: UI progress vs telemetry).
