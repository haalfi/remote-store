# ADR-0025: Async-to-Sync Backend Adapter (`AsyncBackendSyncAdapter`)

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

ADR-0012 set up the hybrid async/sync model: `AsyncBackend` is the async
ABC, `Backend` is the sync ABC, and `SyncBackendAdapter` bridges a sync
`Backend` into the async world via `asyncio.to_thread`. Only one
direction was specified.

ID-127 introduces the Graph backend, the project's first async-native
backend. Sync callers of `Store` must still be able to use it, which
requires the inverse bridge: run an async backend from sync code.
RFC-0010 § Async posture defers the design of that bridge to this ADR
and makes ID-141 a prerequisite of the Graph implementation PR.
(ID-141 was renumbered from ID-128, which collided with the completed
`Capability.ATOMIC_MOVE` item in `BACKLOG-DONE.md`.)

The async→sync direction is non-trivial because:

- Python's `asyncio` does not allow re-entering a running event loop.
  `loop.run_until_complete()` from inside a running loop raises
  `RuntimeError`.
- `asyncio.run()` creates and tears down a new loop on every call,
  which defeats connection pooling and client reuse inside async SDKs
  (`httpx.AsyncClient`, `aiohttp`, MSAL cache handles).
- Sync callers may arrive from arbitrary threads, including threads
  with no current event loop and threads that happen to be hosting
  one (notebooks, GUI toolkits, pytest-asyncio).
- Cancellation, error propagation, and resource cleanup must survive
  the boundary crossing in both directions.

Four candidate mechanisms were considered:

**Option A — `asyncio.run()` per call.** Simple; creates a fresh loop
for each sync method, submits the coroutine, tears down. Rejected:
prevents the backend's async client from being reused across calls,
forfeits connection pools, multiplies auth-token refreshes, and still
fails if the caller is already inside a running loop.

**Option B — Reuse the caller's running loop.** Not possible without
patching; `run_until_complete()` on a running loop raises, and
scheduling a coroutine plus blocking on the same loop deadlocks.

**Option C — `nest_asyncio`.** A third-party monkey-patch that allows
nested `run_until_complete`. Rejected as the default: patches the
global `asyncio` module (process-wide side effect), is an optional
dependency, and is a known source of hard-to-reason-about behaviour in
libraries that share the runtime with other async frameworks.

**Option D — Private event loop in a background thread.** Adapter owns
one asyncio loop running in a dedicated daemon thread for its
lifetime. Sync methods submit coroutines via
`asyncio.run_coroutine_threadsafe()` and block on the returned
`concurrent.futures.Future`. This is the standard "run async from
sync" pattern documented in the `asyncio` stdlib and battle-tested in
multiple bridge libraries.

## Decision

Introduce `AsyncBackendSyncAdapter`, a class implementing the sync `Backend` ABC
by delegating to a wrapped `AsyncBackend` that runs on a private event loop in a
dedicated daemon thread (**Option D** of the four weighed in Context). It mirrors
`SyncBackendAdapter` (ADR-0012); together they form the full bidirectional bridge
the hybrid model needs.

**Private loop on a dedicated daemon thread, not `asyncio.run()` per call and not
`nest_asyncio`.** `asyncio` forbids re-entering a running loop, and a fresh loop
per call forfeits the async SDK's connection pools and auth-token cache; a
per-adapter private loop keeps the client alive while sync callers submit
coroutines via `run_coroutine_threadsafe` and block on the returned `Future`.
*Reverse if* the stdlib gains safe nested-loop execution, or the wrapped backends
stop needing cross-call client reuse.

**Two distinct adapters, not one parameterised bridge.** The two boundary
directions differ enough that two named classes read clearer than one flag-driven
bridge. *Reverse if* a single parameterised bridge proves clearer in practice.

**The module lives in the sync core (`src/remote_store/_async_to_sync_adapter.py`),
not under `aio/`.** It implements the sync `Backend`, so it belongs with sync
code; placing it under `aio/` would force every sync `Store` user wrapping an
async backend to import the `aio/` runtime at construction, inverting the
invariant that sync code stays independent of `aio/`. `AsyncBackend` is imported
lazily in `__init__` to keep that core-to-`aio` edge off the top level. *Reverse
if* the sync-independent-of-`aio/` layering invariant is abandoned.

