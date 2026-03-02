# Research: Logging, Monitoring & Tracing for remote-store

**Date:** 2026-03-02
**Backlog items:** ID-004 (Structured logging & metrics hooks), ID-024 (`ext.observe` / `ext.otel`)
**Status:** Implementation complete

> **Note:** All three observability layers are now shipped. See spec
> `019-ext-observe.md` and modules `ext/observe.py` (Layer 2) and
> `ext/otel.py` (Layer 3). The `ext.notify` naming used throughout this
> document was renamed to `ext.observe` during implementation (per Q7
> resolution below). Layer 3 lives in a separate `ext.otel` module
> rather than the nested path sketched in §5.

---

## 1. Executive Summary

This document researches how `remote-store` should approach the three pillars
of observability — **logging**, **monitoring (metrics)**, and **tracing** — as
a Python *library* (not an application). The key distinction matters: libraries
emit signals, applications decide what to do with them.

Our dependencies (boto3/botocore, paramiko, azure-storage-file-datalake, s3fs, fsspec)
all follow the same core pattern: stdlib `logging` with `NullHandler`, plus
optional hooks/callbacks for transfer progress. The Python ecosystem has
converged on OpenTelemetry as the vendor-neutral standard for metrics and
tracing, with a clean API/SDK split designed exactly for our use case.

**Headline recommendations:**

| Concern | Approach | Dependency impact |
|---------|----------|-------------------|
| **Logging** | stdlib `logging` with `NullHandler` — intrinsic to the library | Zero (stdlib) |
| **Monitoring** | Callback hooks in `ext.notify` + optional OTel metrics bridge | Zero core; `opentelemetry-api` as optional extra |
| **Tracing** | Optional OTel spans via `ext.notify` or dedicated bridge | Zero core; `opentelemetry-api` as optional extra |

---

## 2. Current State in remote-store

### 2.1 Existing logging (minimal)

Three locations currently use `logging`:

| Module | Logger name | What's logged | Level |
|--------|-------------|---------------|-------|
| `backends/_sftp.py:42` | `remote_store.backends._sftp` | Connection lifecycle, auto-add warning, tenacity retry sleep | INFO, WARNING |
| `backends/_azure.py:38` | `remote_store.backends._azure` | HNS detection fallback | WARNING |
| `ext/arrow.py:43` | `remote_store.ext.arrow` | Large file materialization | WARNING |

**What's missing:** No logging for read/write/delete/copy/move operations,
no logging in the Store layer, no logging in S3/S3-PyArrow/Local/Memory
backends, no structured context (operation, path, backend, duration).

### 2.2 No NullHandler registered

The library does **not** add a `NullHandler` to the `"remote_store"` top-level
logger. This means applications that don't configure logging see Python's
`lastResort` handler (stderr, WARNING+). This is the correct accidental
behavior for WARNING-only messages, but violates the explicit best practice
and without `NullHandler`, WARNING+ messages leak to stderr via `lastResort`
(Python 3.2+), which is not under application control.

### 2.3 Existing callback pattern

`ext.transfer` already implements `on_progress: Callable[[int], None]` for
upload/download/transfer — a simple per-chunk byte-count callback. This is
the closest existing analog to what `ext.notify` would generalize.

### 2.4 Backlog items

- **ID-004** — "Structured logging & metrics hooks" — adds `logging` calls
  at key points + considers callback/event system. Superseded by ID-024.
- **ID-024** — "`ext.notify` — hooks / middleware / instrumentation" —
  interceptor layer: `store = instrument(store, on_read=..., on_write=...,
  on_error=...)`. Compatible with structlog, stdlib logging, or plain callbacks.

---

## 3. How Our Dependencies Handle Observability

### 3.1 boto3 / botocore (AWS SDK for Python)

**Logging:**
- Uses stdlib `logging` with `NullHandler()` on the `"boto3"` logger.
- Hierarchical loggers: `boto3`, `boto3.resources`, `botocore`,
  `botocore.endpoint`, etc.
- Provides `boto3.set_stream_logger(name, level)` as a convenience for
  enabling debug output.
- WARNING: DEBUG level includes full wire traces with potentially
  sensitive data (request/response bodies, secret values).

**Monitoring:** No built-in metrics. AWS provides CloudWatch for service-side
metrics but the SDK itself exposes nothing.

**Tracing:** No built-in tracing. OpenTelemetry provides
`opentelemetry-instrumentation-botocore` as a separate package that
instruments all AWS API calls with spans.

### 3.2 paramiko (SSH/SFTP)

**Logging:**
- Uses stdlib `logging` throughout: `paramiko.transport`, `paramiko.sftp`,
  `paramiko.auth_handler`, etc.
- Provides `paramiko.util.log_to_file(filename, level)` convenience method.
- Logs SSH handshake, key exchange, auth, channel operations, SFTP commands.
- At DEBUG level: very verbose (packet-level details).

**Monitoring/Tracing:** None. Pure SSH protocol library — no hooks or
instrumentation points. Our SFTP backend already uses tenacity's
`before_sleep_log` which logs retries via paramiko's logger pattern.

### 3.3 azure-storage-file-datalake / azure-core (Azure SDK for Python)

**Logging:**
- Uses stdlib `logging` with hierarchical loggers:
  `azure.storage.blob`, `azure.core.pipeline`, etc.
- Azure's `DistributedTracingPolicy` in the HTTP pipeline automatically
  creates spans for every HTTP call.

**Tracing (notable — most sophisticated of our dependencies):**
- Built-in OpenTelemetry support via `azure-core-tracing-opentelemetry`
  plugin (separate pip install).
- Activation: either `AZURE_SDK_TRACING_IMPLEMENTATION=opentelemetry`
  env var or `settings.tracing_implementation = "opentelemetry"` in code.
- Automatic span creation for every SDK call (e.g., `BlobClient.upload_blob`
  creates a span with blob name, container, account as attributes).
- HTTP-level spans are suppressed when SDK-level spans are active
  (avoids duplicate spans).

**Key takeaway:** Azure SDK demonstrates the "tracing plugin" pattern well —
the core SDK has no hard dependency on OTel, but a bridge package activates
it. This is exactly the pattern we should consider.

