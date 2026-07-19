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

Use **Option C (Hybrid)**: `AsyncBackend` ABC + `SyncBackendAdapter` +
`AsyncStore`.

1. **Separate async types.** `AsyncBackend` (ABC) and `AsyncStore` are distinct
   from `Backend` and `Store`, with no shared base, because they serve separate
   use cases (the httpx `Client`/`AsyncClient` pattern). *Reverse if* a shared
   base removes more duplication than the type separation costs.

2. **Auto-wrapping.** `AsyncStore` accepts both an `AsyncBackend` and a sync
   `Backend`, auto-wrapping the latter via `SyncBackendAdapter`, so async users
   get immediate value with existing backends and no manual wrapping. *Reverse
   if* implicit wrapping hides a correctness or performance cost that an explicit
   wrap would surface.

3. **`read()` returns `AsyncIterator[bytes]`.** There is no standard
   `AsyncBinaryIO` in Python, and `AsyncIterator[bytes]` is the idiomatic async
   streaming shape (httpx, aiohttp); `read_bytes()` stays the `bytes`
   convenience. *Reverse if* a standard async binary-file protocol emerges.

4. **`asyncio` only, no anyio or trio.** Chosen for simplicity (fewer
   abstractions, easier debugging), not dependency cost; the async audience
   already has anyio transitively. *Reverse if* a supported runtime needs
   trio/anyio semantics asyncio cannot express (a non-breaking change).

5. **Non-I/O methods stay sync.** Operations with no I/O have no reason to be
   async. *Reverse if* one gains an I/O dependency.

6. **Phased rollout.** Phase 1 ships the core surface, Phase 2 native async
   backends, Phase 3 async extensions, each with its own spec. *Reverse if*
   delivering the surface whole beats staging it.

7. **Zero new runtime deps in Phase 1.** Phase 1 uses only stdlib `asyncio`,
   preserving the core's zero-dependency floor; optional async deps (asyncssh)
   arrive as Phase 2 extras. *Reverse only* by deliberately abandoning the
   zero-dependency-core promise.

The `aclose()` naming and wiring, the exact non-I/O method roster, and the
`read_bytes` contract are spec-rate and live in
[spec 029](../specs/029-async-store-backend-api.md) (ASYNC-007, ASYNC-020,
ASYNC-022, ASYNC-023, ASYNC-034). `SyncBackendAdapter`'s iterator materialization
is a realized consequence of auto-wrapping, covered under Consequences.

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
