# Async test infrastructure — orientation
<!-- doc: repo-only -->

Start here when you are adding a new **async backend** (the next is
[ID-127 OneDrive/SharePoint Graph](../../sdd/BACKLOG.md)) or an async ext
module. This page is a **map**, not a rulebook: it names the moving parts and
points at the authority for each. When this page and an authority disagree, the
authority wins.

| Authority | Owns |
|---|---|
| [spec 029](../../sdd/specs/029-async-store-backend-api.md) | `AsyncBackend` / `AsyncStore` contract, the two adapters, capability translation (ASYNC-001..093) |
| [spec 048](../../sdd/specs/048-testing-architecture.md) | Test-tree shape, fixture registry, kind / stage / replay (TEST-001..010) |
| [ADR-0025](../../sdd/adrs/0025-async-to-sync-backend-adapter.md) | Why `AsyncBackendSyncAdapter` exists and how it owns its event loop |
| [`sdd/TESTING.md`](../../sdd/TESTING.md) | Placement rows plus quality rules (real deps over mocks, `match=` on every `raises`) |

## What lives here

| Path | Role |
|---|---|
| [`conftest.py`](conftest.py) | Cross-cutting async fixtures: `async_backend` (parametrized `native` / `adapted`), `async_store`, `native_memory`, `native_store`, `RestrictedAsyncBackend` |
| [`_doubles.py`](_doubles.py) | Failure-path doubles: `_HangingAsyncBackend`, `_RaisingAsyncBackend` |
| `test_async_*.py` | Cross-cutting suites: ABC (`test_async_backend.py`), drift guard (`test_async_drift.py`), cancellation, PBT, store, and the two adapter suites |
| [`ext/`](ext/) | Tests for `src/remote_store/aio/ext/` modules (`test_async_<x>.py`) |

Per-backend async tests do **not** live here. They go under
`tests/backends/<name>/aio/` (TEST-003 / TEST-010). This directory holds the
shared async machinery only.

## The two adapters (read this before touching either)

They wrap in **opposite directions**. Conflating them is the most common
async-test mistake:

| Adapter | Direction | Source | Where it shows up |
|---|---|---|---|
| `SyncBackendAdapter` | sync `Backend` → `AsyncBackend` | `src/remote_store/aio/_sync_adapter.py` | the `adapted` leg of every native/adapted parametrization (`conftest.py`, `memory_async.py`) |
| `AsyncBackendSyncAdapter` | `AsyncBackend` → sync `Backend` | `src/remote_store/_async_to_sync_adapter.py` | its own suites `test_async_to_sync_adapter*.py`, driven by the `_doubles.py` doubles |

So the dual **native / adapted** conformance parametrization runs on
`SyncBackendAdapter` — not `AsyncBackendSyncAdapter`.

## Live vs doubles

Two layers, not interchangeable:

- **Real backends** carry the behavioural contract. Async conformance runs every
  registered async fixture; for `memory` that is two registry entries —
  `memory_async_native` (`AsyncMemoryBackend`) and `memory_async_adapted`
  (`SyncBackendAdapter(MemoryBackend())`) — registered in
  [`memory_async.py`](../backends/fixtures/memory_async.py). Conformance is
  registry-driven: register the fixture and the suite picks it up, with no
  per-test wiring.
- **Doubles** in [`_doubles.py`](_doubles.py) exist only for paths a real
  backend cannot reach deterministically: timeouts, cancellation, verbatim error
  propagation, mid-stream iterator failure. Reach for a double only when a real
  backend cannot drive the path (`sdd/TESTING.md` Rule 6), never as a shortcut
  around a real dependency.

## Adding a new async backend — checklist

1. Implement the `AsyncBackend` ABC (spec 029) at
   `src/remote_store/aio/backends/_<name>.py`.
2. Set `__mirror__` to the sync peer (ID-159; the drift guard
   `test_async_drift.py` and `TestAsyncBackendMirror` enforce the parity).
3. Register the fixture(s) in `tests/backends/fixtures/<name>_async.py` —
   template: [`memory_async.py`](../backends/fixtures/memory_async.py). Add a
   second `adapted` entry only when a sync peer exists to wrap.
4. Put per-backend tests under `tests/backends/<name>/aio/` — templates:
   [`memory/aio/test_basics.py`](../backends/memory/aio/test_basics.py), and
   [`azure/aio/`](../backends/azure/aio/) for the live/replay split.
5. Let conformance run itself: registration (step 3) is the wiring.
6. Add a double **only** when a failure path needs one. Extend `_doubles.py`,
   don't fork it.

Don't re-derive the conftest layout per backend — that is the sprawl BK-164 and
ID-156 cleaned up. A fixture you are tempted to add here probably belongs in
`tests/backends/<name>/` instead.