### 3.4 s3fs (built on fsspec)

**Logging:**
- Inherits fsspec's logging approach: `logging.getLogger("s3fs")`.
- s3fs itself logs warnings for retries, errors, and cache operations.

**Monitoring:** Inherits fsspec's `Callback` system (see below).

### 3.5 fsspec (filesystem abstraction — our closest peer)

**Logging:**
- Hierarchical stdlib loggers: `fsspec`, `fsspec.http`, `fsspec.fuse`, etc.
- Moderate logging: connection events, cache operations, transfer progress.

**Monitoring — the Callback system (important precedent):**
```python
class Callback:
    """Base for monitoring file transfer operations."""
    def set_size(self, size): ...
    def absolute_update(self, value): ...
    def relative_update(self, inc): ...
    def branch(self, path_1, path_2, kwargs): ...
    def call(self, *args, **kwargs): ...
```
- Methods like `get()`, `put()`, `get_file()`, `put_file()` accept
  `callback=Callback(hooks=...)`.
- `branch()` enables hierarchical callbacks (e.g., multi-file transfer
  where each file gets its own sub-callback).
- `TqdmCallback` provides built-in progress bar support.
- `NoOpCallback` is the default — zero overhead when unused.

**This is relevant for `ext.notify` design:** fsspec demonstrates that
a callback parameter on core methods works well for transfer monitoring.
However, fsspec callbacks are limited to transfer progress — they don't
cover existence checks, metadata, listing, errors, etc.

---

## 4. Python Ecosystem Best Practices

### 4.1 Logging in libraries

The Python documentation and community consensus is clear:

**Rule 1: Libraries use `logging.getLogger(__name__)` — never configure.**
```python
# In remote_store/__init__.py or a dedicated _logging.py:
import logging
logging.getLogger("remote_store").addHandler(logging.NullHandler())
```
The `NullHandler` prevents "No handlers found" warnings. Applications
configure logging; libraries just emit.

**Rule 2: Use `__name__` for hierarchical logger names.**
```
remote_store                         # top-level
remote_store.backends._s3            # S3 backend
remote_store.backends._sftp          # SFTP backend
remote_store.ext.transfer            # transfer extension
```
This gives operators fine-grained control:
```python
logging.getLogger("remote_store.backends._sftp").setLevel(logging.DEBUG)
```

**Rule 3: Never add handlers other than `NullHandler`.**
No `StreamHandler`, no `FileHandler`, no `set_stream_logger()` in library
code. The application decides output destination.

**Rule 4: Don't use custom log levels.**
Stick to DEBUG, INFO, WARNING, ERROR, CRITICAL.

**Rule 5: Be careful with DEBUG — it may contain sensitive data.**
Paths, bucket names, keys are fine. Credentials, file contents are not.
Our backends already mask credentials in `__repr__`.

### 4.2 What to log (specific to remote-store)

Based on what our dependencies log and what operators need:

| Level | What to log | Example |
|-------|-------------|---------|
| **DEBUG** | Every Store/Backend method call with arguments | `store.read('data/file.csv')` → `"read path='data/file.csv'"` |
| **DEBUG** | Internal decisions and fallbacks | `"S3 exists() check for 'bucket/key'"` |
| **INFO** | Connection lifecycle events | `"SFTP connecting to host:22 as user"`, `"SFTP connected"` |
| **INFO** | Significant operations with outcome | `"write path='key' size=1048576 overwrite=True"` |
| **WARNING** | Recoverable anomalies | `"HNS detection failed, falling back to non-HNS"` |
| **WARNING** | Security-relevant choices | `"AUTO_ADD host key policy — not safe for production"` |
| **ERROR** | Operation failures (before raising) | `"read failed path='key': NotFound"` |

### 4.3 structlog vs stdlib logging

**For a library: stick with stdlib `logging`.** Rationale:

- Zero dependencies (remote-store core is zero-dep today).
- Maximum compatibility with every application's logging setup.
- structlog can wrap stdlib — users who want structured JSON output
  can configure structlog in their application and it will pick up
  our stdlib log calls automatically.
- Adding structlog as a dependency would be the first core dependency.

**However:** `ext.notify` should be *compatible* with structlog. If a user
passes a structlog-bound logger to `instrument()`, it should just work.
This is naturally the case if we use stdlib `logging` in the core and
accept any callable/logger in the hook API.

### 4.4 Monitoring (metrics) in libraries

**The modern answer is OpenTelemetry Metrics API:**

```python
# Library code — depends only on opentelemetry-api
from opentelemetry.metrics import get_meter

meter = get_meter("remote_store")
read_counter = meter.create_counter(
    "remote_store.reads",
    description="Number of read operations",
)
read_duration = meter.create_histogram(
    "remote_store.read_duration_seconds",
    description="Duration of read operations",
)
```

**Key properties:**
- `opentelemetry-api` is lightweight (~100KB) and provides no-op
  implementations by default.
- When no SDK is installed, all metrics calls are no-ops — zero overhead.
- When the application installs `opentelemetry-sdk` + an exporter
  (Prometheus, StatsD, OTLP), metrics flow automatically.
- The API is stable and vendor-neutral.

**But there's a tension with zero-dep:** Adding `opentelemetry-api` as
a core dependency would break our zero-dependency promise. Options:

1. **Optional extra:** `pip install remote-store[otel]` adds
   `opentelemetry-api`. Library code does `try: import ... except: pass`
   and no-ops itself when not installed.
2. **Callback hooks only:** `ext.notify` provides raw callbacks
   (`on_read`, `on_write`, etc.). A separate bridge function converts
   these to OTel metrics. This keeps core zero-dep.
3. **Both:** Core uses callbacks. An optional
   `ext.notify.otel_bridge(store)` wires callbacks to OTel. Best of
   both worlds.

**Recommended: Option 3.** This mirrors what Azure SDK does.

### 4.5 Tracing (distributed tracing) in libraries

**Same approach — OpenTelemetry Tracing API:**

```python
from opentelemetry import trace

tracer = trace.get_tracer("remote_store")

with tracer.start_as_current_span("store.read", attributes={
    "remote_store.backend": "s3",
    "remote_store.path": "data/file.csv",
}) as span:
    result = backend.read(path)
    span.set_attribute("remote_store.bytes", len(result))
```

