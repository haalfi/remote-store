# Research: Logging, Monitoring & Tracing for remote-store

**Date:** 2026-03-02
**Backlog items:** ID-004 (Structured logging & metrics hooks), ID-024 (`ext.notify`)
**Status:** Research complete — ready to inform RFC/spec work

---

## 1. Executive Summary

This document researches how `remote-store` should approach the three pillars
of observability — **logging**, **monitoring (metrics)**, and **tracing** — as
a Python *library* (not an application). The key distinction matters: libraries
emit signals, applications decide what to do with them.

Our dependencies (boto3/botocore, paramiko, azure-storage-blob, s3fs, fsspec)
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
| `ext/arrow.py` | `remote_store.ext.arrow` | Large file materialization | WARNING |

**What's missing:** No logging for read/write/delete/copy/move operations,
no logging in the Store layer, no logging in S3/S3-PyArrow/Local/Memory
backends, no structured context (operation, path, backend, duration).

### 2.2 No NullHandler registered

The library does **not** add a `NullHandler` to the `"remote_store"` top-level
logger. This means applications that don't configure logging see Python's
`lastResort` handler (stderr, WARNING+). This is the correct accidental
behavior for WARNING-only messages, but violates the explicit best practice
and will cause `"No handlers could be found"` warnings in older Python if
we add DEBUG/INFO logging.

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

### 3.3 azure-storage-blob / azure-core (Azure SDK for Python)

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
terser but loses type safety. **Recommend A.**

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
| **azure-storage-blob** | stdlib + pipeline | Azure Monitor | Built-in OTel plugin (`azure-core-tracing-opentelemetry`) | None |
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

## 9. Open Questions for RFC

These should be resolved during RFC/spec work:

1. **Should `ext.notify` be a single `instrument()` function or a class
   (`InstrumentedStore`)?** Function is simpler; class allows
   `isinstance()` checks and `.unwrap()`.

2. **Should hooks be synchronous-only or support async?** For now sync
   is sufficient (no async Store yet — see ID-013). But the event model
   should not preclude async hooks in the future.

3. **Should events be emitted before + after, or only after?** Before
   enables circuit-breaking / rate-limiting (but adds complexity). After
   is simpler and sufficient for logging/metrics/tracing.
   Tracing needs "before" (to start the span) and "after" (to end it) —
   so a context-manager style hook may be needed for tracing.

4. **Should `ext.notify` handle `ext.transfer` operations?** Transfer
   uses Store.read() + Store.write() internally, so those would already
   be captured. But the "transfer as a whole" event (src→dst) is a
   higher-level concern.

5. **Should we adopt fsspec's `Callback` pattern for transfer progress
   alongside `ext.notify`?** The existing `on_progress` in `ext.transfer`
   is simpler. But fsspec's `branch()` pattern is more powerful for
   multi-file operations (future: `batch_copy` with `concurrent=True`).

6. **Should `opentelemetry-api` be a core dependency or optional extra?**
   Research strongly suggests optional extra. Core stays zero-dep.

7. **Naming: `ext.notify` vs `ext.observe` vs `ext.instrument`?**
   The backlog says `ext.notify`. Consider whether this name adequately
   conveys the purpose.

---

## 10. Additional Design Precedents (from extended research)

The following patterns from our dependencies and the broader ecosystem
are especially relevant to `ext.notify` design.

### 10.1 Azure SDK's `@distributed_trace` decorator

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

### 10.2 Botocore event system

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

### 10.3 httpx event hooks

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

### 10.4 Context propagation via `contextvars`

Python's `contextvars` module (stdlib, 3.7+) is the standard for
propagating context (request IDs, correlation IDs) across async boundaries.
structlog integrates with it for bound-logger context.

**Relevance:** `ext.notify` events should carry the current `contextvars`
context so that tracing bridges can attach spans to the correct parent.
The OpenTelemetry API handles this automatically via `Context`, but
callback-only users may want access to a correlation ID. Consider adding
an optional `context` field to `StoreEvent` (§5, Layer 2).

### 10.5 Using `extra={}` for structured log context

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

## 11. References

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
- Backlog: `sdd/BACKLOG.md` (ID-004, ID-024, ID-025)
- Extension architecture: `sdd/adrs/0008-extension-architecture.md`
- Existing logging: `backends/_sftp.py:42`, `backends/_azure.py:38`, `ext/arrow.py`
