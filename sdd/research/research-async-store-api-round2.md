# Research Round 2: Async Store API vs Current Feature Surface (ID-013)

**Date:** 2026-03-30
**Backlog item:** ID-013 (Async Store / Backend API)
**Predecessor:** [Round 1 research](research-async-store-api.md) (2026-03-03)
**Status:** Research complete — findings ready for review

---

## 1. Purpose

The backlog item ID-013 requires a second research round before
implementation proceeds. Three things changed since the initial research
on 2026-03-03:

1. The sync Store/Backend API evolved (3 new methods, parameter additions).
2. Spec 029 (draft) and ADR-0012 were written against the March 3 surface.
3. The question of whether async belongs in the same package remains open.

This document audits the current FEATURES.md (v0.20.0) against spec 029
and ADR-0012, identifies gaps, and evaluates the audience/packaging
question.

---

## 2. Feature Gap: Current Sync API vs Spec 029

### 2.1 Store methods added after spec 029 was drafted

| Method | Added | ID | In spec 029? | Async implications |
|--------|-------|----|-------------|-------------------|
| `read_seekable(path)` | 2026-03-24 | ID-102 | No | Needs async equivalent or explicit deferral. Seekable streams don't map cleanly to `AsyncIterator[bytes]` — see §3. |
| `resolve(key) -> ResolutionPlan` | 2026-03-29 | ID-120 | No | **Sync** — pure string/metadata, no I/O. Add to non-I/O passthrough list alongside `to_key`, `native_path`. |
| `write_text(path, text)` | Pre-existing | — | Missing from ASYNC-046 enumeration | Trivial async equivalent: `await async_store.write_text(...)`. Delegates to `write()` after encoding. |
| `ping()` | Pre-existing | — | Missing | Noted in backlog as needing async equivalent. Maps to `check_health()` on backend. Simple: `await asyncio.to_thread(backend.check_health)`. |
| `open_atomic(path)` | Pre-existing | — | Noted as needing deferral | Context-manager streaming writes are hard to bridge async. See §3. |

### 2.2 Backend methods added after spec 029

| Method | Added | In spec 029? | Notes |
|--------|-------|-------------|-------|
| `read_seekable(path) -> BinaryIO` | 2026-03-24 | No | Non-abstract with spool fallback. Some backends override (Azure range reader, HTTP). |
| `resolve(path) -> ResolutionPlan` | 2026-03-29 | No | Non-abstract with default impl. Sync — no I/O. |
| `check_health() -> None` | Pre-existing | No | Non-abstract, default no-op. Store exposes as `ping()`. |
| `list_files` `max_depth` parameter | Pre-existing | Not reflected | Spec 029 ASYNC-014 omits `max_depth`. |
| `list_folders` `max_depth` parameter | Pre-existing | Not reflected | Spec 029 ASYNC-015 omits `max_depth`. |
| `get_folder_info` `max_depth` parameter | Pre-existing | Not reflected | Spec 029 ASYNC-017 omits `max_depth`. |

### 2.3 Extensions added since round 1

| Extension | Added | Async impact |
|-----------|-------|-------------|
| `ParquetDatasetStore` (ID-122) | 2026-03-22 | Phase 3 concern. Wraps PyArrow, which has its own async story. |
| `Dagster` IO manager v2 pattern | Post-round-1 | Key use case — see §5. |

### 2.4 Summary of spec 029 amendments needed

Before implementation, spec 029 must be updated to cover:

1. **ASYNC-057: `read_seekable()`** — design decision needed (see §3).
2. **ASYNC-058: `resolve()`** — sync passthrough, no I/O. Add to ASYNC-034 property passthrough list.
3. **ASYNC-059: `ping()` / `check_health()`** — `async def ping()` on AsyncStore, delegates to `await asyncio.to_thread(backend.check_health)` via SyncBackendAdapter.
4. **ASYNC-046 update** — add `write_text`, `read_seekable`, `resolve`, `ping` to enumeration.
5. **`max_depth` parameters** — add to ASYNC-014, ASYNC-015, ASYNC-017.
6. **ASYNC-060..063: `AsyncMemoryBackend`** — already noted in backlog.
7. **`open_atomic` deferral note** — already noted in backlog.
8. **ASYNC-036: Streaming write bridging** — `SyncBackendAdapter` must materialize `AsyncIterator[bytes]` to `bytes` before calling sync `write()`.