### Ownership model

One private loop and one daemon thread per adapter instance, never shared or
reused; the adapter is a **one-shot resource**, so a closed adapter raises rather
than restarting the loop. Concurrent sync callers are serialised onto the single
loop, which *manufactures* thread-safety for a loop-safe async backend;
**ordering between concurrent callers is not guaranteed**, so callers needing
order coordinate externally. *Reverse if* a backend needs multi-loop parallelism
one serialising loop cannot give. Exact concurrency bounds and no-crossover
guarantee: spec 029 § ASYNC-089.

### Streaming iterators and open streams

`read()` and the listing iterators **pump chunks lazily across the boundary and
never materialise** the full stream or listing, since native-async backends exist
to stream and the sync wrapper preserves that. The rule is **at most one
outstanding `__anext__` per stream/iterator** (no read-ahead), the only
per-stream buffer being the unread tail of the last chunk. *Reverse if* a wrapped
backend cannot stream, making materialisation unavoidable. Exact
`BinaryIO`/short-read surface and buffer mechanics: spec 029 § ASYNC-080,
ASYNC-081.

### Write-side content

The bridge runs **sync `BinaryIO` to `AsyncIterator[bytes]`** (the sync side has
no iterator-of-bytes input), pulling the `BinaryIO` via `asyncio.to_thread` so
the loop never blocks on the caller's file object. **`open_atomic` is synthesised
over the backend's `write_atomic`** (spool, flush on clean exit, drop on error)
rather than adding an `open_atomic`-shaped op to `AsyncBackend`, keeping the async
ABC unchanged and leaving Graph (ID-127) nothing new to implement. The
`ATOMIC_WRITE` gate is enforced by the wrapped backend. *Reverse if* a backend
needs a native incremental async atomic write. Exact spool/flush and
mid-write-failure semantics: spec 029 § ASYNC-085, ASYNC-091.

### Behaviour when the caller is in a running loop

**Fail fast:** invoked from a thread with a running loop, a blocking method
raises `RuntimeError` pointing the caller to `AsyncStore`, keeping the sync
contract genuinely sync and preventing deadlock (per ADR-0012, sync `Store` is
not coroutine-safe by design). **No `nest_asyncio` in v1**, which would
monkey-patch global `asyncio`; the adapter neither imports nor depends on it.
*Reverse if* notebook/GUI demand justifies an explicit opt-in mode, which ships
behind its own flag and its own ADR. Exact detection point and message stem:
spec 029 § ASYNC-082.

### Capability translation

The adapter **translates** the wrapped `CapabilitySet` rather than
blind-forwarding it: **`SEEKABLE_READ` is masked off** because the chunk-pull
stream is forward-only (random-access callers fall through to `read_seekable`'s
spool, as every non-seekable sync backend already does); `LAZY_READ` and the rest
pass through unchanged. **`unwrap()` raises `CapabilityNotSupported`** by default
because an async handle bound to the private loop is unsafe from the caller's
thread, unless the backend exposes a sync-safe handle. *Reverse if* a native
async seekable-read op is added, letting `SEEKABLE_READ` pass through. Exact
translation/gating table and unwrap exemption: spec 029 § ASYNC-084, ASYNC-086.

### Lifecycle

`close(timeout=30.0)` drains in-flight tasks, stops the loop, and joins the
thread within a bounded timeout (default matches the per-backend network
ceilings; `None` waits forever; on expiry it logs a `WARNING` and lets the daemon
thread be reaped at process exit); `__enter__`/`__exit__` delegate to it.
**Errors cross verbatim:** no wrapping or translation, so error types and the
ERR-001 `path`/`backend` attributes (spec 005) reach the sync caller unchanged;
`check_health()` is likewise not a no-op and does not swallow the backend's probe
errors. **Cancellation is best-effort:** `Future.cancel()` only requests
`Task.cancel()`, observed at the next `await`, so `close()` drains before
stopping; `KeyboardInterrupt` is not special-cased, because KI-to-cancel would
give this one backend behaviour no other sync backend has. **No per-call
timeout:** per-operation timeouts are the wrapped backend's responsibility;
`close()` is the only global bound. *Reverse if* per-operation cancellation or
timeout becomes a cross-backend contract. Exact drain order, message stems, and
failure-mode semantics: spec 029 § ASYNC-083, ASYNC-087, ASYNC-088, ASYNC-090,
ASYNC-092, ASYNC-093.

