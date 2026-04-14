# ADR-0025: Async-to-Sync Backend Adapter (`AsyncBackendSyncAdapter`)

## Status

Draft

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

Introduce a new class `AsyncBackendSyncAdapter` under
`remote_store.aio` that implements the sync `Backend` ABC by
delegating to an `AsyncBackend` running on a private event loop in a
dedicated background thread. Do **not** invert `SyncBackendAdapter`;
the execution direction is different enough that two distinct adapters
are clearer than one parameterised bridge.

The `AsyncBackendSyncAdapter` is the mirror of `SyncBackendAdapter`
(ADR-0012). Together they provide the full bidirectional bridge the
hybrid model needs.

### Ownership model

- **One loop per adapter instance.** The adapter creates a new
  `asyncio.new_event_loop()` and starts a daemon `threading.Thread`
  that runs `loop.run_forever()`. The loop is private — not shared,
  not exposed, not reused across adapter instances.
- **One thread per adapter instance.** The loop thread is created in
  `__init__` and joined in `close()`. It is dedicated to this adapter;
  no other work is scheduled on it.
- **Thread-safe for concurrent sync callers.** Multiple threads may
  call sync methods on the same adapter concurrently. Each call
  submits an independent coroutine to the loop and blocks on its own
  future. Ordering between concurrent callers is not guaranteed;
  callers that need deterministic ordering must coordinate
  externally (e.g. their own lock or queue).

### Submission and blocking

- Each sync method wraps the corresponding `AsyncBackend` coroutine
  and submits it via `asyncio.run_coroutine_threadsafe(coro, loop)`.
- The sync method blocks on the returned `concurrent.futures.Future`.
  `Future.result()` propagates the coroutine's return value or
  re-raises its exception.
- Non-I/O methods (`name`, `capabilities`, `to_key`, `native_path`,
  `resolve`, `unwrap`) delegate directly to the wrapped async backend
  without the loop, mirroring `SyncBackendAdapter`'s passthrough.
- I/O methods that return scalars or `None` — `exists`, `is_file`,
  `is_folder`, `read_bytes`, `get_file_info`, `get_folder_info`,
  `move`, `copy`, `delete`, `delete_folder`, **`check_health`** —
  follow the standard submit-and-block pattern. `check_health()`
  is explicitly **not** a no-op: connectivity errors from the
  wrapped async backend must reach the sync caller verbatim.

### Streaming iterators and open streams

- `read(path)` returns a sync file-like stream whose `read(n)` pumps
  chunks out of the backend's `AsyncIterator[bytes]`. The stream
  holds an internal byte buffer (`memoryview` slice) carrying the
  unread tail of the most recently fetched chunk: `read(n)` first
  drains that buffer, and only submits a new `__anext__` coroutine
  when the buffer is empty and more bytes are still required.
  This satisfies the `BinaryIO` contract that `read(n)` returns at
  most *n* bytes even when the backend yields larger chunks.
  `close()` submits the async iterator's `aclose()` to the loop.
- `list_files`, `list_folders`, `glob`, `iter_children` return sync
  iterators backed by the same chunk-pull pattern. Materialising the
  full listing up front is **not** acceptable: native-async backends
  exist precisely to stream, and the sync wrapper must preserve that.
- The underlying async iterator handle lives on the loop; every
  step crosses the thread boundary via `run_coroutine_threadsafe`.
- **Single-chunk in-flight invariant.** The adapter has at most one
  outstanding `__anext__` per stream/iterator: no look-ahead, no
  read-ahead pool, no parallel prefetch. The unread tail of the
  most recently fetched chunk (held in the `read()` stream's byte
  buffer described above) is the *only* sanctioned per-stream
  buffer. The bridge must not reintroduce the memory bloat that
  materialising the full listing would cause.

### Write-side content

The sync `Backend.write()` / `write_atomic()` accept the sync
`WritableContent = BinaryIO | bytes` (`src/remote_store/_types.py`).
There is no sync iterator-of-bytes input — that shape exists only on
the async side as `AsyncWritableContent = bytes | AsyncIterator[bytes]`
(`src/remote_store/aio/_types.py`). The bridge therefore goes
**sync `BinaryIO` → `AsyncIterator[bytes]`**, not the other way:

- `bytes` content is forwarded as-is to the async coroutine.
- `BinaryIO` content is wrapped in an internal `AsyncIterator[bytes]`
  that calls `asyncio.to_thread(stream.read, chunk_size)` per chunk
  inside the submitted coroutine, so the event loop never blocks on
  the caller's blocking file object. The single-chunk in-flight
  invariant from § Streaming applies symmetrically: at most one
  pending `to_thread` per write, no parallel pre-read.