**Key properties:**
- Same `opentelemetry-api` dependency as metrics.
- No-op when SDK is not installed.
- Traces automatically propagate context through the call chain.
- Span attributes provide structured metadata (backend, path, size,
  duration, error type).

**Semantic conventions:** OTel has no "file storage" semantic conventions
yet, but we can define our own namespace: `remote_store.*`.

**Same zero-dep tension, same solution:** Optional extra + bridge in
`ext.notify`.

---

## 5. Proposed Design Direction

Based on this research, the observability story for remote-store should
be layered:

### Layer 1: Intrinsic logging (stdlib, zero-dep)

**Scope:** Inside the library itself — Store, backends, extensions.

**What changes:**
1. Add `logging.getLogger("remote_store").addHandler(logging.NullHandler())`
   in `__init__.py`.
2. Add `log = logging.getLogger(__name__)` to every module.
3. Add DEBUG/INFO/WARNING/ERROR calls at key points (see §4.2 table).
4. Log structured context using `%s`-style formatting (lazy evaluation):
   ```python
   log.debug("read path=%r backend=%r", path, self.name)
   ```

**Dependency impact:** Zero. Stdlib only.

**This is ID-004** (the non-metrics part). It can ship independently
of `ext.notify`.

### Layer 2: Callback hooks (`ext.notify`, zero-dep core)

> **Naming note:** Q7 in §9 proposes renaming to `ext.observe`. Sketches
> below still use `ext.notify` pending RFC acceptance.

**Scope:** `ext.notify` provides a Store-wrapping mechanism that fires
user-defined callbacks before/after each Store operation.

**Sketch:**
```python
from remote_store.ext.notify import instrument

def on_read(event):
    print(f"Read {event.path} from {event.backend} in {event.duration_ms}ms")

store = instrument(store, on_read=on_read, on_write=on_write, on_error=on_error)
# store is now a proxy — all calls pass through, firing hooks
```

**Event model:**
```python
@dataclasses.dataclass(frozen=True)
class StoreEvent:
    operation: str          # "read", "write", "delete", "list_files", ...
    path: str               # store-relative key
    backend: str            # backend name
    started_at: float       # time.monotonic() start
    duration_ms: float      # elapsed milliseconds
    error: Exception | None # None on success
    metadata: dict          # operation-specific: size, overwrite, recursive, ...
```

**Proxy pattern:** The instrumented store wraps the original, delegating
all calls and emitting events. Two possible implementations:

- **A) Subclass/wrapper Store** that overrides every method.
- **B) `__getattr__` proxy** that intercepts calls dynamically.

Option A is safer (explicit, type-checked, IDE-friendly). Option B is
terser but loses type safety. **Recommend A**, with the following caveat:

**Maintenance hazard of Option A:** `Store` has 20+ public methods today.
When a new method is added, `InstrumentedStore` silently inherits the
un-instrumented base version — calls bypass hooks with no warning. Option B
(`__getattr__`) catches new methods automatically, but loses type safety
and IDE support.

**Mitigation — hybrid approach:** Use Option A (explicit overrides) plus
a test that asserts `InstrumentedStore` overrides every public method of
`Store`. This catches drift at CI time:
```python
def test_instrumented_store_covers_all_public_methods():
    store_methods = {
        m for m in vars(Store)
        if not m.startswith("_") and callable(getattr(Store, m))
    }
    overridden = set(vars(InstrumentedStore)) & store_methods
    missing = store_methods - overridden
    assert not missing, f"InstrumentedStore missing overrides: {missing}"
```
The RFC should specify this test as a required safeguard for Option A.

**Dependency impact:** Zero (pure Python, stdlib `dataclasses` + `time`).

### Layer 3: OpenTelemetry bridge (optional extra)

**Scope:** Pre-built hook implementations that emit OTel traces + metrics
from the `ext.notify` events.

**Sketch:**
```python
from remote_store.ext.notify import instrument
from remote_store.ext.notify.otel import otel_hooks  # requires opentelemetry-api

store = instrument(store, **otel_hooks())
# Now emits OTel spans for every operation, plus counters/histograms
```

**What `otel_hooks()` returns:**
```python
def otel_hooks():
    tracer = trace.get_tracer("remote_store")
    meter = metrics.get_meter("remote_store")
    op_counter = meter.create_counter("remote_store.operations")
    op_duration = meter.create_histogram("remote_store.operation_duration_seconds")
    error_counter = meter.create_counter("remote_store.errors")

    def on_read(event): ...
    def on_write(event): ...
    def on_error(event): ...

    return {"on_read": on_read, "on_write": on_write, "on_error": on_error, ...}
```

**Dependency:** `opentelemetry-api` as an optional extra:
```toml
[project.optional-dependencies]
otel = ["opentelemetry-api>=1.20"]
```

**No SDK dependency.** The application provides the SDK + exporter.

### Layer overview

```
┌─────────────────────────────────────────────────────┐
│  Application                                        │
│  ┌──────────────────────────────────────────┐       │
│  │  OpenTelemetry SDK + Exporter            │       │
│  │  (Prometheus, Jaeger, OTLP, Datadog...)  │       │
│  └──────────────┬───────────────────────────┘       │
│                 │ receives spans + metrics           │
│  ┌──────────────┴───────────────────────────┐       │
│  │  Layer 3: ext.notify.otel bridge         │       │
│  │  (optional: opentelemetry-api)           │       │
│  └──────────────┬───────────────────────────┘       │
│                 │ translates events → OTel           │
│  ┌──────────────┴───────────────────────────┐       │
│  │  Layer 2: ext.notify callback hooks      │       │
│  │  (zero-dep, pure Python)                 │       │
│  └──────────────┬───────────────────────────┘       │
│                 │ wraps Store, emits events          │
│  ┌──────────────┴───────────────────────────┐       │
│  │  Layer 1: stdlib logging                 │       │
│  │  (zero-dep, intrinsic to the library)    │       │
│  └──────────────┬───────────────────────────┘       │
│                 │                                    │
│  ┌──────────────┴───────────────────────────┐       │
│  │  remote-store core                       │       │
│  │  Store → Backend → cloud/local/memory    │       │
│  └──────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────┘
```