### Store-level wiring

The sync `Store` gains a construction path that auto-wraps a supplied
`AsyncBackend` in this adapter, mirroring `AsyncStore`'s auto-wrap of a sync
`Backend`. The adapter is backend-agnostic; Graph registry integration lives in
spec 044. *Reverse if* the auto-wrap convenience is removed from the `Store`
constructor.

## Consequences

- **Graph backend unblocked.** ID-127 can ship a single
  async-native backend that serves both `AsyncStore` directly and
  sync `Store` via this adapter. No duplicate sync implementation.
- **Predictable control flow.** Sync callers see ordinary blocking
  calls; async backend sees ordinary coroutines. The boundary is
  narrow and explicit.
- **Event-loop and thread overhead per adapter instance.** One
  daemon thread and one loop live for the adapter's lifetime.
  Acceptable: `Store` instances are long-lived, and the cost is
  paid once per backend instance, not per call.
- **No process-wide patching.** `asyncio` global state is not
  modified. Coexists cleanly with callers that run their own
  event loop in other threads.
- **Running-loop callers must use `AsyncStore`.** The sync Store
  API is not safe to call from inside an async handler. The
  fail-fast error makes the misuse obvious. Notebook / GUI
  compatibility is deferred to a future opt-in.
- **Cancellation is best-effort from sync.** Between
  `Future.cancel()` returning and the task actually unwinding,
  short windows of "cancel requested, task still running" exist.
  Documented; sufficient for the operations on the Backend ABC.
- **Streaming preserved.** Iterators and `read()` streams do not
  materialise into memory; the adapter pumps chunks across the
  boundary. Large listings and large reads cross the bridge
  without balloon allocations.
- **Error model unchanged.** Exception types survive the bridge
  verbatim. Spec 005 needs no amendment.
- **No new capability flag.** `CapabilitySet` itself is unchanged.
  The adapter performs translation, not enumeration: it masks
  `SEEKABLE_READ` (chunk-pull stream is not natively seekable) and
  forwards the rest unchanged. See § Capability translation.
- **`open_atomic` synthesised over `write_atomic`.** The async ABC
  is not extended; the spool-and-flush pattern keeps the Graph
  implementation surface narrow.
- **No new runtime dependency.** Stdlib `asyncio` and `threading`
  only.
- **Prerequisite for ID-127.** The Graph implementation PR cannot
  land without this adapter; the dependency is recorded in
  `sdd/BACKLOG.md` (`ID-127 Depends on: ID-141, ID-142`).
- **Phase 3 (ID-013b) is orthogonal, not superseding.** Async
  extensions (`AsyncObservedStore`, `AsyncCachedStore`, …) solve
  the inverse problem: making extensions usable from async code.
  This adapter stays valuable indefinitely because sync `Store`
  callers always need a way to reach an async-native backend.
- **Async-first extension surface enabled.** A future extension
  authored async-native around `AsyncStore` (e.g. an async-only
  cloud-search wrapper) becomes reachable from sync `Store` users
  for free via this adapter — no second sync implementation
  required.

### Risks

- **Misuse from async contexts.** Sync `Store` calls from inside an
  async handler will raise rather than deadlock, but a caller that
  catches the `RuntimeError` and retries on a worker thread will
  still pay a thread hop per call. Documented as anti-pattern in
  the user-facing guide; not a correctness problem.
- **Per-call cancellation race.** A sync caller that interrupts a
  call may observe `CancelledError` while the async task is still
  unwinding; subsequent calls on the same adapter are unaffected,
  but external observers (logs, metrics) may see overlapping
  "cancelled" and "completed-cleanup" events.
- **Worker-thread starvation under high concurrency.** All sync
  callers share one event loop; backends that are CPU-bound (rare
  for I/O backends, but possible for `_graph_transfer`'s chunk
  hashing) can stall sibling calls. Mitigation deferred to backend
  authors via `asyncio.to_thread` for hot CPU paths.

  > Superseded by [ADR-0029](0029-graph-transfer-blocking-io-offload.md):
  > the Graph transfer path does no hashing; the real stall source is
  > blocking spool **I/O**, now offloaded in-backend via `asyncio.to_thread`.