- `write_atomic(path, content, …)` follows the identical pattern.
  The `ATOMIC_WRITE` capability gate is enforced by the wrapped
  async backend, not the adapter — the adapter forwards the call
  unchanged and lets the backend raise `CapabilityNotSupported` if
  the gate is closed.
- `open_atomic(path, …)` — abstract on sync `Backend`, with **no
  async analogue** on `AsyncBackend`. The adapter synthesises it as
  a context manager that yields a `SpooledTemporaryFile`; on clean
  `__exit__` the spool is rewound and submitted to the wrapped
  backend's `write_atomic` (a single `bytes`/`BinaryIO` write); on
  exception the spool is dropped and `path` is untouched. The
  capability gate is the same as `write_atomic` — backends without
  `ATOMIC_WRITE` raise `CapabilityNotSupported` when the spool
  flushes. (Synthesising over `write_atomic` rather than extending
  `AsyncBackend` keeps the async ABC unchanged; ID-127 does not need
  an `open_atomic`-shaped Graph operation.)

### Cancellation

- Cancellation flows from sync to async by calling
  `Future.cancel()` on the `concurrent.futures.Future` returned by
  `run_coroutine_threadsafe`. This schedules `Task.cancel()` on the
  underlying asyncio task.
- Async backends are expected to honour `asyncio.CancelledError`
  normally; cleanup (closing HTTP responses, releasing connections,
  aborting upload sessions) happens inside the async code as usual.
- `concurrent.futures.Future.cancel()` is a best-effort flag, and
  `asyncio.Task.cancel()` only *requests* cancellation — the task
  observes `CancelledError` at the next `await` point and may
  still run cleanup before it actually exits (CPython issues
  python/cpython#103819 and python/cpython#105836 document the
  exact semantics). The adapter's `close()` therefore waits for
  in-flight tasks to drain before stopping the loop; ad-hoc
  per-call cancellation surfaces `CancelledError` to the sync
  caller without a teardown guarantee.
- `KeyboardInterrupt` is **not** specially handled. It propagates
  out of the blocking `Future.result()` like any other exception;
  the in-flight async task is left running and is cancelled when
  the adapter's `close()` runs (or when the daemon thread is
  reaped at process exit). Adding KI-to-cancel translation would
  give this one backend behaviour that no sync backend has, which
  costs more in contract asymmetry than the convenience earns.

### Behaviour when the caller is in a running loop

- **Default: fail fast.** If a sync method is invoked from a thread
  with a running event loop, the adapter raises a clear
  `RuntimeError` explaining that the sync Store API cannot block a
  running loop and directing the caller to `AsyncStore` instead.
  This keeps the sync contract genuinely sync and prevents
  deadlocks. Aligned with ADR-0012 § Async posture: the sync
  `Store` is **not coroutine-safe**, by design — async callers use
  `AsyncStore`, full stop.
- **Detection.** The adapter checks
  `asyncio.get_running_loop()` (which raises if no loop is running)
  to decide. Detection happens at the entry of every blocking call,
  not at adapter construction, because the caller's loop context is
  per-call.
- **No opt-in nest-asyncio path in v1.** The door is open to add one
  later behind an explicit flag, but the default design does not
  require it and the first release does not ship it. Notebook and
  GUI users are directed to use `AsyncStore` directly.

### `nest_asyncio` stance

- Not a runtime dependency. Not imported by the adapter.
- If a future compatibility mode is added, it will be an explicit
  opt-in with its own ADR. This ADR commits to *not* relying on
  `nest_asyncio` for correctness.

### Lifecycle

- `close(timeout: float | None = 30.0)` submits
  `self._async_backend.aclose()` to the loop, waits for in-flight
  tasks to drain, calls `loop.call_soon_threadsafe(loop.stop)`, and
  joins the thread with the supplied bound. The default of 30 s
  matches the existing per-backend network-call ceilings; passing
  `None` waits indefinitely. If the timeout expires, the adapter
  logs a warning at `WARNING` level naming the unfinished tasks and
  returns; the daemon thread is torn down with the process.
- Context-manager protocol (`__enter__` / `__exit__`) delegates to
  `close()` on exit.
- The adapter is a one-shot resource: once closed, further calls
  raise a clear error rather than silently restarting the loop.

### Error propagation

- Exceptions raised inside the async coroutine are re-raised
  verbatim in the sync caller via `Future.result()`. Traceback
  preservation follows the standard `concurrent.futures` behaviour.
- Error types and the canonical `path` / `backend` attributes
  (ERR-001 in `sdd/specs/005-error-model.md`) are preserved
  exactly: the adapter does not wrap or translate exceptions, and
  the error-mapping rules established by `AsyncBackend`
  implementations under ADR-0012 reach the sync caller unchanged.