---

## 3. Design Decisions Needed

### 3.1 `read_seekable` in async context

**Problem:** `read_seekable()` returns `BinaryIO` (seekable). The async
read pattern is `AsyncIterator[bytes]` (not seekable). These are
fundamentally different contracts.

**Options:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Omit from Phase 1 | Defer `read_seekable` to Phase 2 | Simple. No half-baked abstraction. | Feature gap vs sync API. |
| B. Return `bytes` | `async def read_seekable(path) -> bytes` materializes fully | Seekable in-memory via `io.BytesIO`. Simple. | Defeats streaming for large files. Name is misleading. |
| C. Thread-bridge BinaryIO | Return sync `BinaryIO` obtained via `to_thread` | Preserves seekability. | Caller must use `to_thread` for each `.read()` / `.seek()` — defeats async purpose. |
| D. Async seekable protocol | New `AsyncSeekableReader` with `async read(n)`, `async seek(offset)` | True async seeking. | No stdlib equivalent. Custom protocol. Over-engineering for Phase 1. |

**Recommendation:** **Option A (defer)**. `read_seekable` is a
convenience for random-access patterns (Arrow, Parquet). In async
contexts, callers either: (a) use `read_bytes()` + `io.BytesIO` for
small files, or (b) use native async SDK features for large files
(Phase 2). Document the workaround.

### 3.2 `open_atomic` in async context

**Problem:** `open_atomic()` is a sync context manager yielding `BinaryIO`.
The caller writes incrementally. In async, this requires an async context
manager yielding something writable — but there's no stdlib async
writable stream.

**Recommendation:** **Defer to Phase 2.** `write_atomic(path, content)`
(which accepts `bytes | AsyncIterator[bytes]`) covers the async use
case. The incremental-write-to-file pattern of `open_atomic` is inherently
sync. Note this in spec 029.

---

## 4. Scope & Complexity Assessment

### 4.1 What async adds to the codebase

| Component | Sync (current) | Async (Phase 1) | Delta |
|-----------|----------------|-----------------|-------|
| Backend ABC | `_backend.py` (~430 lines) | `_async_backend.py` (~350 est.) | +350 |
| Store | `_store.py` (~900 lines) | `_async_store.py` (~750 est.) | +750 |
| SyncBackendAdapter | — | `_sync_adapter.py` (~200 est.) | +200 |
| AsyncMemoryBackend | — | `_async_memory.py` (~250 est.) | +250 |
| ProxyStore (async) | `_proxy.py` (~220 lines) | `_async_proxy.py` (~220 est.) | +220 |
| Types | `_types.py` | `AsyncWritableContent` addition | +5 |
| Tests | ~7000 lines backend+store | ~3000 est. (via parametrize reuse) | +3000 |
| Drift tests | — | Sync↔async parity assertions | +200 |
| **Total** | | | **~5000 lines** |

Phase 1 adds roughly 5K lines (~2K source, ~3K tests). The codebase is
currently ~15K source lines. This is a ~13% increase, not a doubling.

Phase 2 (native async backends) and Phase 3 (async extensions) would each
add similar amounts, but those are separate decisions.

### 4.2 Documentation impact

- API reference: auto-generated from docstrings — async classes appear
  alongside sync. Manageable.
- Tutorials: one new "Async Quick Start" page. Existing tutorials stay
  sync.
- FEATURES.md: add "Async API" section listing `AsyncStore`, `AsyncBackend`,
  `SyncBackendAdapter`.

### 4.3 Package surface impact

New public exports (Phase 1):
- `AsyncBackend`, `AsyncStore`, `SyncBackendAdapter`, `AsyncMemoryBackend`
- `AsyncWritableContent` type alias
- `async_store()` convenience constructor (mirrors `store()`)

This is 6 new symbols. The current public surface is ~80 symbols. An 8%
increase.

