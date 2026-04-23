# ext.observe - Observability Hooks Specification

## Overview

`ext.observe` provides a Store-wrapping mechanism that fires user-defined
callbacks before and after each Store operation, enabling logging, metrics,
auditing, and tracing without modifying business code. The implementation
uses a proxy subclass pattern (ADR-0010) with explicit method overrides and
a drift-protection test.

**Module:** `src/remote_store/ext/observe.py`
**Dependencies:** None (pure Python, always available)
**Related:** [001-store-api.md](001-store-api.md) (Store API), ADR-0010, ID-024,
ID-004 (superseded).

---

## Event Model

### OBS-001: StoreEvent Dataclass

**Invariant:** `StoreEvent` is a frozen dataclass with the following fields:

- `operation: str` — operation name (e.g., `"read"`, `"write"`, `"delete"`,
  `"copy"`, `"move"`, `"iter_children"`, `"list_files"`, `"list_folders"`, `"glob"`,
  `"get_file_info"`, `"get_folder_info"`, `"head"`, `"exists"`, `"is_file"`,
  `"is_folder"`, `"read_bytes"`, `"read_text"`, `"write_atomic"`, `"write_text"`,
  `"delete_folder"`, `"to_key"`, `"unwrap"`, `"supports"`).
- `path: str` — store-relative key (first positional path argument). Empty
  string for operations that take no path (e.g., `supports`).
- `backend: str` — backend name from `store._backend.name`.
- `started_at: float` — `time.monotonic()` at method entry.
- `duration_ms: float` — elapsed time in milliseconds.
- `error: Exception | None` — `None` on success, the exception instance on
  failure.
- `metadata: dict[str, Any]` — operation-specific extra data (e.g.,
  `overwrite`, `recursive`, `dst`, `pattern`, `size`, `missing_ok`).