---

## 6. Comparison with Peer Libraries

| Library | Logging | Metrics | Tracing | Callbacks |
|---------|---------|---------|---------|-----------|
| **boto3/botocore** | stdlib + NullHandler | None | Via `otel-instrumentation-botocore` | None |
| **paramiko** | stdlib throughout | None | None | None |
| **azure-storage-file-datalake** | stdlib + pipeline | Azure Monitor | Built-in OTel plugin (`azure-core-tracing-opentelemetry`) | None |
| **fsspec** | stdlib hierarchical | None | None | `Callback` class for transfers |
| **s3fs** | stdlib (inherits fsspec) | None | None | Inherits fsspec `Callback` |
| **smart_open** | stdlib | None | None | `on_progress` callback |
| **requests** | stdlib + NullHandler | None | Via `otel-instrumentation-requests` | Hooks (response, auth) |
| **httpx** | stdlib | None | Via `otel-instrumentation-httpx` | Event hooks |
| **remote-store (proposed)** | stdlib + NullHandler | Via ext.notify + OTel bridge | Via ext.notify + OTel bridge | ext.notify events |

**Observation:** Our proposed approach is more comprehensive than most peers.
Only Azure SDK has built-in tracing support, and even that requires an
optional package. We'd be in good company.

---

## 7. Metrics to Expose

If we build the OTel bridge, these are the key metrics:

### Counters
| Metric | Description | Attributes |
|--------|-------------|------------|
| `remote_store.operations` | Total operations | `operation`, `backend`, `status` (ok/error) |
| `remote_store.errors` | Total errors | `operation`, `backend`, `error_type` |
| `remote_store.bytes_read` | Total bytes read | `backend` |
| `remote_store.bytes_written` | Total bytes written | `backend` |

### Histograms
| Metric | Description | Attributes |
|--------|-------------|------------|
| `remote_store.operation_duration_seconds` | Operation latency | `operation`, `backend` |

### Attributes (span + metric labels)
| Attribute | Description | Example |
|-----------|-------------|---------|
| `remote_store.backend` | Backend type | `"s3"`, `"sftp"`, `"azure"` |
| `remote_store.operation` | Operation name | `"read"`, `"write"`, `"list_files"` |
| `remote_store.path` | Store-relative path | `"data/file.csv"` |
| `remote_store.status` | Outcome | `"ok"`, `"error"` |
| `remote_store.error_type` | Error class name | `"NotFound"`, `"PermissionDenied"` |

---

## 8. Implementation Sequencing

The three layers can ship independently:

| Phase | What | Backlog | Est. complexity | Breaking? |
|-------|------|---------|-----------------|-----------|
| **Phase 1** | NullHandler + intrinsic logging | ID-004 | Low | No |
| **Phase 2** | `ext.notify` with callback hooks | ID-024 | Medium | No |
| **Phase 3** | OTel metrics + tracing bridge | ID-024 (sub-part) | Medium | No |

**Phase 1** is a good first PR — small, non-breaking, immediately useful
for debugging. It's purely additive (log statements) and requires no new
API design.

**Phase 2** is the main design challenge — the proxy Store pattern,
event model, and hook signature. Needs an RFC + spec.

**Phase 3** is straightforward once Phase 2 exists — it's just pre-built
hook implementations using the OTel API.

---

## 9. Open Questions — Proposals

These should be resolved during RFC/spec work. Each includes a concrete
proposal with rationale.

### Q1. `instrument()` function vs `InstrumentedStore` class?

**Proposal: Class (`InstrumentedStore`) with `instrument()` factory.**

```python
# User-facing API (factory function)
store = instrument(store, on_read=on_read, on_write=on_write)

# Under the hood
class InstrumentedStore(Store):
    """Proxy that delegates to an inner Store and fires hooks."""
    def unwrap(self) -> Store: ...
```

**Rationale:**
- `instrument()` is the simple entry point (matches §5 sketch).
- The class is the implementation — users don't construct it directly.
- `isinstance(store, InstrumentedStore)` lets code detect instrumentation
  (useful for "don't double-wrap" guards).
- `.unwrap()` is consistent with `Store.unwrap()` for PyArrow
  (precedent: ID-016). It lets middleware layers peel back instrumentation
  when they need the raw Store (e.g., for native-path passthrough).
- Type-checkers see `InstrumentedStore` as a `Store` — no protocol tricks.

### Q2. Sync-only or async hooks?

**Proposal: Sync-only for v1. Async-ready event model.**

```python
# v1: sync hooks only
def on_read(event: StoreEvent) -> None: ...

# Future v2 (when async Store ships via ID-013):
async def on_read_async(event: StoreEvent) -> None: ...
```

**Rationale:**
- No async Store exists yet (ID-013 is unprioritized).
- Designing async hooks now means specifying event-loop behavior
  (which loop? `asyncio.run`? fire-and-forget?) with zero users to
  validate against.
- The `StoreEvent` dataclass is async-agnostic — adding `async` hooks
  later requires only a new hook signature, not a new event model.
- Precedent: `httpx` started sync-only hooks and added async later.

### Q3. Before + after events, or after-only?

**Proposal: Context-manager-style hooks (covers both).**

```python
from contextlib import contextmanager

@contextmanager
def tracing_hook(operation: str, path: str, backend: str):
    """Before/after via context manager."""
    span = tracer.start_span(f"store.{operation}")
    try:
        yield span          # "before" — span is open
    except Exception as exc:
        span.record_exception(exc)
        raise
    finally:
        span.end()          # "after" — span is closed

store = instrument(store, around=tracing_hook)
```

But **also** keep the simple after-only hooks for the common case:

```python
# Simple after-only (logging, metrics — 90% of use cases)
store = instrument(store, on_read=lambda e: print(e))

# Context-manager (tracing, circuit-breaking — 10% of use cases)
store = instrument(store, around=tracing_hook)
```

**Rationale:**
- After-only is simpler and covers logging + metrics (the majority).
- Tracing fundamentally needs before+after (span lifecycle).
- A context-manager is the Pythonic way to express "around" advice —
  no need to invent `on_before_read` / `on_after_read` pairs.
