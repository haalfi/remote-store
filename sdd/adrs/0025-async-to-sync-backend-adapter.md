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
  future. Ordering between concurrent callers is not guaranteed.

### Submission and blocking

- Each sync method wraps the corresponding `AsyncBackend` coroutine
  and submits it via `asyncio.run_coroutine_threadsafe(coro, loop)`.
- The sync method blocks on the returned `concurrent.futures.Future`.
  `Future.result()` propagates the coroutine's return value or
  re-raises its exception.
- Non-I/O methods (`name`, `capabilities`, `to_key`, `native_path`,
  `resolve`, `unwrap`) delegate directly to the wrapped async backend
  without the loop, mirroring `SyncBackendAdapter`'s passthrough.

### Streaming iterators and open streams

- `read(path)` returns a sync file-like stream whose `read(n)` pumps
  chunks out of the backend's `AsyncIterator[bytes]`. Each `read(n)`
  submits an `__anext__` coroutine to the loop and blocks. `close()`
  submits the async iterator's `aclose()` to the loop.
- `list_files`, `list_folders`, `glob`, `iter_children` return sync
  iterators backed by the same chunk-pull pattern. Materialising the
  full listing up front is **not** acceptable: native-async backends
  exist precisely to stream, and the sync wrapper must preserve that.
- The underlying async iterator handle lives on the loop; every
  step crosses the thread boundary via `run_coroutine_threadsafe`.

### Write-side content

- `write(path, content, …)` accepts the sync `WritableContent` types
  (`bytes`, file-like, iterator of `bytes`). Iterator-of-bytes
  arguments are adapted into an `AsyncIterator[bytes]` that pulls the
  next sync chunk on a worker thread via `asyncio.to_thread` inside
  the submitted coroutine, so the event loop never blocks on the
  caller's iterator.

### Cancellation

- Cancellation flows from sync to async by calling
  `Future.cancel()` on the `concurrent.futures.Future` returned by
  `run_coroutine_threadsafe`. This schedules `Task.cancel()` on the
  underlying asyncio task.
- Async backends are expected to honour `asyncio.CancelledError`
  normally; cleanup (closing HTTP responses, releasing connections,
  aborting upload sessions) happens inside the async code as usual.
- `Future.cancel()` may return before the underlying task has fully
  unwound. The adapter's `close()` waits for in-flight tasks to
  finish their cancellation before stopping the loop; ad-hoc
  per-call cancellation surfaces `CancelledError` to the sync caller
  without a teardown guarantee.
- `KeyboardInterrupt` in the sync caller is translated into a cancel
  on the in-flight future before the exception is re-raised.

### Behaviour when the caller is in a running loop

- **Default: fail fast.** If a sync method is invoked from a thread
  with a running event loop, the adapter raises a clear
  `RuntimeError` explaining that the sync Store API cannot block a
  running loop and directing the caller to `AsyncStore` instead.
  This keeps the sync contract genuinely sync and prevents
  deadlocks.
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

- `close()` submits `self._async_backend.aclose()` to the loop,
  waits for in-flight tasks to drain, calls
  `loop.call_soon_threadsafe(loop.stop)`, and joins the thread with
  a bounded timeout. If the timeout expires, the adapter logs a
  warning and returns; the daemon thread is torn down with the
  process.
- Context-manager protocol (`__enter__` / `__exit__`) delegates to
  `close()` on exit.
- The adapter is a one-shot resource: once closed, further calls
  raise a clear error rather than silently restarting the loop.

### Error propagation

- Exceptions raised inside the async coroutine are re-raised
  verbatim in the sync caller via `Future.result()`. Traceback
  preservation follows the standard `concurrent.futures` behaviour.
- Error types and error attributes (ADR-0012 § 4, ERR-001) are
  preserved: the adapter does not wrap or translate exceptions.
- `TimeoutError` from the async layer stays `TimeoutError`;
  `ResourceLocked` (ADR-0024) stays `ResourceLocked`; and so on.

### Capabilities and resolution

- `capabilities` delegates to the wrapped async backend without
  modification — the flat capability set is preserved across the
  bridge.
- `resolve()` delegates directly (no I/O, no loop).
- `unwrap()` returns whatever the async backend returns; callers
  that ask for a sync native handle from an async-native backend
  get whatever the backend exposes (typically the async client).

### Module placement

`src/remote_store/aio/_async_to_sync_adapter.py`. Parallel to
`_sync_adapter.py` so the two bridges sit side by side. Public
re-export from `remote_store.aio` matches the `SyncBackendAdapter`
pattern.

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
- **No new capability.** `CapabilitySet` is unchanged; the adapter
  forwards the wrapped backend's declaration as-is.
- **No new runtime dependency.** Stdlib `asyncio` and `threading`
  only.

## References

- ADR-0012: Async Store / Backend API — Hybrid Model
- ADR-0023: Async Monitor-URL Polling
- ADR-0024: `ResourceLocked` Error Type
- RFC-0010: Microsoft Graph Backend (§ Async posture)
- `sdd/specs/003-backend-adapter-contract.md`
- `src/remote_store/aio/_sync_adapter.py` (mirror implementation)
- Python stdlib: `asyncio.run_coroutine_threadsafe`,
  `asyncio.Task.cancel`
- `concurrent.futures.Future.cancel` semantics
