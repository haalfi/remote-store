# ADR-0012: Async Store / Backend API — Hybrid Model

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

ID-013 requires async versions of `Store` and `Backend` for use in async
frameworks (FastAPI, aiohttp, Litestar, Starlette). The sync-only API
forces users to wrap every call in `asyncio.to_thread()` manually, which
is noisy, error-prone, and prevents leveraging native async I/O where the
underlying SDK supports it (s3fs, Azure aio, asyncssh).

DESIGN.md §7.3 contemplated async (`aclose` as lifecycle hook). §8 says
"no dependency on anyio / asyncio / trio" for the core — but asyncio is
stdlib, not a third-party dependency. ADR-0001 deferred async to a future
phase. The core package has zero runtime dependencies and must stay that
way in Phase 1.

Five design options were evaluated in the research
(`sdd/research/research-async-store-api.md`, section 4):

**Option A — Thread-pool wrapper only.** `AsyncStore` wraps sync `Store`
via `asyncio.to_thread()`. Simple but defeats the purpose of async —
every call goes through the default thread pool. No true async I/O.

**Option B — Full parallel hierarchy.** Separate `AsyncBackend` ABC and
`AsyncStore` with native async backends only. Right architecture, but
requires all backends upfront — too much scope for initial delivery.

**Option C — Hybrid.** `AsyncBackend` ABC with `SyncBackendAdapter` that
wraps any sync `Backend` via `asyncio.to_thread()`. `AsyncStore` accepts
both types, auto-wrapping sync backends. Immediate value with a native
async upgrade path.

**Option D — Greenlet bridge (SQLAlchemy-style).** Dismissed — overkill
for our flat Backend ABC. Adds a C extension dependency (greenlet).

**Option E — Async-first with sync wrapper (fsspec-style).** Dismissed —
requires rewriting all backends as async-first. Breaking internal change
with no user-facing benefit.

## Decision

<!-- adr:decision -->
Use **Option C (Hybrid)**: `AsyncBackend` ABC + `SyncBackendAdapter` +
`AsyncStore`.
<!-- /adr:decision -->

1. **Separate async types.** `AsyncBackend` (ABC) and `AsyncStore` are
   distinct types from `Backend` and `Store`. No shared base class — they
   serve separate use cases. Follows the httpx pattern (separate `Client`
   / `AsyncClient`, shared config types).

2. **Auto-wrapping.** `AsyncStore` accepts both `AsyncBackend` and sync
   `Backend`. If given a sync `Backend`, it auto-wraps via
   `SyncBackendAdapter`. Users get async immediately with existing
   backends, no manual wrapping needed.

3. **`read()` returns `AsyncIterator[bytes]`.** There is no standard
   `AsyncBinaryIO` in Python. `AsyncIterator[bytes]` is the idiomatic
   async streaming pattern (used by httpx, aiohttp). `read_bytes()`
   remains the convenience method returning `bytes`.

4. **`aclose()` naming.** Follows the Python convention for async
   cleanup: `aclose` on async generators, `asyncio.StreamWriter`, and
   redis-py. `__aexit__` calls `aclose()`.

5. **`asyncio` only.** No anyio or trio dependency. The rationale is
   simplicity (fewer abstractions, easier debugging), not dependency cost
   — our async audience (FastAPI, Starlette, httpx users) already has
   anyio transitively. Can be revisited without breaking changes.

6. **Iterator materialization.** `SyncBackendAdapter` materializes
   `list_files()`, `list_folders()`, `glob()`, and `iter_children()` in
   a thread (collects to list, then yields). Cannot stream across thread
   boundaries. Native async backends (Phase 2) stream properly.

7. **Non-I/O methods stay sync.** `to_key()`, `unwrap()`,
   `native_path()`, `capabilities`, `name` — no I/O, no reason to be
   async.

8. **Phased rollout.** Phase 1: core surface (`AsyncBackend`,
   `SyncBackendAdapter`, `AsyncStore`, `AsyncMemoryBackend`). Phase 2:
   native async backends. Phase 3: async extensions. Each phase gets its
   own spec.

9. **Zero new runtime deps in Phase 1.** Uses only stdlib `asyncio`.
   Optional async deps (asyncssh) come in Phase 2 as extras.

## Consequences

- Async users unblocked immediately with existing sync backends via
  auto-wrapping.
- Native async backends (Phase 2) provide true async I/O for cloud
  backends without changing the `AsyncStore` API.
- No breaking changes to the existing sync API.
- Same error model, path model, capability model, metadata types.
- Doubles the abstraction surface — `Backend` + `AsyncBackend`, `Store`
  + `AsyncStore`. Mitigated by drift-protection tests (ADR-0010 pattern).
- `SyncBackendAdapter` materializes iterators, increasing memory for
  large listings on wrapped sync backends. Native async backends stream.
- Extension modules need async variants (Phase 3).
