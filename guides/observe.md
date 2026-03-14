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
| `on_write` | `write`, `write_atomic`, `open_atomic` |
| `on_delete` | `delete`, `delete_folder` |
| `on_copy` | `copy` |
| `on_move` | `move` |
| `on_list` | `list_files`, `list_folders`, `iter_children`, `glob`, `get_file_info`, `get_folder_info`, `exists`, `is_file`, `is_folder` |
| `on_ping` | `ping` |
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
    correlation_id: str | None  # from set_correlation_id(), None if not set
```

### Correlation IDs

Use `set_correlation_id()` to tag all events within a scope with
a shared identifier (e.g., a request ID):

```python
from remote_store import observe, set_correlation_id

observed = observe(store, on_any=lambda e: print(e.correlation_id))

token = set_correlation_id("req-abc-123")
observed.read_bytes("data.csv")   # correlation_id="req-abc-123"
observed.write("out.csv", b"...")  # correlation_id="req-abc-123"
set_correlation_id(None)  # or: from contextvars import Token; _correlation_id.reset(token)
```

The correlation ID is stored in a `contextvars.ContextVar`, so it
works correctly with threading and async tasks.

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

The library ships with built-in stdlib logging. Every module uses
`logging.getLogger(__name__)`, so all loggers live under the
`remote_store` namespace (e.g. `remote_store._store`,
`remote_store.backends._local`, `remote_store.ext.observe`).
A `NullHandler` is attached to the root `"remote_store"` logger so
the library is silent by default.

### Showing only warnings

Set the level on the `"remote_store"` logger -- this applies to all
child loggers in the hierarchy:

```python
import logging

logging.basicConfig()  # ensure at least one handler on root
logging.getLogger("remote_store").setLevel(logging.WARNING)
```

### Verbose debug output

```python
import logging

logging.basicConfig(level=logging.WARNING)  # keep other libs quiet
logging.getLogger("remote_store").setLevel(logging.DEBUG)

# DEBUG remote_store._store: read path='data/file.csv'
# INFO  remote_store._store: write complete path='output.csv'
```

### Logging levels used

| Level | When |
|-------|------|
| `DEBUG` | Method entry (every Store operation) |
| `INFO` | Mutating-operation completion (write, delete, move, copy) |
| `WARNING` | Suppressed hook exceptions, fallback behaviour |
| `ERROR` | Before re-raising backend errors |

### Structured `extra` fields

Log records include structured `extra` fields accessible via custom
formatters or structlog processors:

| Field | Description |
|-------|-------------|
| `op` | Operation name (`"read"`, `"write"`, ...) |
| `path` | Store-relative key |
| `backend` | Backend name (`"local"`, `"s3"`, ...) |

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

## Layer 3: OpenTelemetry Bridge

The `ext.otel` module provides pre-built hooks that emit
[OpenTelemetry](https://opentelemetry.io/) spans and metrics. Install
the optional dependency:

```bash
pip install "remote-store[otel]"
```

This depends only on `opentelemetry-api` (not the SDK). If no SDK is
configured at runtime, all OTel calls become zero-cost no-ops.

### Quick start

```python
from remote_store.ext.otel import otel_observe

observed = otel_observe(store)
observed.write("data/report.csv", csv_bytes)
# -> OTel span "store.write" + metrics recorded automatically
```

Or compose with other hooks using `otel_hooks()`:

```python
from remote_store import observe
from remote_store.ext.otel import otel_hooks

observed = observe(
    store,
    **otel_hooks(),
    on_error=my_error_alerter,
)
```

### Spans

Each operation creates a span with:

- **Name:** `store.{operation}` (e.g. `store.read`, `store.write`)
- **Kind:** `SpanKind.CLIENT` (outbound call to storage)
- **Attributes:** `remote_store.operation`, `remote_store.backend`,
  `remote_store.path`
- **On error:** Status set to ERROR, exception recorded, `error.type`
  attribute added

### Metrics

Three instruments are created:

| Type | Name | Unit | Attributes |
|------|------|------|------------|
| Counter | `remote_store.operations` | `1` | `operation`, `backend`, `status` |
| Counter | `remote_store.errors` | `1` | `operation`, `backend`, `error.type` |
| Histogram | `remote_store.operation.duration` | `s` | `operation`, `backend`; plus `error.type` on error |

Note: `path` is intentionally excluded from metric attributes to
avoid high-cardinality issues with metric backends like Prometheus.

### Configuring the SDK

The bridge works with any OpenTelemetry SDK configuration. A typical
production setup exports to an OTLP-compatible collector:

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

# Now otel_observe() spans flow to your collector
observed = otel_observe(store)
```

---

**See also:**
[API reference](api/ext-observe.md) --
[Example script](https://github.com/haalfi/remote-store/blob/master/examples/observe_hooks.py)