- Two hook types (`on_<op>` for after, `around` for context-manager)
  is a clean split. The `around` hook runs first, the `on_<op>` hooks
  run inside it (after the operation completes).
- Precedent: Django middleware uses `__call__` as a context-manager-like
  pattern; pytest fixtures use `yield`-based setup/teardown.

### Q4. Should `ext.notify` capture `ext.transfer` operations?

**Proposal: Yes, but at both levels.**

```
transfer(src_store, dst_store, key)
  └─ src_store.read(key)    → StoreEvent(op="read", ...)
  └─ dst_store.write(key, data) → StoreEvent(op="write", ...)
  └─ (implicit)             → StoreEvent(op="transfer", ...)
```

**Design:**
- Individual `read`/`write` events fire automatically (the instrumented
  stores see every call — no special handling needed).
- `ext.transfer` emits a **composite** `transfer` event via a top-level
  `around` hook or explicit `StoreEvent(op="transfer", metadata={"src": ..., "dst": ...})`.
- The composite event carries `metadata.src_backend`, `metadata.dst_backend`,
  `metadata.src_path`, `metadata.dst_path`, total `duration_ms`.

**Rationale:**
- Users want both: "how long did the read take?" (per-op) and "how long
  did the transfer take end-to-end?" (composite).
- Not capturing the composite event makes `ext.transfer` invisible to
  monitoring — users would only see disconnected read+write pairs.
- Implementation: `ext.transfer` calls a package-internal helper to emit
  the composite event. If the store is not instrumented, it's a no-op.

### Q5. Adopt fsspec's `Callback` pattern?

**Proposal: No. Keep `on_progress` in `ext.transfer`, separate from `ext.notify`.**

**Rationale:**
- `on_progress` (bytes transferred) and `ext.notify` (operation events)
  serve different audiences: progress bars vs monitoring.
- fsspec's `Callback` class is heavyweight (6 methods, branching for
  sub-operations). Our `on_progress: Callable[[int], None]` is simpler
  and already shipped (v0.9.0).
- If `batch_copy` with `concurrent=True` (ID-035) needs per-file
  progress, we can add `on_file_progress` to `ext.batch` — still a
  simple callback, not a `Callback` class hierarchy.
- Merging progress into `ext.notify` conflates "UI feedback" with
  "operational telemetry." Keep them separate.

### Q6. `opentelemetry-api` as core or optional dependency?

**Proposal: Optional extra, gated at import time.**

```toml
# pyproject.toml
[project.optional-dependencies]
otel = ["opentelemetry-api>=1.20"]
```

```python
# ext/notify/otel.py — top of file
try:
    from opentelemetry import trace, metrics
except ImportError as exc:
    raise ImportError(
        "Install remote-store[otel] for OpenTelemetry support"
    ) from exc
```

**Rationale:**
- Core stays zero-dep (project principle).
- `opentelemetry-api` alone is ~200KB, pulls in `deprecated` and
  `importlib-metadata`. Acceptable as an optional extra, not as a core
  tax on every user.
- The OTel API is already designed to no-op when no SDK is installed,
  but requiring the import means we don't need no-op shims in our code.
- Precedent: every peer library (boto3, requests, httpx) uses external
  OTel instrumentation packages, not bundled OTel.

### Q7. Naming: `ext.notify` vs `ext.observe` vs `ext.instrument`?

**Proposal: `ext.observe`.**

| Name | Pros | Cons |
|------|------|------|
| `ext.notify` | Backlog uses it; clear "events are sent" | Implies push-based pub/sub; sounds like notifications/alerts |
| `ext.observe` | Aligns with "observability"; verb form reads well: `observe(store)` | Slightly generic |
| `ext.instrument` | OTel term of art; familiar to ops folk | `instrument(store)` is the function, `ext.instrument` is the module — name collision reads odd |

**`ext.observe` wins because:**
- The module name is `ext.observe`, the factory function is `observe()`:
  `from remote_store.ext.observe import observe` — clean, no stutter.
- "Observe" is the verb form of "observability" — the exact concept
  this feature delivers. It covers logging, metrics, and tracing
  without implying only one of them.
- `ext.notify` sounds like it sends notifications (email, Slack, webhook).
  That's a potential user confusion.
- `ext.instrument` has the module/function name collision problem.
  `from remote_store.ext.instrument import instrument` stutters.

**Migration:** Update ID-024 description in BACKLOG.md from `ext.notify`
to `ext.observe` when the RFC ships. The backlog name was a placeholder.

### Q8. Thread safety of callbacks

**Proposal: Document "callbacks must be fast" + provide a `BufferedObserver` adapter.**

```python
# User guide: "Callbacks run synchronously on the calling thread.
# They block the Store operation until they return. Keep callbacks
# fast — log a line, increment a counter, append to a list."

# For slow callbacks (HTTP POST, database write), use the adapter:
from remote_store.ext.observe import observe, BufferedObserver

slow_hook = BufferedObserver(
    on_read=post_to_metrics_endpoint,
    max_queue=1000,
    flush_interval=5.0,  # seconds
)
store = observe(store, on_read=slow_hook.on_read)

# BufferedObserver appends events to a queue and flushes in a
# background thread. Drops events if queue is full (backpressure).
```

**Rationale:**
- "Callbacks must be fast" is the right default — simple, predictable,
  no hidden threads.
- But we know people will want to POST metrics to an HTTP endpoint.
  Without an adapter, they'll write their own buggy queue. Better to
  provide one.
- `BufferedObserver` is a separate class, not built into the core
  `observe()` machinery. It's optional, explicit, and testable.
- Ship `BufferedObserver` in Phase 2 (same PR as `ext.observe`), not
  Phase 1. It's a convenience, not a prerequisite.

### Q9. Correlation across related operations

**Proposal: Layer 1 stays uncorrelated. Layer 2 uses `contextvars`.**

