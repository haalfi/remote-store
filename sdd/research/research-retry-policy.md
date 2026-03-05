# Research: Retry Policy Configuration (ID-010)

**Date:** 2026-03-05
**Backlog items:** ID-010 (Retry policy configuration)
**Status:** Research complete — ready for design decisions

---

## 1. Problem Statement

The SFTP backend has hardcoded retry logic (3 attempts, 2–10 s exponential
backoff via `tenacity`). S3 and Azure rely on their SDK's built-in retry.
There is no unified retry surface — each backend does (or doesn't do) its own
thing, and users have zero knobs to tune retry behavior through `remote-store`.

The backlog item states:

> SFTP has hardcoded retry logic (3 attempts, 2–10 s backoff via `tenacity`).
> Expose a `RetryPolicy` dataclass in `BackendConfig.options` so users can tune
> attempts, backoff, and jitter per-backend.

### Why this matters

1. **Production workloads need tunable retries.** Batch jobs want aggressive
   retry (10 attempts, long backoff). Request-serving code wants fast failure
   (2 attempts, short backoff). One-size-fits-all is wrong for both.
2. **Flaky networks are common.** SFTP over WAN, S3 behind a VPN, Azure in
   cross-region setups — transient failures are routine, not exceptional.
3. **Rate limiting.** Cloud backends throttle (S3 503 SlowDown, Azure 429).
   Users need backoff tuning to avoid hammering a throttled endpoint.
4. **Observability.** Users want to know *that* retries happened and *why*,
   not discover them via unexplained latency spikes.

### Design constraints

- Core package has **zero runtime dependencies** (`dependencies = []`).
- `tenacity>=4.0` is an optional dependency (part of the `sftp` extra).
- `BackendConfig.options` is a `dict[str, object]` — the natural injection
  point for retry configuration.
- S3 and Azure SDKs have their own built-in retry mechanisms — a naive
  tenacity wrapper on top creates "retry multiplication."

---

## 2. Current State: How Each Backend Handles Retry

### 2.1 SFTP — Explicit tenacity on connect only

**File:** `src/remote_store/backends/_sftp.py` (lines 519–566)

```python
@retry(
    retry=retry_if_exception_type((paramiko.SSHException, OSError, EOFError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
def _do_connect() -> None:
    ssh.connect(...)
```

- **Scope:** Connection establishment only. Individual file operations
  (read, write, delete, list) are NOT retried.
- **Hardcoded:** 3 attempts, 2–10 s exponential backoff, no jitter.
- **Spec:** SFTP-009 (Tenacity Retry on Connect).
- **Audit note:** M-17 flags that this retry logic is untested.
- **Liveness check:** The `_sftp` property also calls `stat('.')` to detect
  stale connections and auto-reconnects. This is recovery, not retry.

### 2.2 S3 — Relies on botocore built-in retry

**File:** `src/remote_store/backends/_s3.py`

s3fs delegates to botocore, which has its own retry layer:

- **Default mode:** `legacy` (5 attempts, exponential backoff).
- **Standard mode:** Configurable via `botocore.config.Config(retries={"max_attempts": N, "mode": "standard"})`.
- **Adaptive mode:** Dynamic token-bucket rate limiting.
- **Retried errors:** Throttling (503 SlowDown, 429), transient errors (500,
  502, 503, 504), connection errors, timeout errors.

Users can *already* pass retry config through `client_options`:

```python
S3Backend(
    bucket="b",
    client_options={
        "client_kwargs": {
            "config": botocore.config.Config(retries={"max_attempts": 10, "mode": "adaptive"})
        }
    },
)
```

But this is undiscoverable, botocore-specific, and doesn't help with
non-botocore errors (e.g., s3fs's own network handling).

Additionally, s3fs has a module-level `retries` parameter (default 5) and
functions `s3fs.add_retryable_error()` / `s3fs.set_custom_error_handler()`
for registering retryable exception types. These are global — not per-instance.

### 2.3 Azure — Relies on Azure SDK built-in retry

**File:** `src/remote_store/backends/_azure.py`

Azure Storage SDK uses HTTP pipeline policies for retry:

- **Default:** `ExponentialRetry(initial_backoff=15, increment_base=3, retry_total=3, random_jitter_range=3)`.
- **Alternative:** `LinearRetry(backoff=15, retry_total=3, random_jitter_range=3)`.
- **Retried errors:** HTTP 408, 429, 500, 502, 503, 504, connection errors.

Users can pass retry config through `client_options`:

```python
from azure.storage.blob import ExponentialRetry
AzureBackend(
    container="c",
    account_name="a",
    client_options={"retry_policy": ExponentialRetry(retry_total=10)},
)
```

Again, undiscoverable and SDK-specific.

### 2.4 S3-PyArrow — Hybrid, partially configurable

**File:** `src/remote_store/backends/_s3_pyarrow.py`

- **Data path (PyArrow C++ S3):** PyArrow exposes `retry_strategy` on
  `S3FileSystem` with two strategy classes:
  - `AwsStandardS3RetryStrategy(max_attempts=3)` — default, exponential
    backoff, broad error coverage (recommended).
  - `AwsDefaultS3RetryStrategy(max_attempts=N)` — legacy, narrower coverage.
  The **only configurable knob** is `max_attempts`. Backoff timing, jitter,
  and error classification are not configurable through PyArrow's API.
  Related timeout parameters: `request_timeout`, `connect_timeout`.
- **Control path (s3fs):** Same as S3 backend above.

### 2.5 Local / Memory — No retry (correct)

Local filesystem and in-memory operations don't have transient failures
worth retrying. No retry needed.

### Summary

| Backend | Retry mechanism | Scope | User-configurable? |
|---------|----------------|-------|--------------------|
| **SFTP** | tenacity (hardcoded) | Connect only | No |
| **S3** | botocore built-in | All SDK calls | Yes, but buried in `client_options` |
| **Azure** | Azure SDK policies | All SDK calls | Yes, but buried in `client_options` |
| **S3-PyArrow** | C++ internal + botocore | Partial | Minimal |
| **Local** | None | N/A | N/A |
| **Memory** | None | N/A | N/A |

---

## 3. Survey: How the Python Ecosystem Handles Retry

### 3.1 google-api-core `Retry` (gold standard)

```python
Retry(
    predicate=if_transient_error,  # Callable[[Exception], bool]
    initial=1.0,                   # initial delay (seconds)
    maximum=60.0,                  # max delay cap (seconds)
    multiplier=2.0,                # exponential multiplier
    timeout=120.0,                 # total retry window (seconds)
    on_error=None,                 # callback on each error
)
```

Key decisions:
- Uses **timeout** (total wall-clock window) rather than max_attempts.
- **Predicate-based** retryability — `if_exception_type(Exc1, Exc2)` builds
  predicates.
- **Immutable with `with_XXX` builders:** `retry.with_timeout(500)` returns
  a new instance.
- `ConditionalRetryPolicy` activates retry only for idempotent operations.

**Strengths:** Most thoughtful design. Predicate composability is powerful.
**Weaknesses:** Timeout-only (no attempt count) is confusing for some users.

### 3.2 urllib3 `Retry` (most widely used)

```python
Retry(
    total=10,              # total retries
    backoff_factor=0.5,    # exponential backoff multiplier
    backoff_max=120,       # backoff ceiling (seconds)
    backoff_jitter=0.0,    # random jitter
    status_forcelist=None, # HTTP status codes to retry
)
```

Backoff formula: `backoff_factor * (2 ** num_previous_retries) + uniform(0, backoff_jitter)`

**Strengths:** Battle-tested, explicit jitter, attempt-based.
**Weaknesses:** HTTP-specific knobs (status codes, methods) don't map to
storage operations.

### 3.3 obstore `RetryConfig` (closest analog)

```python
RetryConfig(
    max_retries=10,
    retry_timeout="60s",          # total wall-clock cap
    backoff={"init_backoff": "1s", "max_backoff": "30s", "base": 2.0},
)
```

The only multi-backend storage library with a unified retry config object.
Backed by the Rust `object_store` crate.

**Strengths:** Simple, storage-specific, proven in production.
**Weaknesses:** No predicate customization, no jitter knob.

### 3.4 tenacity (our existing dependency)

```python
retry(
    retry=retry_if_exception_type(OSError),
    stop=stop_after_attempt(3) | stop_after_delay(60),
    wait=wait_exponential(multiplier=1, min=2, max=10) + wait_random(0, 2),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
```

**Strengths:** Maximum composability — combinable stop/wait/retry conditions.
**Weaknesses:** Not a config object — it's a decorator. Hard to
serialize/deserialize for config files.

### 3.5 fsspec ecosystem (fragmented)

- **s3fs:** Module-level `retries` parameter (default 5),
  `add_retryable_error()` for exception types. No per-instance config.
- **adlfs:** Delegates to Azure SDK.
- **sshfs:** No retry.
- **No shared retry abstraction across fsspec.**

### Summary table

| Library | Type | Limit style | Backoff params | Jitter |
|---------|------|-------------|----------------|--------|
| **google-api-core** | Class | timeout (seconds) | initial, maximum, multiplier | Internal |
| **urllib3** | Class | total (count) | backoff_factor, backoff_max | Explicit |
| **obstore** | Dict | max_retries + retry_timeout | init_backoff, max_backoff, base | Internal |
| **tenacity** | Decorator | stop_after_attempt / stop_after_delay | wait_exponential(multiplier, min, max) | Additive |
| **s3fs** | Module-level | retries (count) | Fixed | None |

---

## 4. Design Space: Where Should Retry Live?

The central tension: **S3 and Azure already retry internally.** Adding a
retry layer on top creates multiplication. There are three viable approaches.

### 4.1 Option A: Unified tenacity layer at Store level

Wrap every `Store` method call with a configurable tenacity retry decorator.
The Store becomes the retry boundary.

```python
store = Store(backend, root_path="data")
store.retry_policy = RetryPolicy(max_attempts=5, backoff_base=2.0, backoff_max=30.0)
# Every store.read(), store.write(), etc. is retried on transient errors
```

**Pros:**
- Single retry config for all backends.
- Users don't need to think about per-backend differences.
- Works with any backend, including future ones.

**Cons:**
- **Retry multiplication:** S3 has 5 botocore retries × 5 Store retries = 25
  actual attempts. Azure has 3 SDK retries × 5 Store retries = 15 attempts.
  This is wasteful and can cause extremely long waits.
- **Wrong error types:** Store methods raise `remote-store` errors (`NotFound`,
  `BackendUnavailable`, etc.), not SDK exceptions. Retrying on `NotFound`
  makes no sense. The retryable-error predicate must be carefully curated.
- **Conflates levels:** Connection retry (SFTP) vs operation retry (S3 503)
  vs application retry (idempotency) are different concerns.
- Adds tenacity as a **core** dependency (currently it's SFTP-only optional).

### 4.2 Option B: Per-backend native retry configuration

Expose each SDK's native retry configuration through a unified
`RetryPolicy` dataclass that maps to backend-specific settings.

```python
policy = RetryPolicy(max_attempts=5, backoff_base=2.0, backoff_max=30.0, jitter=1.0)

# S3: maps to botocore Config(retries={"max_attempts": 5, "mode": "standard"})
S3Backend(bucket="b", retry=policy)

# Azure: maps to ExponentialRetry(retry_total=5, initial_backoff=2, increment_base=2)
AzureBackend(container="c", retry=policy)

# SFTP: maps to tenacity @retry(stop=stop_after_attempt(5), wait=wait_exponential(...))
SFTPBackend(host="h", retry=policy)
```

**Pros:**
- No retry multiplication — replaces SDK defaults, doesn't stack on top.
- Each backend interprets the policy in the most efficient way for its SDK.
- Clean separation — retry stays at the transport level where it belongs.

**Cons:**
- Lossy mapping: a `RetryPolicy` can't express everything botocore or Azure
  SDK supports (status code lists, conditional retry, adaptive mode).
- PyArrow C++ S3 retry is barely configurable — mapping is very limited.
- Users who need full SDK control still use `client_options` (which already
  works today).
- Different backends may interpret the same policy slightly differently.

### 4.3 Option C: Retry-aware Store middleware (ext layer)

Instead of building retry into backends, offer it as an observable middleware
in `ext/`, similar to how `ext.observe` wraps Store with hooks.

```python
from remote_store.ext.retry import RetryPolicy, retry_store

policy = RetryPolicy(max_attempts=3, backoff_base=1.0, backoff_max=30.0)
store = retry_store(base_store, policy=policy)
# store.write() now retries on BackendUnavailable
```

Under the hood, `retry_store()` returns a `RetryStore(Store)` proxy that
wraps each method with tenacity retry, filtering on retryable error types
(`BackendUnavailable`, `PermissionDenied` on rate-limit, etc.).

**Pros:**
- Zero change to backends or Store — purely additive.
- Composable with `ext.observe` — `observe(retry_store(base))`.
- Explicit opt-in — users who want retry get it; others don't pay for it.
- Can be combined with SDK-level retry (intentionally — the ext layer
  catches errors that escape the SDK retry).
- tenacity stays optional (part of an ext extra, not core).

**Cons:**
- Two retry layers (SDK + middleware) are harder to reason about.
- Retry at the Store level means the full method re-executes, including
  path validation, logging, etc. (minor overhead).
- `read()` returns `BinaryIO` — retrying a streaming read is tricky
  (must discard the partial stream and re-open).

### 4.4 Option D: Hybrid — Backend-native defaults + Store-level override

Combine B and C: backends configure their SDK's native retry from the policy
(eliminating SDK defaults), and the Store middleware handles cross-cutting
retry (e.g., reconnect-and-retry for SFTP connection drops mid-operation).

**Pros:** Theoretically cleanest — each layer does what it's best at.
**Cons:** Most complex. Two places to configure retry. Hard to explain.

---

## 5. Recommendation

### Primary: Option B (per-backend native retry configuration)

This is the most natural fit for the library's architecture:

1. **Backends own their transport** — retry is a transport concern.
2. **No retry multiplication** — the policy replaces SDK defaults.
3. **Minimal API surface** — one dataclass, one constructor parameter.
4. **No new core dependencies** — tenacity stays in the SFTP extra.

### Secondary consideration: Option C as a future extension

A Store-level retry middleware in `ext/` could handle higher-level retry
(e.g., "reconnect SFTP and retry the operation" or "retry a write that
failed mid-stream"). This is orthogonal to backend-level retry and can be
added later without changing the backend-level design.

### Not recommended: Option A

Store-level retry as the primary mechanism causes retry multiplication and
is at the wrong abstraction level. Rejected.

---

## 6. Proposed `RetryPolicy` Dataclass

```python
@dataclasses.dataclass(frozen=True)
class RetryPolicy:
    """Retry configuration for transient backend errors.

    Backends map these parameters to their native retry mechanisms.
    Backends that don't support a parameter silently ignore it.
    """

    max_attempts: int = 3
    """Maximum number of attempts (including the initial attempt).
    Set to 1 to disable retry."""

    backoff_base: float = 1.0
    """Base delay in seconds for exponential backoff.
    Delay = backoff_base * (2 ** attempt) capped at backoff_max."""

    backoff_max: float = 60.0
    """Maximum delay between retries in seconds."""

    jitter: float = 1.0
    """Maximum random jitter added to each delay in seconds.
    Set to 0.0 to disable jitter."""

    timeout: float | None = None
    """Total wall-clock timeout in seconds for all attempts combined.
    None means no total timeout (only max_attempts limits retries)."""
```

### Mapping to each backend

| Parameter | SFTP (tenacity) | S3 (botocore) | Azure SDK | S3-PyArrow |
|-----------|----------------|---------------|-----------|------------|
| `max_attempts` | `stop_after_attempt(N)` | `Config(retries={"max_attempts": N})` | `retry_total=N-1` | `AwsStandardS3RetryStrategy(max_attempts=N)` + s3fs side |
| `backoff_base` | `wait_exponential(min=N)` | Not directly mapped¹ | `initial_backoff=N` | Not configurable (C++ internal) |
| `backoff_max` | `wait_exponential(max=N)` | Not directly mapped¹ | Implicit via increment | Not configurable (C++ internal) |
| `jitter` | `wait_random(0, N)` | Built-in (not configurable) | `random_jitter_range=N` | Not configurable (C++ internal) |
| `timeout` | `stop_after_delay(N)` | Not supported | Not supported | Not supported |

¹ botocore uses fixed backoff: `min(base * 2^attempt, 20)` where base is
`random() * 2^attempt`. The `backoff_base` and `backoff_max` cannot be
directly set. For S3, the mapping is best-effort.

### Where it lives

- **Type definition:** `src/remote_store/_config.py` (alongside `BackendConfig`)
- **No new dependencies** for the dataclass itself.
- SFTP uses tenacity (already an optional dep) to implement the policy.
- S3/Azure map to their SDK's native config objects.

### How users configure it

```python
from remote_store import RetryPolicy, BackendConfig, RegistryConfig

# Direct backend construction
from remote_store.backends import SFTPBackend
backend = SFTPBackend(host="sftp.example.com", retry=RetryPolicy(max_attempts=5))

# Via BackendConfig
config = BackendConfig(
    type="sftp",
    options={"host": "sftp.example.com"},
    retry=RetryPolicy(max_attempts=5),
)

# Via dict config (from_dict / YAML / TOML)
config = RegistryConfig.from_dict({
    "stores": {
        "remote": {
            "backend": {
                "type": "sftp",
                "options": {"host": "sftp.example.com"},
                "retry": {"max_attempts": 5, "backoff_base": 2.0},
            }
        }
    }
})

# Disable retry entirely
backend = SFTPBackend(host="h", retry=RetryPolicy(max_attempts=1))
```

---

## 7. Scope Question: Connect Retry vs Operation Retry

SFTP currently retries *connection* only. Should `RetryPolicy` also cover
individual *operations* (read, write, delete)?

### Arguments for operation retry (SFTP)

- SSH connections drop mid-session (network blip, server restart).
- A `write()` that fails with `OSError` or `SSHException` mid-transfer is
  retryable if the backend reconnects first.
- The liveness check (`stat('.')`) already detects stale connections — retry
  could trigger reconnect + re-attempt.

### Arguments against operation retry (SFTP)

- Non-idempotent operations (`write` with `overwrite=False`, `move`) are
  unsafe to retry blindly.
- Partial writes may leave orphaned data — retry without cleanup causes
  corruption.
- The current SFTP-009 spec explicitly limits retry to connection.

### Arguments for operation retry (S3/Azure)

- S3 and Azure SDKs already retry individual operations at the HTTP level.
- `RetryPolicy` naturally configures this existing behavior.
- No additional code needed — just pass config to the SDK.

### Recommendation

- **S3/Azure:** `RetryPolicy` configures the SDK's existing operation-level
  retry. This is safe because the SDKs already handle idempotency.
- **SFTP:** `RetryPolicy` configures *connection* retry (replacing the
  hardcoded values). Operation retry is a separate, more complex feature
  that requires idempotency analysis and should be a follow-up if needed.
  The liveness check + auto-reconnect already handles the most common case
  (stale connection on next operation).

---

## 8. Open Questions for Spec/ADR

1. **Should `RetryPolicy` be a field on `BackendConfig` or nested in `options`?**
   The backlog item says `BackendConfig.options`. A dedicated field
   (`BackendConfig.retry: RetryPolicy | None`) is cleaner and type-safe,
   but changes the `BackendConfig` schema. Recommendation: dedicated field.

2. **Should `RetryPolicy` be a core type or live in an optional module?**
   As a frozen dataclass with no imports, it has zero dependency cost.
   Recommendation: core type in `_config.py`.

3. **What about `RetryPolicy.disabled()` class method?**
   `RetryPolicy(max_attempts=1)` works but reads poorly. A
   `RetryPolicy.disabled()` factory (returns `RetryPolicy(max_attempts=1)`)
   is more expressive. Nice-to-have, not critical.

4. **Should backends accept `retry` as a constructor parameter?**
   Currently backends take individual kwargs (`host`, `port`, etc.) not
   config objects. Adding `retry: RetryPolicy | None = None` to each
   backend constructor is the cleanest API. Backends that ignore retry
   (Local, Memory) simply don't accept the parameter.

5. **Should the default `RetryPolicy()` match current SFTP behavior?**
   Current SFTP: 3 attempts, 2–10 s exponential. Proposed default:
   3 attempts, 1–60 s exponential, 1 s jitter. The defaults should be
   reasonable for all backends, not SFTP-specific. SFTP's current behavior
   can be preserved with `RetryPolicy(max_attempts=3, backoff_base=2.0, backoff_max=10.0)`.

6. **How does this interact with `ext.observe`?**
   Retry happens inside the backend, below the observe middleware.
   `ext.observe` sees the final result (success after N retries, or failure
   after exhausting retries). If users want retry-level observability,
   they need backend-level logging (which SFTP's `before_sleep_log` already
   provides). The `RetryPolicy` could optionally accept an `on_retry`
   callback, but this adds complexity — defer unless there's demand.

7. **Should `from_dict()` auto-parse `retry` from nested dicts?**
   Yes — `{"retry": {"max_attempts": 5}}` should produce
   `BackendConfig(retry=RetryPolicy(max_attempts=5))`. This keeps YAML/TOML
   config ergonomic.

---

## 9. Implementation Estimate

| Work item | Effort | Dependencies |
|-----------|--------|-------------|
| `RetryPolicy` dataclass in `_config.py` | Small | None |
| `BackendConfig.retry` field + `from_dict()` parsing | Small | RetryPolicy |
| SFTP: read policy from constructor, replace hardcoded values | Medium | RetryPolicy |
| S3: map policy to botocore `Config(retries=...)` | Small | RetryPolicy |
| Azure: map policy to `ExponentialRetry(...)` | Small | RetryPolicy |
| S3-PyArrow: map policy to s3fs side | Small | RetryPolicy |
| Tests: unit tests for RetryPolicy, integration tests per backend | Medium | All above |
| Spec: `sdd/specs/0XX-retry-policy.md` | Medium | Design decisions |
| Docs: user guide, config examples | Small | Spec |
| CHANGELOG, BACKLOG update | Small | All above |

Total: Medium-sized feature. Comparable to ID-039 (Secret/credential hygiene).

---

## 10. References

### Python ecosystem
- [google-api-core Retry](https://googleapis.dev/python/google-api-core/latest/retry.html)
- [urllib3 Retry](https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html)
- [obstore RetryConfig](https://docs.rs/object_store/latest/object_store/struct.RetryConfig.html)
- [tenacity docs](https://tenacity.readthedocs.io/)
- [botocore retry configuration](https://botocore.amazonaws.com/v1/documentation/api/latest/reference/config.html)
- [Azure Storage retry policies](https://learn.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.exponentialretry)

### Internal
- SFTP spec: `sdd/specs/009-sftp-backend.md` (SFTP-009)
- Audit: M-17 (SFTP retry untested)
- BackendConfig: `src/remote_store/_config.py`
- SFTP retry code: `src/remote_store/backends/_sftp.py` (lines 519–566)