- `TimeoutError` from the async layer stays `TimeoutError`;
  `ResourceLocked` (ADR-0024) stays `ResourceLocked`; and so on.

### `read_seekable` (sync-only convenience)

`read_seekable` is concrete on the sync `Backend` (with a
`SpooledTemporaryFile` fallback over `read()`); it has **no async
analogue** on `AsyncBackend`. The adapter does *not* override it:
the inherited default sees a chunk-pull stream, calls `.seekable()`
(which returns `False`), and spools to disk-or-memory exactly as it
already does for the synchronous backends that emit non-seekable
streams. No new code path is needed; this section exists so the
implementer does not mistakenly wire a no-op.

A future native fast-path (e.g. issuing per-`read()` HTTP `Range`
requests directly through the async backend, mirroring
`AzureBackend`) is out of scope for this ADR. If added, it would
need an explicit async `read_seekable`-shaped operation on
`AsyncBackend` and is tracked as a Graph follow-up.

### Capability translation

The adapter does **not** blindly forward the wrapped backend's
`CapabilitySet`. The bridge changes the observable shape of two
capabilities and must mask one off:

- **`SEEKABLE_READ` — masked off.** SIO-008 promises that
  `Backend.read()` returns a natively seekable stream. The chunk-pull
  pump returned by this adapter is forward-only; no `seek()`
  accelerator can be honoured without buffering. The adapter strips
  `SEEKABLE_READ` from the forwarded set even when the wrapped
  async backend declares it. Callers that need random access go
  through `read_seekable` and pay the spool cost (above), which is
  the same fallback every non-seekable sync backend already uses.
- **`LAZY_READ` — preserved.** SIO-009 requires `read()` to fetch
  data lazily on demand. The single-chunk in-flight invariant +
  `__anext__`-per-`read(n)` cadence preserves laziness end-to-end:
  the bridge never pre-reads beyond what the sync caller has asked
  for. Forwarded unchanged.
- **`ATOMIC_WRITE`, `ATOMIC_MOVE`, `GLOB`, and the remaining flags**
  — preserved unchanged. The async coroutine performs the operation;
  the bridge only marshals the call. Folder listing and folder
  deletion have no dedicated capability flag; they remain gated by
  `LIST` / `DELETE` on the wrapped backend per the sync `Backend`
  contract (see spec 029 § ASYNC-084).

`resolve()` delegates directly (no I/O, no loop).

`unwrap()` is **not** a generic passthrough: an `httpx.AsyncClient`
returned from a sync `unwrap()` is bound to the private loop in the
daemon thread, and using it from the caller's thread will fail or
corrupt loop state. The adapter raises `CapabilityNotSupported`
unless the wrapped backend exposes a sync-safe handle (mirroring
`SyncBackendAdapter.unwrap`'s behaviour for unsupported types). The
async handle remains reachable to coroutines submitted via the same
adapter; callers that need it directly should construct an
`AsyncStore` instead.

### Module placement

`src/remote_store/_async_to_sync_adapter.py` — in the **core**
module, not under `aio/`. Symmetric with `SyncBackendAdapter`
(which lives in `aio/` because it implements `AsyncBackend`):
this adapter implements the sync `Backend` ABC, so it belongs
with the sync core. Putting it under `aio/` would force every
sync `Store` user that wraps an async backend to import the
`aio/` runtime modules at construction time, inverting the layering
invariant that sync code stays independent of `aio/`.

`AsyncBackend` is imported lazily inside the adapter's `__init__`
to avoid a top-level core → aio import. Public re-export from
`remote_store` follows the `SyncBackendAdapter` re-export pattern
in shape (alongside `Backend`, `Store`).

### Store-level wiring

The sync `Store` gains a construction path that accepts an
`AsyncBackend` and wraps it with `AsyncBackendSyncAdapter`
automatically — the mirror of `AsyncStore`'s auto-wrap of sync
`Backend` (ADR-0012 § 2). Registry integration for the Graph
backend is specified in spec 044; the adapter itself is backend-
agnostic.

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
  warn when wrapped over a bridged backend (tracked separately).
- **Bridged read streams are forward-only.** The `BinaryIO` returned
  by `read()` exposes `read(n)` and `close()` only. Extensions that
  reach for `seek()`, `tell()`, `seekable()`, `readable()`, or
  `fileno()` on the stream object will receive `False` /
  `AttributeError` as appropriate — `SEEKABLE_READ` is masked off so
  no extension that respects the capability gate will reach for
  them. Random-access callers route through `read_seekable` and pay
  the spool fallback (above).

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