```python
import contextvars

# In ext/observe.py
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rs_correlation_id", default=None
)

# The around hook sets it for composite operations:
@contextmanager
def _transfer_span(operation, path, backend):
    token = _correlation_id.set(uuid4().hex[:8])
    try:
        yield
    finally:
        _correlation_id.reset(token)

# StoreEvent includes it when set:
@dataclasses.dataclass(frozen=True)
class StoreEvent:
    operation: str
    path: str
    backend: str
    duration_ms: float
    error: Exception | None
    metadata: dict
    correlation_id: str | None  # from contextvars, None if not in a composite op
```

**Rationale:**
- Layer 1 (stdlib logging) is intentionally simple — adding
  `correlation_id` to every `extra={}` dict complicates every log call
  for a feature most users won't use.
- Layer 2 (`ext.observe`) already wraps Store calls — it's the natural
  place to manage correlation context.
- `contextvars` is stdlib, thread-safe, and async-compatible. It's the
  standard mechanism for request-scoped context in Python.
- The `correlation_id` propagates automatically to inner `read`/`write`
  events during a `transfer()`, letting users see that the read and
  write belong to the same transfer.
- Users who want correlation in Layer 1 can add a stdlib `logging.Filter`
  that reads `_correlation_id.get()` — documented as an advanced pattern
  in the user guide.

---

## 10. Style Decisions

Resolved style choices for intrinsic logging (Layer 1). These apply to
all modules under `src/remote_store/`.

### 10.1 Logger variable name: `log`

```python
import logging

log = logging.getLogger(__name__)
```

**Rationale:** Reads naturally at call sites (`log.info(...)` is terse and
functional). No PEP prescribes `logger` vs `log`; consistency within the
project is what matters. `log` is used by paramiko and many production
codebases.

**Rule:** Every module uses `log = logging.getLogger(__name__)`. No other
names (`logger`, `LOG`, `_log`).

### 10.2 Message formatting: `%`-style everywhere

```python
log.info("write complete: %s (%d bytes)", path, size)
log.debug("retry attempt %d/%d for %s", attempt, max_retries, path)
```

**Rationale:**
- **Lazy interpolation.** The `%` formatting is deferred until the message
  is actually emitted. With f-strings, the string is always built, even
  when the log level would suppress it. For a library where the application
  controls log levels, this is the correct default.
- **Lint compliance.** ruff rule `G004` (`logging-fstring-interpolation`)
  flags f-strings in log calls. Using `%`-style avoids needing to disable
  or ignore the rule.
- **Ecosystem convention.** The stdlib logging docs, Django, requests, and
  boto3 all use `%`-style. Following the convention reduces surprise for
  contributors and consumers.

**Rules:**
1. Always use `%`-style: `log.info("msg %s", arg)`, never `log.info(f"msg {arg}")`.
2. Keep the message string human-readable — it's what a developer sees
   in `tail -f` or a terminal.
3. Never put sensitive data (credentials, tokens, connection strings) in
   the message or in `extra`.

### 10.3 Structured context: `extra={}` for machine-parseable fields

```python
log.info(
    "write complete: %s (%d bytes)", path, size,
    extra={"backend": "s3", "path": path, "size": size, "op": "write"},
)
```

**Rationale:**
- The `extra` dict populates `LogRecord` attributes that structured
  logging tools (Splunk, Datadog, ELK, structlog `ProcessorFormatter`)
  can index and query.
- The message string is for humans; `extra` is for monitoring. Both are
  present in every log call, serving different audiences from the same
  line of code.
- When an application configures structlog to wrap stdlib, `extra` fields
  automatically appear in structured output. When using plain formatters,
  they are still accessible on the `LogRecord` but do not clutter the
  default output.

**Rules:**
1. All log calls at INFO or above that relate to store operations SHOULD
   include `extra={}` with at minimum `backend` and `op`.
2. DEBUG-level calls MAY include `extra` when the structured data is
   useful for diagnostics.
3. The `extra` keys use a flat namespace: `backend`, `op`, `path`, `size`,
   `duration_s`, `error`, `attempt`, `max_retries`. No nesting.
4. Numeric values use native types (`int`, `float`), not stringified forms.

### 10.4 Log levels

| Level     | Use for                                                      | Example                                        |
|-----------|--------------------------------------------------------------|-------------------------------------------------|
| `DEBUG`   | Operation details useful during development/troubleshooting  | `"opening SFTP channel to %s:%d"`               |
| `INFO`    | Successful operations at the public API boundary             | `"write complete: %s (%d bytes)"`               |
| `WARNING` | Recoverable issues: retries, fallbacks, deprecations         | `"retry attempt %d/%d for %s"`                  |
| `ERROR`   | Failures that propagate as exceptions                        | `"write failed: %s — %s"`                       |

**Rules:**
1. Never use `CRITICAL` — a library should not declare anything critical.
2. One INFO per public API call (entry or exit, not both) to avoid noise.
3. Retries log each attempt at WARNING, not just the final failure.
4. Stack traces via `log.exception()` or `exc_info=True` only at ERROR.

### 10.5 Exception logging patterns

```python
# Pattern: log in the except block, before re-raising
try:
    result = self._client.get_object(Bucket=bucket, Key=key)
except ClientError as exc:
    log.error(
        "read failed: %s — %s", path, exc,
        extra={"backend": "s3", "op": "read", "path": path,
               "error": type(exc).__name__},
    )
    raise self._classify_error(exc, path) from exc
```

**Rules:**
1. Log at ERROR in the `except` block, **before** re-raising the mapped
   exception. This ensures every failure appears in logs even if the
   caller swallows the mapped exception.
2. Use `log.error(...)` with `extra={"error": type(exc).__name__}` for
   machine-parseable error classification. Do **not** put the full
   traceback in `extra` — it belongs in the message via `exc_info=True`
   only when the traceback adds diagnostic value (e.g., unexpected
   internal errors, not routine `NotFound`).
3. Use `log.exception(...)` (which implies `exc_info=True`) only for
   truly unexpected errors where the full stack trace aids diagnosis.
   For expected/classified errors (`NotFound`, `AlreadyExists`), plain
   `log.error(...)` is sufficient — the exception class name in `extra`
   is enough.
4. Never log and swallow — if you catch it and log it, always re-raise
   (or let the caller know). Silent failures are worse than no logging.

### 10.6 Performance: what NOT to log