---

## 5. Audience Analysis

### 5.1 Who benefits from async?

| Audience | Use case | Benefit |
|----------|----------|---------|
| **FastAPI / Starlette users** | File upload/download endpoints | Avoid blocking ASGI thread pool. True async I/O in Phase 2. |
| **Dagster pipelines** | IO managers in async ops | Dagster 1.9+ supports `AsyncIOManager`. Currently forces sync → thread delegation. |
| **Data platform teams** | Concurrent file operations across stores | `asyncio.gather()` for parallel reads/writes without thread-pool exhaustion. |
| **Litestar / aiohttp users** | Similar to FastAPI | Same thread-blocking concern. |
| **CLI / script users** | Batch processing | Marginal benefit — sync is fine. |
| **Notebook / citizen developers** | Interactive exploration | No benefit. Sync is simpler. |

### 5.2 Dagster specifically

Dagster is the most concrete use case. The current `RemoteStoreIOManager`
is sync. Dagster's `AsyncIOManager` (available since 1.9) allows
`handle_output` and `load_input` to be async, which matters for:

- Ops that do concurrent I/O (e.g., reading multiple partitions in parallel)
- Avoiding thread-pool exhaustion when many ops run concurrently
- Integration with async-native data sources

However, the Dagster async IO manager is a Phase 3 extension concern. It
requires `AsyncStore` (Phase 1) to exist first.

### 5.3 Is the target audience "citizen developers"?

The library's README positions it as "unified file storage" — which serves
both citizen developers (simple local/S3 usage) and platform engineers
(custom backends, extensions, Dagster integration). Async specifically
serves the latter group. Citizen developers will never use `AsyncStore`.

**This is fine.** Libraries routinely serve multiple audiences. httpx has
`Client` for simple scripts and `AsyncClient` for web services. The key
is that the sync API remains the default and the async API is opt-in.

---

## 6. Packaging: Same Package vs Separate?

### 6.1 Options

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Same package | `remote_store.AsyncStore` alongside `remote_store.Store` | Single install. Shared types/errors. No version drift. | Larger package. Async code loaded even by sync users. |
| B. Separate package | `remote-store-async` depending on `remote-store` | Clean separation. Sync users unaffected. | Two packages to version. Import confusion. Shared type changes require coordinated releases. |
| C. Subpackage | `remote_store.aio` (lazy-loaded) | Logical separation. Single package. Zero import cost for sync users. | Slightly more complex packaging. |

### 6.2 Ecosystem precedent

| Library | Approach | Notes |
|---------|----------|-------|
| httpx | Same package (`httpx.AsyncClient`) | Most popular pattern |
| SQLAlchemy | Same package (`sqlalchemy.ext.asyncio`) | Works well at scale |
| Azure SDK | Same package (`azure.storage.blob.aio`) | Sub-namespace |
| redis-py | Same package (`redis.asyncio`) | Sub-namespace |
| aiohttp | Separate package (async-only) | Different case — no sync equivalent |
| boto3 / aioboto3 | Separate packages | Cautionary tale — version coupling issues |

### 6.3 Recommendation: Same package, `remote_store.aio` namespace

**Option C.** Put async classes in `remote_store.aio`:

```python
from remote_store.aio import AsyncStore, AsyncBackend

# Convenience re-export at top level (optional)
from remote_store import AsyncStore
```

Rationale:
- **Single package** avoids version drift (the #1 pain point with
  aioboto3/aiobotocore).
- **Sub-namespace** keeps the top-level `import remote_store` clean for
  sync users — no async symbols pollute the default namespace.
- **Lazy loading** (`__init__.py` with `__getattr__`) means sync users
  pay zero import cost for async code.
- **Shared types** (`FileInfo`, `FolderEntry`, `RemotePath`, errors,
  `Capability`) are used by both sync and async — same-package is natural.

---

## 7. Updated Ecosystem Landscape (March 2026)

### 7.1 Changes since round 1