- `correlation_id: str | None` — value from `contextvars.ContextVar`,
  `None` when not set. Allows grouping related events (e.g., a batch
  operation's individual calls).

---

## Factory Function

### OBS-002: observe() Signature

**Invariant:**

```python
def observe(
    store: Store,
    *,
    on_read: OnEvent | None = None,
    on_write: OnEvent | None = None,
    on_delete: OnEvent | None = None,
    on_copy: OnEvent | None = None,
    on_move: OnEvent | None = None,
    on_list: OnEvent | None = None,
    on_error: OnEvent | None = None,
    on_any: OnEvent | None = None,
    around: AroundHook | None = None,
) -> ObservedStore: ...
```

Where:
- `OnEvent = Callable[[StoreEvent], None]` — after-only callback.
- `AroundHook = Callable[[str, str, str], AbstractContextManager[None]]` —
  receives `(operation, path, backend)`, returns a context manager that wraps
  the entire operation including hook dispatch.

**Postconditions:**
- Returns an `ObservedStore` instance wrapping `store`.
- The returned object is a `Store` subclass (`isinstance(result, Store)` is `True`).

**Rationale:** Per-operation hooks allow selective observation. `on_any` is a
catch-all. `on_error` fires on any failed operation regardless of whether a
per-operation hook is registered.

---

## Proxy

### OBS-003: ObservedStore Proxy

**Invariant:** `ObservedStore` is a subclass of `Store` that explicitly
overrides every public method of `Store`. Each override:

1. Records `started_at = time.monotonic()`.
2. Enters the `around` context manager (if set).
3. Delegates to the inner store's method.
4. Computes `duration_ms`.
5. Constructs a `StoreEvent`.
6. Fires the matching `on_<op>` callback (if set), regardless of outcome
   (see OBS-004).
7. Fires `on_any` (if set), regardless of outcome.
8. On exception: fires `on_error` (if set), then re-raises.
9. Returns the result from the inner store.

**Properties:**
- `inner: Store` — read-only property returning the wrapped store.

**Postconditions:**
- The proxy never modifies arguments or return values.
- After-hook exceptions (`on_<op>`, `on_any`, `on_error`) are suppressed
  (logged at WARNING) to prevent observation from breaking the observed
  operation. The `around` context manager follows standard Python semantics:
  exceptions from `__enter__` or `__exit__` propagate (see OBS-005).

### OBS-003a: Hook-to-Operation Mapping

The `on_<op>` hooks map to operations as follows:

| Hook | Operations |
|------|-----------|
| `on_read` | `read`, `read_bytes`, `read_text` |
| `on_write` | `write`, `write_text`, `write_atomic` |
| `on_delete` | `delete`, `delete_folder` |
| `on_copy` | `copy` |
| `on_move` | `move` |
| `on_list` | `iter_children`, `list_files`, `list_folders`, `glob`, `get_file_info`, `get_folder_info`, `head`, `exists`, `is_file`, `is_folder` |

Operations not covered by a specific hook (`to_key`, `unwrap`, `supports`,
`child`, `close`) still fire `on_any` and `on_error`.

---

## Hook Types

### OBS-004: After-Only Hooks (on_<op>)

**Invariant:** Each `on_<op>` callback receives a `StoreEvent` **after** the
operation completes (success or failure). The callback cannot prevent the
operation or modify its result.

### OBS-005: Around Hook

**Invariant:** The `around` callback receives `(operation, path, backend)` and
returns a context manager. The context manager's `__enter__` runs before the
operation; `__exit__` runs after, regardless of success or failure. This
enables before/after instrumentation (e.g., setting trace spans).

**Postconditions:**
- If the `around` context manager raises on `__enter__`, the operation is
  skipped and the exception propagates.
- If the `around` context manager raises on `__exit__`, the exception from
  `__exit__` propagates (standard context manager semantics).

---

## Buffered Observer

### OBS-006: BufferedObserver

**Invariant:** `BufferedObserver` collects events in a thread-safe queue and
periodically flushes them to a user-provided batch handler.

```python
class BufferedObserver:
    def __init__(
        self,
        handler: Callable[[list[StoreEvent]], None],
        *,
        max_queue: int = 1000,
        flush_interval: float = 5.0,
    ): ...
    def on_event(self, event: StoreEvent) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
```

**Properties:**
- `on_event` enqueues a `StoreEvent`. If the queue is full, the event is
  **dropped** and a warning is logged (backpressure).
- `flush` drains the queue and calls `handler` with the batch.
- `close` stops the background flush thread and performs a final flush.
- The background thread is a `daemon` thread with periodic flush every
  `flush_interval` seconds.
- Thread-safe via `queue.Queue`.

---

## Safety

### OBS-007: Drift-Protection Test

**Invariant:** The test suite includes a test that asserts `ObservedStore`
overrides every public method of `Store` (i.e., every callable in
`Store.__dict__` whose name does not start with `_` has a corresponding
entry in `ObservedStore.__dict__`).

**Rationale:** This prevents new Store methods from silently bypassing
observation. See ADR-0010.

---

## Logging Contract

### OBS-008: Intrinsic Logging Conventions

**Invariant:** All library modules follow these conventions:

- Logger variable: `log = logging.getLogger(__name__)`.
- Format: `%`-style (lazy evaluation, ruff G004 compliant).
- Structured context via `extra={}` dict with keys like `backend`, `op`,
  `path` where applicable.
- Levels: DEBUG (method entry), INFO (write/delete/move/copy completion),
  WARNING (retries, fallbacks), ERROR (before re-raise).
- Package init registers `NullHandler`:
  `logging.getLogger("remote_store").addHandler(logging.NullHandler())`.
- Never log inside tight loops (per-chunk streaming).
- Never log sensitive data (credentials, file contents).

---

## Error Handling

### OBS-009: Error Propagation

**Invariant:** `CapabilityNotSupported` and all other exceptions from Store
methods always propagate to the caller. The proxy catches exceptions only
to build the `StoreEvent` (with `error` set) and fire hooks, then
re-raises unconditionally.

After-hook exceptions (from `on_<op>`, `on_any`, `on_error`) are suppressed
and logged at WARNING level. They never mask the original operation's result
or exception. The `around` context manager is not suppressed — its exceptions
propagate per standard context manager semantics (see OBS-005).

---

## Lifecycle

### OBS-010: No Lifecycle Ownership

**Invariant:** `ObservedStore.close()` delegates to the inner store's
`close()` (firing hooks as for any other method). The proxy does not add
its own resources that need cleanup — it has no independent lifecycle.

**Rationale:** Consistent with the extension contract (ADR-0008): extensions
never close the Store. The `ObservedStore` follows the same principle as
`Store.child()` — the outermost owner manages the lifecycle.

---

## OpenTelemetry Bridge

### OBS-011: otel_hooks Factory

**Invariant:** `otel_hooks()` returns a `dict` suitable for unpacking into
`observe()`:

```python
def otel_hooks(
    *,
    tracer_name: str = "remote_store",
    meter_name: str = "remote_store",
    tracer: Tracer | None = None,
    meter: Meter | None = None,
) -> dict[str, Any]: ...
```

The returned dict contains:
- `"around"`: a context-manager factory that creates OTel spans.
- `"on_any"`: a callback that records metrics (counters and histogram).

When `tracer` or `meter` are provided, they are used directly (bypassing
the global providers). When ``None`` (default), the tracer/meter are
obtained from the global `TracerProvider`/`MeterProvider` via the
corresponding `*_name` parameter.

**Postconditions:**
- `observe(store, **otel_hooks())` produces an `ObservedStore` with OTel
  tracing and metrics enabled.
- When `opentelemetry-api` is not installed, importing `ext.otel` raises
  `ImportError`.

### OBS-012: Span Conventions

**Invariant:** Each span emitted by the `around` hook follows these
conventions:

- **Span name:** `store.{operation}` (e.g., `store.read`, `store.write`).
- **Span kind:** `SpanKind.CLIENT`.
- **Attributes:**
  - `remote_store.operation` (str): operation name.
  - `remote_store.backend` (str): backend name.
  - `remote_store.path` (str): store-relative key.
- **On error:**
  - `span.set_status(StatusCode.ERROR, str(exc))`.
  - `span.record_exception(exc)`.
  - `error.type` attribute set to the exception class's qualified name.

### OBS-013: Metric Instruments

**Invariant:** The `on_any` hook records the following metrics:

| Type | Name | Unit | Attributes |
|------|------|------|------------|
| Counter | `remote_store.operations` | `1` | `operation`, `backend`, `status` (`"ok"` or `"error"`) |
| Counter | `remote_store.errors` | `1` | `operation`, `backend`, `error.type` |
| Histogram | `remote_store.operation.duration` | `s` | `operation`, `backend`; plus `error.type` on error |

**Postconditions:**
- `path` is **not** included in metric attributes (high-cardinality risk).
- Duration is recorded in **seconds** (OTel convention), converted from
  `StoreEvent.duration_ms`.

### OBS-014: Import Gating

**Invariant:** `ext.otel` requires `opentelemetry-api>=1.28.0`. The module
performs a top-level `import opentelemetry` and raises `ImportError` if the
package is missing.

`otel_hooks` and `otel_observe` are imported directly from
`remote_store.ext.otel` (ADR-0013).

**Convenience wrapper:**

```python
def otel_observe(
    store: Store,
    *,
    tracer_name: str = "remote_store",
    meter_name: str = "remote_store",
    tracer: Tracer | None = None,
    meter: Meter | None = None,
) -> ObservedStore: ...
```

Equivalent to `observe(store, **otel_hooks(tracer_name=..., meter_name=..., tracer=..., meter=...))`.

### OBS-015: WriteResult in Post-Operation StoreEvent

**Invariant:** After a successful `write`, `write_text`, or `write_atomic`
on the wrapped store, `ObservedStore` injects the returned `WriteResult`
into the post-operation `StoreEvent` under `StoreEvent.metadata["write_result"]`.
The pre-operation phase of `around` and the failure path (exception raised
by the wrapped write) are unchanged — on failure, no `"write_result"` key
is present.

**Postconditions:**

- Successful `write` / `write_text` / `write_atomic`:
  `event.metadata["write_result"]` is the `WriteResult` returned by the
  wrapped store (identity, not a copy).
- `StoreEvent.metadata` keeps its existing `dict[str, Any]` type; access
  via `event.metadata["write_result"]` is explicitly untyped. Callers
  narrow with `isinstance(..., WriteResult)` if static checking is
  required. A typed field on `StoreEvent` is deferred (RFC-0011 Open
  Questions).
- No other `on_<op>` hook injects into `event.metadata` beyond the
  existing per-operation keys (OBS-001).

**Implementation note:** The current `_observe_op` helper is a context
manager that constructs the `StoreEvent` before the wrapped call returns.
Injecting `write_result` requires either (a) mutating `event.metadata`
after the wrapped call completes but before hook dispatch, or (b)
re-constructing the event post-call. The invariant is neutral between
these implementations; the test harness asserts only the observable
contract (`event.metadata["write_result"] is result`).

**See also:** [045-write-result.md](045-write-result.md) (WR-019).