```python
# BAD — inside a tight read loop, creates dict per chunk
for chunk in stream:
    log.debug("chunk %d bytes", len(chunk),
              extra={"backend": "s3", "op": "read_chunk", "size": len(chunk)})

# GOOD — log once at entry/exit, not per-chunk
log.debug("read started: %s", path, extra={"backend": "s3", "op": "read"})
stream = self._client.get_object(...)
# ... return stream, log completion in the caller or wrapper
```

**Rules:**
1. **Never log inside tight loops** (per-chunk streaming, retry inner
   loops). One log line per public API call, not per iteration.
2. **`extra={}` is cheap but not free.** Dict creation + attribute
   setting on `LogRecord` costs ~0.5µs per call. At DEBUG level this is
   noise; at 10,000 calls/s in a streaming pipeline it adds up. Restrict
   `extra` to INFO+ on hot paths.
3. **Guard expensive argument computation:**
   ```python
   if log.isEnabledFor(logging.DEBUG):
       log.debug("list returned %d files", len(files),
                 extra={"backend": "s3", "op": "list_files", "count": len(files)})
   ```
   The `isEnabledFor` check costs ~30ns vs building the `extra` dict.
   Use this guard only when the arguments themselves are expensive
   (e.g., `len()` on a large list, `repr()` on a complex object).
   For simple string/int arguments, `%`-style lazy formatting is
   sufficient — no guard needed.

### 10.7 `extra` key namespacing

Our `extra` keys (`backend`, `op`, `path`, `size`, etc.) are
intentionally **un-namespaced** — they populate `LogRecord` attributes
directly.

**Risk:** If an application configures a logging `Filter` or structlog
processor that also sets `backend` or `path`, the values collide on the
`LogRecord`. This is a known stdlib limitation (there is no `extra`
isolation).

**Decision: accept the risk, document it.** Rationale:
- Namespaced keys (`rs_backend`, `remote_store.backend`) are ugly at
  every call site and in every Splunk/Datadog query.
- Collision requires the application to deliberately use the same key
  names in their own `extra` dicts, which is unlikely and easy to fix.
- The Layer 2 `ext.notify` event model (`StoreEvent.backend`) is fully
  isolated — it's a dataclass, not a shared dict.
- Document in the user guide: "remote-store uses these `extra` keys:
  `backend`, `op`, `path`, `size`, `duration_s`, `error`, `attempt`,
  `max_retries`. Avoid reusing these names in your own log `extra`."

### 10.8 Deprecation warnings

Deprecations use `warnings.warn()`, **not** `log.warning()`:

```python
import warnings

warnings.warn(
    "Store.old_method() is deprecated, use Store.new_method() instead",
    DeprecationWarning,
    stacklevel=2,
)
```

**Rationale:**
- PEP 565 standardizes `DeprecationWarning` for libraries. Python's
  warning system integrates with `-W` flags, `pytest -W error`, and
  `PYTHONWARNINGS` — none of which work with `log.warning()`.
- Deprecations are code-health signals for **developers reading code
  or running tests**, not operational signals for **operators reading
  logs**. Different audience, different channel.

**Rule:** `log.warning()` is for runtime anomalies (retries, fallbacks).
`warnings.warn(..., DeprecationWarning, stacklevel=2)` is for API
deprecations. Never mix them.

### 10.9 Testing strategy

All logging assertions use pytest's `caplog` fixture:

```python
def test_write_logs_completion(caplog, store):
    with caplog.at_level(logging.INFO, logger="remote_store"):
        store.write("test.txt", b"data")
    assert "write complete" in caplog.text
    # Verify structured extra fields
    record = caplog.records[-1]
    assert record.op == "write"
    assert record.backend == "memory"
```

**Rules:**
1. Phase 1 spec should include test IDs for logging behavior — at
   minimum: NullHandler registered, INFO on write, WARNING on retry,
   ERROR on failure, no logging above WARNING during normal operations.
2. Test the `extra` fields by accessing `LogRecord` attributes directly
   (`record.backend`, `record.op`), not by parsing the message string.
3. Use `caplog.at_level(level, logger="remote_store")` to scope
   assertions to our logger hierarchy. Never assert against the root
   logger.
4. Do **not** test exact message strings (they're for humans and may
   change). Test for key substrings and structured `extra` values.

### 10.10 Migration of existing logging

Three modules currently use logging with inconsistent conventions:

| Module | Current variable | Current style | Action |
|--------|-----------------|---------------|--------|
| `backends/_sftp.py` | `log` | `%`-style, no `extra` | Add `extra` to existing calls |
| `backends/_azure.py` | `_log` | `exc_info=True`, no `extra` | Rename to `log`, add `extra` |
| `ext/arrow.py` | `logger` | `%`-style, no `extra` | Rename to `log`, add `extra` |

**Rule:** Migration happens as part of Phase 1 (ID-004), same PR as the
NullHandler addition and new logging calls. This is not a separate task —
consistency must be established in a single commit.

### 10.11 Summary table

| Concern                | Decision            | Enforced by         |
|------------------------|---------------------|---------------------|
| Variable name          | `log`               | Code review         |
| Format style           | `%`-style           | ruff `G004`         |
| Structured context     | `extra={}`          | Code review         |
| Sensitive data         | Never logged        | AF-008 + review     |
| NullHandler            | Top-level `__init__` | Test (Layer 1 impl) |
| Logger per module      | `__name__`          | Code review         |
| Exception logging      | `except` block, before re-raise | Code review |
| Tight-loop logging     | Never               | Code review         |
| `extra` namespacing    | Un-namespaced, documented | User guide    |
| Deprecations           | `warnings.warn()`   | Code review         |
| Testing                | `caplog` + `extra` attrs | Spec tests    |
| Migration              | Phase 1, single PR  | PR checklist        |

---

## 11. Additional Design Precedents (from extended research)

The following patterns from our dependencies and the broader ecosystem
are especially relevant to `ext.notify` design.

### 11.1 Azure SDK's `@distributed_trace` decorator

Azure SDK applies a `@distributed_trace` decorator to every public client
method. This is the most comprehensive approach found in any studied library:

```python
# Azure SDK internal pattern (simplified)
from azure.core.tracing.decorator import distributed_trace

class BlobClient:
    @distributed_trace
    def upload_blob(self, data, **kwargs):
        # Span is automatically created, named "BlobClient.upload_blob"
        ...
```

The decorator:
- Creates a span wrapping the entire method call.
- Names the span `<ClassName>.<method_name>`.
- Propagates W3C Trace Context in outgoing HTTP requests.
- Can be opted out per-call via `TracingOptions`.

**Relevance to remote-store:** A similar decorator or proxy method pattern
in `ext.notify` could wrap Store methods consistently. The proxy pattern
(our preferred approach) achieves the same effect without requiring
decorators on the core Store class.

### 11.2 Botocore event system

Botocore (the engine behind boto3) has a rich event system with events like:
- `before-send` — fired before each HTTP request
- `after-call` — fired after a successful API call
- `after-call-error` — fired after a failed API call
- `needs-retry` — fired when the retry handler evaluates a response

This event system is how `opentelemetry-instrumentation-botocore` attaches
without modifying botocore source code. It supports `request_hook` and
`response_hook` callbacks for custom span enrichment.

**Relevance to remote-store:** Our `ext.notify` event model (§5, Layer 2)
is analogous. The botocore approach validates that before/after events
with hooks work well at scale. However, botocore events are registered
on a Session (mutable global state), while our proxy pattern is per-Store
(safer, more explicit).

### 11.3 httpx event hooks

httpx offers two levels of hooks:
- **Client-wide** `event_hooks={"request": [...], "response": [...]}` on
  the client constructor.
- **Per-request** `extensions={"trace": callback}` for fine-grained
  transport-level event monitoring (connection attempts, TLS handshakes,
  response headers, etc.).

**Relevance:** The two-level pattern (global + per-operation) is worth
considering for `ext.notify`. The proxy approach naturally gives per-Store
hooks. Per-operation hooks (e.g., `store.read("file.csv", hooks=...)`)
would add complexity — defer unless a real use case emerges.

### 11.4 Context propagation via `contextvars`

Python's `contextvars` module (stdlib, 3.7+) is the standard for
propagating context (request IDs, correlation IDs) across async boundaries.
structlog integrates with it for bound-logger context.

**Relevance:** `ext.notify` events should carry the current `contextvars`
context so that tracing bridges can attach spans to the correct parent.
The OpenTelemetry API handles this automatically via `Context`, but
callback-only users may want access to a correlation ID. Consider adding
an optional `context` field to `StoreEvent` (§5, Layer 2).

### 11.5 Using `extra={}` for structured log context

Libraries can pass structured context via stdlib logging's `extra` parameter:

```python
logger.info("write complete", extra={"backend": "s3", "path": key, "size": 4096})
```

When the application uses structlog's `ProcessorFormatter` on stdlib handlers,
these `extra` fields are automatically included in structured output. When
using plain formatters, the `extra` fields are available on the `LogRecord`
but not printed unless the format string references them.

**Relevance:** Our intrinsic logging (Layer 1) should use `extra={}` for
backend name, path, operation, and byte counts. This gives structured
logging users rich context for free.

---

## 12. References

### Python logging
- [Logging HOWTO — Python 3.14 docs](https://docs.python.org/3/howto/logging.html)
- [Logging Cookbook — Python 3.14 docs](https://docs.python.org/3/howto/logging-cookbook.html)
- [The Hitchhiker's Guide to Python — Logging](https://docs.python-guide.org/writing/logging/)
- [Python Logging Best Practices — Real Python](https://realpython.com/ref/best-practices/logging/)
- [10 Best Practices for Logging in Python — Better Stack](https://betterstack.com/community/guides/logging/python/python-logging-best-practices/)

### structlog
- [structlog documentation](https://www.structlog.org/en/stable/standard-library.html)
- [structlog Issue #179 — How to use structlog in a library](https://github.com/hynek/structlog/issues/179)
- [Comprehensive Guide to structlog — Better Stack](https://betterstack.com/community/guides/logging/structlog/)

### OpenTelemetry
- [OTel Python Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [OTel Libraries instrumentation guide](https://opentelemetry.io/docs/languages/python/libraries/)
- [OTel Library Design Principles (Specification)](https://opentelemetry.io/docs/specs/otel/library-guidelines/)
- [OTel API vs SDK — SigNoz](https://signoz.io/comparisons/opentelemetry-api-vs-sdk/)
- [OTel API vs SDK — Last9](https://last9.io/blog/opentelemetry-api-vs-sdk/)
- [OTel Python Contrib (GitHub)](https://github.com/open-telemetry/opentelemetry-python-contrib)
- [OTel Botocore Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/botocore/botocore.html)

### Dependency observability
- [Boto3 logging reference](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/boto3.html)
- [Botocore event system](https://botocore.amazonaws.com/v1/documentation/api/latest/topics/events.html)
- [Azure Core Tracing OpenTelemetry](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/core/azure-core-tracing-opentelemetry/README.md)
- [Azure Core Tracing — Microsoft Learn](https://learn.microsoft.com/en-us/python/api/overview/azure/core-tracing-opentelemetry-readme?view=azure-python-preview)
- [Azure SDK distributed tracing blog post](https://devblogs.microsoft.com/azure-sdk/enabling-distributed-tracing-with-the-azure-sdk-for-python/)
- [Paramiko SFTP docs](https://docs.paramiko.org/en/stable/api/sftp.html)
- [fsspec features — callbacks](https://filesystem-spec.readthedocs.io/en/latest/features.html)
- [httpx event hooks](https://www.python-httpx.org/advanced/event-hooks/)

### Metrics patterns
- [Prometheus — Writing Client Libraries](https://prometheus.io/docs/instrumenting/writing_clientlibs/)
- [Understanding Metrics and Monitoring with Python](https://opensource.com/article/18/4/metrics-monitoring-and-python)

### remote-store internal
- Backlog: `sdd/BACKLOG.md` (ID-004, ID-024, ID-006, ID-013)
- Extension architecture: `sdd/adrs/0008-extension-architecture.md`
- Existing logging: `backends/_sftp.py:42`, `backends/_azure.py:38`, `ext/arrow.py:43`