| Topic | Round 1 (March 3) | Now (March 30) |
|-------|-------------------|----------------|
| SQLAlchemy async | 2.0 stable | 2.1.0b1 (Jan 2026) dropped greenlet-by-default. `sqlalchemy[asyncio]` extra now required. Validates our "optional async" approach. |
| Python 3.13 | — | `asyncio.TaskGroup` stable. Good for batch operations. |
| obstore | Mentioned in passing | Growing alternative to s3fs. Native async, Rust-backed. Worth watching for Phase 2. |
| Dagster async IO | Existed | Now more widely adopted in Dagster community. Concrete demand signal. |

### 7.2 Native async SDK readiness per backend

| Backend | Sync SDK | Async SDK | Phase 2 readiness |
|---------|----------|-----------|-------------------|
| Local | `pathlib` / `os` | `asyncio.to_thread` (no native) | Wrap only — acceptable |
| Memory | dict + threading.Lock | dict + asyncio.Lock | Native async trivial |
| HTTP | urllib / requests / httpx | httpx `AsyncClient` | Ready |
| S3 | s3fs (sync wrapper over async internals) | s3fs async internals or obstore | Ready (s3fs) or watch (obstore) |
| S3-PyArrow | PyArrow C++ filesystem | PyArrow async (limited) | Thread-wrap for Phase 1 |
| SFTP | paramiko | asyncssh | Ready (EPL v2.0 license OK for optional dep) |
| Azure | azure-storage-file-datalake | `azure.storage.file.datalake.aio` | Ready |
| SQL-Blob | SQLAlchemy sync | SQLAlchemy async (`[asyncio]` extra) | Ready |
| SQL-Query | SQLAlchemy + PyArrow | SQLAlchemy async + PyArrow | Ready |

**All backends have a viable async path.** No blockers for Phase 2.

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| API drift between Store and AsyncStore | Medium | High | Drift-protection tests (ADR-0010 pattern). CI fails if signatures diverge. |
| `SyncBackendAdapter` memory pressure (iterator materialization) | Low | Medium | Documented limitation. Phase 2 native backends eliminate it. |
| Low adoption (citizen devs don't need async) | Medium | Low | Async is opt-in. Zero cost to sync users. Platform engineers are the audience. |
| Maintenance burden (2 APIs to update) | Medium | Medium | Shared types, shared error model. Only I/O methods differ. ~13% code increase, not 100%. |
| anyio/trio demand | Low | Low | asyncio-only for now. Can add anyio later without breaking changes. |

---

## 9. Conclusions

1. **Spec 029 needs 8 amendments** before implementation (§2.4). The
   largest design decisions are `read_seekable` (recommend defer) and
   `open_atomic` (recommend defer).

2. **Phase 1 scope is manageable**: ~5K lines (2K source + 3K tests),
   ~13% codebase increase. Not a doubling.

3. **Same-package with `remote_store.aio` namespace** is the right
   packaging approach. Follows httpx/SQLAlchemy/redis-py precedent.

4. **The audience is platform engineers**, not citizen developers. This
   is the same audience that uses Dagster, FastAPI, and custom backends.
   Async is opt-in — sync users are unaffected.

5. **All backends have viable async SDKs** for Phase 2. No ecosystem
   blockers.

6. **`resolve()` and `ping()`** are trivial additions to the async surface.
   `read_seekable` and `open_atomic` should be deferred to Phase 2.

### Recommended next steps

1. Amend spec 029 with the 8 items from §2.4.
2. Implement Phase 1: `AsyncBackend`, `SyncBackendAdapter`, `AsyncStore`,
   `AsyncMemoryBackend` in `remote_store.aio`.
3. Add `pytest-asyncio` to dev dependencies.
4. Add drift-protection tests ensuring sync↔async method parity.
5. Update FEATURES.md with async section after implementation.

---

## References

- [Round 1 research](research-async-store-api.md) (2026-03-03)
- [ADR-0012](../adrs/0012-async-store-backend-api.md) — Hybrid model decision
- [Spec 029](../specs/029-async-store-backend-api.md) — Phase 1 spec (draft)
- `FEATURES.md` (repo root) — v0.20.0 feature surface
- `sdd/BACKLOG.md` — ID-013 status and remaining items