- **Loop teardown timeout.** If a wrapped backend ignores
  cancellation, `close()`'s bounded join leaves the daemon thread
  to be reaped at process exit; the warning surfaces this but does
  not force progress.
- **Observability fidelity loss across read-streams.** Extensions
  that wrap `Store` via the proxy pattern (ADR-0010) — notably
  `ext.observe` — fire one event per *operation*, which for `read()`
  is one event at stream construction. Per-chunk pumping across the
  bridge is not visible; the duration metric reflects stream-open
  cost only. Acceptable for the Backend-ABC contract; users wanting
  per-chunk observability should consume `AsyncStore` directly.
- **`ext.cache` default-unbounded `read_bytes`.** `CachedStore` with
  unset `max_content_size` materialises whatever the wrapped backend
  yields. Over an async-native backend that exists precisely to
  *avoid* materialisation, this is more dangerous than over a sync
  REST backend. Users wrapping an async backend should set
  `max_content_size` explicitly; the cache extension should learn to
  warn when wrapped over a bridged backend (tracked as ID-218).
- **Bridged read streams are forward-only.** The `BinaryIO` returned
  by `read()` is not natively seekable: `seekable()` returns `False`
  and `seek()`, `tell()`, and `fileno()` are not provided.
  `readable()` returns `True`. `SEEKABLE_READ` is masked off so no
  extension that respects the capability gate will attempt random
  access. Random-access callers route through `read_seekable` and
  pay the spool fallback (above).

## Followups

- **Normative spec block (`ASYNC-NNN`) — landed.** ID-142 amended
  `sdd/specs/029-async-store-backend-api.md` § AsyncBackendSyncAdapter
  with the invariants this ADR records in prose, so the implementation
  test suite can trace each case via `@pytest.mark.spec("ASYNC-NNN")`
  per `sdd/000-process.md` Rule 2, mirroring `ASYNC-030 … ASYNC-048`
  for `SyncBackendAdapter`. The spec block is the authoritative home
  for exact message stems, drain order, capability translation, and
  concurrency bounds; this ADR describes the design intent. The spec
  is a prerequisite for the ID-127 implementation PR.
- **Test doubles — landed.** `_HangingAsyncBackend` and
  `_RaisingAsyncBackend` under `tests/aio/_doubles.py` make the
  failure paths above reachable without mocking third-party internals
  (`sdd/TESTING.md` Rule 6).
- **Mirror parity test pattern — deferred to ID-127 implementation.**
  Structural mirror of `tests/aio/test_sync_adapter.py` (one `Test…`
  class per domain), plus the additional classes unique to this
  direction: `…RunningLoopFailFast`, `…Cancellation`, `…Concurrency`,
  `…CloseSemantics`.

## References

- ADR-0012: Async Store / Backend API — Hybrid Model (§ Async
  posture, error-mapping rules)
- ADR-0023: Async Monitor-URL Polling
- ADR-0024: `ResourceLocked` Error Type
- RFC-0010: Microsoft Graph Backend (§ Async posture)
- `sdd/specs/003-backend-adapter-contract.md`
- `sdd/specs/005-error-model.md` (ERR-001 path/backend attributes)
- `sdd/specs/006-streaming-io.md` (SIO-008 `SEEKABLE_READ`,
  SIO-009 `LAZY_READ`)
- `src/remote_store/_backend.py` (sync `Backend` ABC — the contract
  the adapter implements; `open_atomic`, `read_seekable`,
  `WritableContent`)
- `src/remote_store/_types.py` (sync `WritableContent = BinaryIO | bytes`)
- `src/remote_store/aio/_async_backend.py` (`AsyncBackend` ABC —
  the wrapped contract; note no `open_atomic` / `read_seekable`)
- `src/remote_store/aio/_types.py` (`AsyncWritableContent`)
- `src/remote_store/aio/_sync_adapter.py` (mirror implementation)
- Python stdlib: `asyncio.run_coroutine_threadsafe`,
  `asyncio.Task.cancel`
- `concurrent.futures.Future.cancel` semantics
- CPython issues on cancel/threadsafe interaction:
  python/cpython#103819, python/cpython#105836
