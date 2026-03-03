# Research: Async Store / Backend API (ID-013)

**Date:** 2026-03-03
**Backlog items:** ID-013 (Async Store / Backend API)
**Status:** Research complete — ready for design decisions

---

## 1. Problem Statement

The current `Store` and `Backend` APIs are synchronous. Users building on async
frameworks (FastAPI, aiohttp, Litestar, Starlette) must wrap every call in
`asyncio.to_thread()` manually, which is noisy, error-prone, and prevents
leveraging native async I/O where the underlying SDK supports it.

The backlog item states:

> Async version of `Store` and `Backend` for use in async frameworks.
> Could be a parallel `AsyncStore` class or an async mode on the existing
> `Store`. Needs design decision on whether to wrap sync backends with
> `asyncio.to_thread` or require native async backends.

### Why this is critical

1. **FastAPI is the #1 Python web framework by GitHub stars.** Not offering an
   async API means every `Store` call in a FastAPI route handler blocks a thread
   from the ASGI server's threadpool, capping concurrency.
2. **Cloud backends are network I/O.** S3, Azure, and SFTP are all network-bound.
   Native async implementations can handle hundreds of concurrent operations on
   a single thread — sync-in-threadpool caps out at the OS thread limit.
3. **Ecosystem expectations.** Libraries that target both sync and async
   frameworks are now the norm in production Python (SQLAlchemy, httpx,
   redis-py, Azure SDK, etc.). A storage abstraction without async support is
   increasingly a non-starter for new projects.

### Design constraints from existing docs

- DESIGN.md §7.3 already mentions `aclose` as a lifecycle hook — async was
  always contemplated.
- DESIGN.md §8: "No dependency on anyio / asyncio / trio" + "Compatible with
  structured concurrency."
- DESIGN.md §9: "Async-only APIs" is explicitly out of scope.
- ADR-0001: "No dependency on async frameworks (sync-only initially)."
- ADR-0003: fsspec is an implementation detail — async support in fsspec/s3fs
  should not leak into our public API.
- ADR-0010: Proxy subclass pattern with drift-protection tests is the
  established pattern for Store wrappers.
- Core package has **zero runtime dependencies** (`dependencies = []`).

---

## 2. Survey: How the Python Ecosystem Handles Sync/Async Duality

### 2.1 fsspec — Async-first, auto-generated sync wrappers

**Pattern:** Write `async def _method()` on `AsyncFileSystem`, auto-generate
sync `method()` via `sync_wrapper`.

**How it works:**
- `AsyncFileSystem` has `async def _ls()`, `async def _cat_file()`, etc.
- A dedicated IO thread runs an event loop (`get_loop()`).
- `sync_wrapper` submits coroutines to this loop via
  `asyncio.run_coroutine_threadsafe` and waits on `threading.Event`.
- The sync `ls()`, `cat_file()` etc. are auto-generated from the async methods
  at class initialization time.

**Strengths:**
- Single implementation — write async once, get sync free.
- Proven in production across s3fs, gcsfs, adlfs, sshfs.

**Weaknesses:**
- Complex internal machinery (dedicated IO thread, cross-thread signaling).
- Hard to debug — sync callers don't see the event loop.
- Nested sync calls deadlock (sync method calling sync method that both go
  through the same loop).
- `__init__` can't be async, requiring workarounds.
- Naming convention (`_method` = async) is confusing.

**Relevance to us:** We already use s3fs (which inherits this pattern), but we
explicitly hide it (ADR-0003). We should not adopt this pattern for our own API.

**Sources:**
- [fsspec Async docs](https://filesystem-spec.readthedocs.io/en/latest/async.html)
- [fsspec.asyn source](https://filesystem-spec.readthedocs.io/en/latest/_modules/fsspec/asyn.html)

---

### 2.2 SQLAlchemy — Greenlet bridge (sync core, async facade)

**Pattern:** All internals are synchronous. `AsyncSession`/`AsyncEngine` use
**greenlet** to intercept blocking calls and `await` them in the async context.

**How it works:**
- User calls `await async_session.execute(stmt)`
- This spawns a greenlet running the sync `session.execute(stmt)`
- When the sync code reaches actual database I/O, it switches back to the
  async greenlet, which `awaits` the native async driver (asyncpg, etc.)
- Results flow back through the greenlet chain.

**The `run_sync()` pattern:** `AsyncSession.run_sync(fn)` runs arbitrary sync
code inside the greenlet, transparently converting blocking I/O to async.

**Strengths:**
- Zero duplication — 600K+ LOC codebase needed only ~4K lines to add async.
- All existing sync code continues to work unchanged.
- Full ORM features available in async mode.

**Weaknesses:**
- greenlet is a C extension — adds a binary dependency. (As of
  [2.1.0b1, Jan 2026](https://www.sqlalchemy.org/blog/2026/01/21/sqlalchemy-2.1.0b1-released/),
  greenlet is no longer installed by default — users must
  `pip install sqlalchemy[asyncio]`.)
- Hard to understand/debug the greenlet switching semantics.
- "Lazy loading" patterns require careful handling in async mode.
- Not truly async for CPU-bound work in the ORM layer.

**Relevance to us:** Impressive engineering, but overkill for our case. Our
backend methods are simple delegation, not a deep ORM graph. We don't have the
600K LOC justification for greenlet complexity.

**Sources:**
- [SQLAlchemy asyncio docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [How SQLAlchemy uses greenlet](https://habr.com/en/articles/767532/)
- [SQLAlchemy async discussion](https://github.com/sqlalchemy/sqlalchemy/discussions/5923)

---

### 2.3 httpx — Dual classes, shared internals

**Pattern:** Separate `Client` (sync) and `AsyncClient` (async) classes that
share configuration, request building, and transport abstractions.

**How it works:**
- `Client` uses `httpx.HTTPTransport` (sync, backed by `httpcore`).
- `AsyncClient` uses `httpx.AsyncHTTPTransport` (async, backed by `httpcore`).
- Both share: constructor parameters, request building (`build_request()` is
  sync on both), config merging, redirect logic, auth flows, event hooks.
- The transport layer is the divergence point — sync vs async I/O.

**Strengths:**
- Clean, idiomatic Python — `client.get()` vs `await async_client.get()`.
- No greenlet magic, no auto-generation.
- `isinstance` checks work: `AsyncClient` is not a `Client`.
- Supports anyio (asyncio + trio).

**Weaknesses:**
- Some code duplication between `Client` and `AsyncClient`.
- Two classes to maintain, test, and document.

**Relevance to us:** **This is the closest analog to our situation.** We have a
`Store` (like `Client`) wrapping a `Backend` (like `Transport`). An `AsyncStore`
wrapping an `AsyncBackend` follows the same pattern. Shared logic (path
validation, capability gating, logging) stays in common code or a base class.

**Sources:**
- [httpx Async Support](https://www.python-httpx.org/async/)
- [httpx API Reference](https://www.python-httpx.org/api/)
- [httpx GitHub](https://github.com/encode/httpx)

---

### 2.4 Azure SDK — Same class name in `.aio` sub-namespace

**Pattern:** Sync and async clients have the **same class name** but live in
different namespaces: `azure.storage.blob.BlobClient` (sync) vs
`azure.storage.blob.aio.BlobClient` (async).

**How it works:**
- Sync and async are separate implementations at the transport layer.
- Shared models (`BlobProperties`, etc.) are never duplicated.
- Async clients are async context managers (`async with`).
- Default async transport: `aiohttp` via `azure.core.pipeline.transport`.

**Strengths:**
- Consistent naming — same mental model.
- No wrapper overhead.
- Models, errors, and config types are shared across sync/async.

**Weaknesses:**
- Requires maintaining two transport implementations.
- Import path is slightly confusing (`BlobClient` exists in two places).

**Relevance to us:** The `.aio` namespace pattern is relevant — we could
potentially have `remote_store.aio.AsyncStore` or similar. But their model
(same class name) would be confusing in a single-package library. We should
use distinct names (`AsyncStore`, `AsyncBackend`).

**Sources:**
- [azure.storage.blob.aio](https://learn.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.aio.blobclient)
- [Python SDK Design Guidelines](https://azure.github.io/azure-sdk/python_design.html)

---

### 2.5 boto3 / aioboto3 / aiobotocore — Async wrapper with leaks

**Pattern:** aiobotocore patches botocore to replace blocking I/O with async.
aioboto3 wraps boto3's higher-level resource API on top of aiobotocore.

**How it works:**
- aiobotocore monkey-patches botocore's HTTP layer to use aiohttp.
- aioboto3 wraps boto3's resource/client creation in async context managers.
- Most boto3 methods become `await`able.

**Strengths:**
- Near-complete API coverage of boto3.
- Familiar API for boto3 users.

**Weaknesses:**
- **Event loop blocking:** SSL context creation, credential handling, and
  other code paths still block the event loop.
- Mandatory async context managers for client creation (breaks some patterns).
- aioboto3 is a wrapper, not truly async — inherits all botocore's sync
  assumptions.
- Lower throughput than purpose-built alternatives (obstore benchmarks).
- Tight version coupling with boto3/botocore releases.

**Relevance to us:** Demonstrates the **pitfalls of wrapping a sync library**.
The event loop blocking issues are exactly what we want to avoid. This pattern
is a cautionary tale — if we wrap sync backends, we must use `to_thread()`
for every call, not just patch the transport layer.

**Sources:**
- [aioboto3 GitHub](https://github.com/terricain/aioboto3)
- [aiobotocore event loop blocking issue](https://github.com/aio-libs/aiobotocore/issues/1023)
- [obstore alternatives comparison](https://developmentseed.org/obstore/latest/alternatives/)

---

### 2.6 aiofiles — Thread-pool wrapper with file-like API

**Pattern:** Wraps stdlib file objects using `asyncio.to_thread()` / thread
pool, exposing an async file-like interface.

**How it works:**
- `async with aiofiles.open('f.txt') as f:` returns an async wrapper.
- `await f.read()` delegates to `loop.run_in_executor(None, f.read)`.
- Not true async I/O — uses threads under the hood.

**Strengths:**
- Clean async API for file operations.
- Drop-in replacement for `open()` in async code.

**Weaknesses:**
- **Not truly async** — all I/O goes through the default thread pool.
- Thread pool overhead (context switch per operation).
- No advantage over `asyncio.to_thread(sync_fn)` for one-shot operations.

**Relevance to us:** Shows that `asyncio.to_thread()` wrapping is acceptable
for local filesystem I/O. Our `LocalBackend` and `MemoryBackend` would use
exactly this pattern — there's no native async alternative for `pathlib`.

**Sources:**
- [aiofiles PyPI](https://pypi.org/project/aiofiles/)
- [aiofiles GitHub](https://github.com/Tinche/aiofiles)

---

### 2.7 asyncssh — Native async SFTP

**Pattern:** Ground-up async implementation of SSH/SFTP using asyncio.

**How it works:**
- All I/O is natively async — socket reads/writes use `asyncio` transport.
- SFTP operations: `await sftp.open()`, `await sftp.listdir()`, etc.
- Internal parallelization: SFTP reads/writes allow up to 128 outstanding
  request slots (`_MAX_SFTP_REQUESTS = 128`, default block size 32KB).

**Performance vs paramiko:**
- **Multi-host concurrency:** asyncssh is 15x+ faster than paramiko (async
  vs threading for concurrent SSH connections).
- **Single large file SFTP:** paramiko may be ~2x faster (~23 MB/s vs ~11
  MB/s reported), likely due to lower per-packet overhead.

**Licensing concern:** AsyncSSH uses the **Eclipse Public License v2.0**,
which is incompatible with GPL and has different terms from BSD/MIT. Our
project is MIT-licensed. EPL v2.0 is a weak copyleft — it allows combining
with other code in a "larger work" without affecting the other code's
license, but EPL-covered modifications must remain EPL. This should be fine
for an optional dependency (we don't modify asyncssh), but deserves a note
in the dependency docs. Same pattern as our existing optional deps.

**Relevance to us:** If we build an `AsyncSFTPBackend`, asyncssh is the leading
candidate. It's production-quality, well-maintained, and truly async. The
single-file throughput regression is acceptable for an API designed for
async frameworks where concurrency matters more than single-stream speed.
The licensing is fine for an optional dependency.

**Sources:**
- [AsyncSSH docs](https://asyncssh.readthedocs.io/)
- [AsyncSSH vs Paramiko comparison](https://elegantnetwork.github.io/posts/comparing-ssh/)
- [AsyncSSH SFTP speed discussion](https://github.com/ronf/asyncssh/issues/374)

---

### 2.8 httpcore / unasync — Code generation (write async, generate sync)

**Pattern:** Write all code as async in an `_async/` directory. A script
mechanically transforms `async def` → `def`, `await expr()` → `expr()`,
`async with` → `with`, and renames classes (`AsyncConnectionPool` →
`SyncConnectionPool`). The generated sync code lives in `_sync/`.

**How it works:**
- httpcore maintains `scripts/unasync.py` with regex-based substitutions.
- A `SUBS` list maps async identifiers to sync equivalents.
- Runs as a pre-commit hook — the `_sync/` directory is committed but
  never hand-edited.

**Libraries using this:** httpcore (httpx's transport layer), Elasticsearch
Python client.

**Strengths:**
- True zero-duplication. Sync and async guaranteed in lockstep.
- Clean separation in filesystem (`_async/` vs `_sync/`).
- No runtime magic.

**Weaknesses:**
- Requires build tooling / pre-commit scripts.
- Debugging sync variant traces to generated code.
- Cannot handle cases where sync and async genuinely differ (e.g., sync
  uses `urllib3`, async uses `aiohttp`).

**Relevance to us:** Interesting but poor fit. Our backends use **different
libraries** for sync vs async (paramiko vs asyncssh, boto3's sync s3fs vs
s3fs async internals, Azure sync vs Azure aio). Mechanical token replacement
can't bridge that gap. The httpcore model works because sync and async
transports use the same logic — ours don't.

**Sources:**
- [httpcore unasync.py](https://github.com/encode/httpcore/blob/master/scripts/unasync.py)
- [python-trio/unasync](https://github.com/python-trio/unasync)

---

### 2.9 libcloud — Abandoned async RFC (cautionary tale)

**Pattern:** Proposed in 2017, never shipped. Three designs evaluated.

libcloud's 2017 RFC proposed three approaches:
1. **AsyncSession wrapper** — wrap sync driver in `async with AsyncSession(driver)`.
2. **Async mixins** — `StorageAsyncDriver` with `_async`-suffixed methods.
3. **`async=True` flag** — constructor flag patches Connection with AsyncConnection.

**Why it failed:** The deep call tree (methods like `list_nodes` make network
calls at leaf nodes) made async conversion essentially a full rewrite. The
sans-I/O approach was deemed too invasive. Writing async-first with sync
wrappers was rejected because it required a library-managed event loop.

**Relevance to us:** Our Backend ABC is **flat** — each method is a single
delegation to the underlying SDK, not a deep call tree. This is why the
hybrid approach works for us where it failed for libcloud. The lesson: keep
the async boundary at the Backend level, not deep in the internals.

**Sources:**
- [Libcloud async RFC](https://libcloud.apache.org/blog/2017/04/09/async-rfc.html)
- [PR #1016 discussion](https://github.com/apache/libcloud/pull/1016)

---

### 2.10 fsspec ecosystem note: `open()` is not async

A critical limitation across all fsspec-based libraries (gcsfs, adlfs, sshfs):
**`open()` does not support async.** The recommendation is to download to a
temp file first, then read. This reinforces our design decision to use
`AsyncIterator[bytes]` for streaming reads rather than trying to create an
async file-like object.

---

### 2.11 anyio — Backend-agnostic async abstraction

**Pattern:** A compatibility layer that lets async code run on asyncio or trio.

**How it works:**
- Provides `anyio.sleep()`, `anyio.create_task_group()`, `anyio.connect_tcp()`,
  etc. — all backend-agnostic.
- Use `anyio.run(main, backend='asyncio')` or `anyio.run(main, backend='trio')`.
- ~2µs dispatch overhead — negligible for I/O-bound work.

**Who uses it:** Prefect, Starlette, httpx (hard dependency), encode/databases.

**Relevance to us:** DESIGN.md says "No dependency on anyio / asyncio / trio."
However, our primary audience (FastAPI, Starlette, httpx users) already has
anyio installed transitively — the marginal dependency cost is zero:
- FastAPI → Starlette → anyio (hard dep, >=3.6.2)
- httpx → anyio (hard dep)
- Prefect → anyio (hard dep)
- Litestar → anyio (hard dep)

The real reason to target `asyncio` only in Phase 1 is simplicity: fewer
abstractions, easier debugging, and Python 3.11+'s `asyncio.TaskGroup` covers
the structured concurrency gap for batch operations. anyio becomes relevant
in Phase 3 if we need to support trio or Python <3.11 with structured task
groups.

**Recommendation:** Target `asyncio` only initially. The rationale is simplicity
(not dependency cost), since our async users already have anyio. anyio can be
considered later if trio demand materializes or if we need structured concurrency
on Python <3.11.

**Sources:**
- [anyio docs](https://anyio.readthedocs.io/en/stable/basics.html)
- [anyio architecture](https://deepwiki.com/agronholm/anyio)
- [Prefect + anyio](https://www.prefect.io/blog/oss-love-letters-how-anyio-powers-prefects-async-architecture)

---

### 2.12 redis-py — Merged async into main package

**Pattern:** Sync `redis.Redis` and async `redis.asyncio.Redis` in the same
package. Merged from the standalone `aioredis` project (v4.2+).

**How it works:**
- `redis.Redis` is sync (uses `socket`).
- `redis.asyncio.Redis` is async (uses `asyncio` streams).
- Both share connection pool infrastructure and the same command API surface.
- Async cleanup uses `await client.aclose()` — the `aclose()` convention.

**Relevance to us:** Validates the `.aio` / sub-namespace pattern for shipping
sync and async in one package. The `aclose()` convention matches our proposed
naming (§5.3). The merged-aioredis history shows that maintaining a standalone
async wrapper eventually becomes untenable — better to ship both in one package.

**Sources:**
- [redis-py asyncio docs](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html)
- [aioredis merger FAQ](https://redis.io/faq/doc/26366kjrif/what-is-the-difference-between-aioredis-v2-0-and-redis-py-asyncio)

---

### 2.13 Django — Incremental async migration (cautionary tale)

**Pattern:** Multi-year incremental migration. Django 3.1: async views. Django
4.1: async ORM queries. Django 5.2: async auth. Still ongoing.

**How it works:**
- Uses `asgiref`'s `sync_to_async` / `async_to_sync` bridges — essentially
  our `SyncBackendAdapter` pattern.
- Async views run in the ASGI event loop; sync ORM calls are bridged via
  `sync_to_async(thread_sensitive=True)`.
- Django maintainers acknowledged that making the ORM core fully async may
  never be feasible — maintaining two parallel ORM cores is too costly.

**Relevance to us:** Directly informs §7 risk assessment ("Doubling maintenance
surface"). Django's experience shows the hybrid approach has real long-term
costs, but also that the `sync_to_async` bridge is battle-tested and production-
viable as a permanent solution for sync internals. Our flat Backend ABC is far
simpler than Django's ORM, making the maintenance burden more manageable.

**Sources:**
- [Django async support](https://docs.djangoproject.com/en/6.0/topics/async/)
- [Django async ORM discussion](https://www.loopwerk.io/articles/2025/async-django-why/)

---

### 2.14 Motor → PyMongo Async — Thread-pool wrapper deprecated in favor of native async

**Pattern:** Motor wrapped PyMongo via thread pool — literally our
`SyncBackendAdapter` pattern. Deprecated May 2025 in favor of PyMongo Async,
which builds native asyncio directly into PyMongo.

**How it works:**
- Motor delegated every PyMongo call through `asyncio.to_thread()` (originally
  `loop.run_in_executor()`).
- PyMongo Async (PyMongo 4.x) ships native async support in the same package,
  rendering Motor unnecessary.

**Relevance to us:** Empirical evidence for our recommended Phase 1 → Phase 2
trajectory. Motor proved that thread-pool wrapping works as a production bridge
but has performance costs that eventually justify native async. Validates the
phased approach: ship `SyncBackendAdapter` now, add native async backends later.

**Sources:**
- [Motor deprecation](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)
- [Motor docs](https://motor.readthedocs.io/)

---

### 2.15 Summary Table

| Library | Pattern | Native Async? | Sync/Async Bridge | Runtime Dep Added |
|---------|---------|---------------|-------------------|-------------------|
| **fsspec** | Async-first, auto-gen sync | Yes (HTTP, S3) | Dedicated IO thread + `sync_wrapper` | None (stdlib asyncio) |
| **SQLAlchemy** | Sync core, greenlet async facade | Partial (driver-level) | greenlet switching | greenlet (C ext) |
| **httpx** | Dual classes, shared internals | Yes (httpcore) | None (separate impls) | None |
| **Azure SDK** | Same name in `.aio` namespace | Yes (aiohttp transport) | None (separate impls) | aiohttp |
| **aioboto3** | Wrapper around sync boto3 | Partial (transport only) | Monkey-patch + async CM | aiohttp |
| **aiofiles** | Thread-pool wrapper | No (threads only) | `run_in_executor` | None |
| **asyncssh** | Ground-up async SSH | Yes | None | None |
| **redis-py** | Merged async into main package | Yes (asyncio streams) | None (separate impls) | None |
| **Django** | Incremental async migration | Partial (views, ORM) | `asgiref` `sync_to_async` | asgiref |
| **Motor → PyMongo** | Thread-pool wrapper → native | Motor: No; PyMongo Async: Yes | Motor: `to_thread`; PyMongo: native | None |
| **anyio** | Backend-agnostic abstraction | Yes (asyncio/trio) | None | anyio |

---

## 3. Async Landscape for Our Dependencies

### 3.1 S3 (currently: s3fs / boto3)

| Option | Type | Notes |
|--------|------|-------|
| **s3fs (already used)** | Native async under the hood | fsspec's `AsyncFileSystem` — has `_cat_file`, `_put`, `_ls` etc. |
| **aioboto3 / aiobotocore** | Wrapper | Known event loop blocking issues. Not recommended. |
| **obstore** | Native async (Rust via PyO3) | Very fast. New project, uses `object_store` Rust crate. |
| **asyncio.to_thread(s3fs)** | Thread wrapper | Simple, safe, no new deps. Loses potential async throughput. |

**Recommendation for async S3:** Use s3fs's native async methods directly
(since we already depend on s3fs), wrapped in our own `AsyncS3Backend`. The
async methods are the *real* implementation in s3fs — the sync versions are
generated from them. This gives us true async S3 I/O with zero new dependencies.

### 3.2 SFTP (currently: paramiko)

| Option | Type | Notes |
|--------|------|-------|
| **asyncssh** | Native async | Production-quality, well-maintained. ~2x slower for single large file SFTP. |
| **asyncio.to_thread(paramiko)** | Thread wrapper | Simple, uses existing dep. No new dep. |
| **sshfs (fsspec)** | fsspec async wrapper | Uses paramiko or asyncssh under the hood. |

**Recommendation for async SFTP:** Support both approaches — `asyncio.to_thread`
wrapper for `SFTPBackend` (zero new deps, good enough for many use cases), and
a dedicated `AsyncSFTPBackend` using asyncssh as an optional new dependency for
users who need native async SFTP.

### 3.3 Azure (currently: azure-storage-file-datalake)

| Option | Type | Notes |
|--------|------|-------|
| **azure-storage-file-datalake aio** | Native async | Same package, `.aio` sub-module. Already installed. |
| **asyncio.to_thread(current)** | Thread wrapper | Simple, but wastes native async capability. |

**Recommendation for async Azure:** Use the native `aio` variants from the
same Azure SDK packages we already depend on. Zero new dependencies — the async
classes ship in the same packages (`azure-storage-file-datalake`,
`azure-storage-blob`). This gives true async I/O.

### 3.4 Local filesystem (currently: stdlib pathlib)

| Option | Type | Notes |
|--------|------|-------|
| **asyncio.to_thread** | Thread wrapper | Only viable option for pathlib/shutil. |
| **aiofiles** | Thread wrapper (nicer API) | Would add a dependency for no real benefit. |
| **aiofile (libaio)** | True async (Linux only) | Not cross-platform, niche. |

**Recommendation for async Local:** `asyncio.to_thread()` wrapping the existing
`LocalBackend`. Local filesystem I/O is fast enough that thread-pool overhead is
negligible. No new dependencies needed.

### 3.5 Memory (currently: stdlib dict + threading.Lock)

| Option | Type | Notes |
|--------|------|-------|
| **asyncio.to_thread** | Thread wrapper | Overkill — memory ops are microseconds. |
| **Direct implementation** | Native async | Just make methods `async def` — no real I/O. |

**Recommendation for async Memory:** Direct `async def` implementation. Memory
operations are trivially fast — no I/O, no reason to use a thread pool. Replace
`threading.Lock` with `asyncio.Lock` for async-safety.

---

## 4. Design Options Analysis

### Option A: `asyncio.to_thread()` wrapper only (AsyncStore wrapping sync Backend)

```python
class AsyncStore:
    def __init__(self, backend: Backend, root_path: str = ""):
        self._sync_store = Store(backend, root_path)

    async def read_bytes(self, path: str) -> bytes:
        return await asyncio.to_thread(self._sync_store.read_bytes, path)

    async def write(self, path: str, content: bytes, *, overwrite: bool = False) -> None:
        await asyncio.to_thread(self._sync_store.write, path, content, overwrite=overwrite)
```

**Pros:**
- Simplest to implement — thin wrapper over existing code.
- Zero new dependencies.
- Works with all existing backends immediately.
- Easy to maintain — Backend ABC unchanged.

**Cons:**
- **No true async I/O.** Every call goes through the default thread pool.
  With 1,000 concurrent requests, you hit the thread pool limit (usually 40
  threads in the default executor). This defeats the purpose of async.
- Network backends (S3, Azure, SFTP) have native async options that would
  provide dramatically better throughput.
- `read()` returns `BinaryIO` which is sync — no async streaming possible.
- `list_files()` yields `Iterator[FileInfo]` which is sync — no `async for`.
- Basically "cosmetic async" — what Django's approach was described as.

**Verdict:** Acceptable as a **Phase 1** to unblock async users quickly, but
insufficient as a long-term solution. Must be followed by native async backends.

---

### Option B: Full parallel hierarchy (AsyncBackend ABC + AsyncStore)

```python
class AsyncBackend(abc.ABC):
    @abc.abstractmethod
    async def read_bytes(self, path: str) -> bytes: ...

    @abc.abstractmethod
    async def write(self, path: str, content: bytes, *, overwrite: bool = False) -> None: ...

    @abc.abstractmethod
    async def list_files(self, path: str, *, recursive: bool = False) -> AsyncIterator[FileInfo]: ...

class AsyncStore:
    def __init__(self, backend: AsyncBackend, root_path: str = ""): ...

    async def read_bytes(self, path: str) -> bytes: ...
    async def write(self, path: str, content: bytes, *, overwrite: bool = False) -> None: ...
    async def list_files(self, path: str, ...) -> AsyncIterator[FileInfo]: ...
```

**Pros:**
- Fully idiomatic async Python.
- Each backend can use native async I/O (s3fs async, azure aio, asyncssh).
- Proper `AsyncIterator` for listing — works with `async for`.
- Clean type checking — mypy sees the full async contract.
- Follows the httpx pattern (separate sync/async classes, shared config).

**Cons:**
- Doubles the abstraction surface — Backend + AsyncBackend, Store + AsyncStore.
- Every backend needs an async variant (or an adapter).
- Extension modules need async variants.
- More testing surface.

**Verdict:** The right long-term architecture, but substantial effort.

---

### Option C: Hybrid — AsyncBackend ABC with sync-backend adapter

```python
class AsyncBackend(abc.ABC):
    """Abstract base class for async storage backends."""
    @abc.abstractmethod
    async def read_bytes(self, path: str) -> bytes: ...
    # ... all methods async ...

class SyncBackendAdapter(AsyncBackend):
    """Wraps any sync Backend into an AsyncBackend via asyncio.to_thread."""
    def __init__(self, backend: Backend):
        self._sync = backend

    async def read_bytes(self, path: str) -> bytes:
        return await asyncio.to_thread(self._sync.read_bytes, path)

    async def list_files(self, path: str, *, recursive: bool = False) -> AsyncIterator[FileInfo]:
        # Runs sync iterator in thread, yields results
        items = await asyncio.to_thread(lambda: list(self._sync.list_files(path, recursive=recursive)))
        for item in items:
            yield item

class AsyncStore:
    def __init__(self, backend: AsyncBackend | Backend, root_path: str = ""):
        if isinstance(backend, Backend) and not isinstance(backend, AsyncBackend):
            backend = SyncBackendAdapter(backend)
        self._backend: AsyncBackend = backend
```

**Pros:**
- AsyncStore works with **both** sync and async backends immediately.
- Sync backends get wrapped automatically — zero effort for users.
- Native async backends bypass the thread pool for better performance.
- Gradual migration path: start with wrapped sync, add native async later.
- Follows the httpx transport pattern (sync and async transports, single client).

**Cons:**
- `SyncBackendAdapter` for `list_files` must materialize the iterator in
  the thread (can't yield across thread boundary), increasing memory usage
  for large listings.
- The `isinstance` check in `__init__` adds a bit of magic.
- Still need to implement `AsyncBackend` for native async variants.

**Verdict:** **Best balance of pragmatism and architecture.** Users get async
immediately with existing backends, and native async backends are the
performance upgrade path.

---

### Option D: Greenlet bridge (SQLAlchemy-style)

**Not recommended.** Our codebase is ~10K LOC, not 600K. The complexity of
greenlet switching, the C extension dependency, and the debugging difficulty
are not justified. Our backends are simple I/O delegations, not deep ORM
graphs. Dismissed.

---

### Option E: Async-first with sync wrapper (fsspec-style)

**Not recommended.** This would require rewriting all existing backends as
async-first and auto-generating sync versions. Massive breaking change to the
internal architecture with no user-facing benefit (sync API already works).
The dedicated IO thread + `sync_wrapper` machinery adds debugging complexity.
Dismissed.

---

## 5. Recommended Design: Option C (Hybrid)

### 5.1 Architecture

```
User → AsyncStore → AsyncBackend (ABC) → AsyncS3Backend (native s3fs async)
                                       → AsyncAzureBackend (native aio SDK)
                                       → AsyncSFTPBackend (asyncssh)
                                       → SyncBackendAdapter(LocalBackend)  ← auto-wrapped
                                       → SyncBackendAdapter(MemoryBackend) ← auto-wrapped
                                       → AsyncMemoryBackend (optional, direct async)

User → Store → Backend (ABC) → [unchanged, existing code]
```

### 5.2 New abstractions

| New Type | Module | Description |
|----------|--------|-------------|
| `AsyncBackend` | `_async_backend.py` | Abstract base class with `async def` methods |
| `AsyncStore` | `_async_store.py` | User-facing async Store, delegates to `AsyncBackend` |
| `SyncBackendAdapter` | `_async_backend.py` | Wraps any sync `Backend` → `AsyncBackend` |
| `AsyncRegistry` | `_async_registry.py` | Optional async-aware registry with `aclose()` |

### 5.3 Method mapping (Backend → AsyncBackend)

| Sync (Backend) | Async (AsyncBackend) | Return type change |
|----------------|---------------------|--------------------|
| `exists(path) -> bool` | `async exists(path) -> bool` | None |
| `is_file(path) -> bool` | `async is_file(path) -> bool` | None |
| `is_folder(path) -> bool` | `async is_folder(path) -> bool` | None |
| `read(path) -> BinaryIO` | `async read(path) -> AsyncIterator[bytes]` | **Changed** — see §5.4 |
| `read_bytes(path) -> bytes` | `async read_bytes(path) -> bytes` | None |
| `write(path, content) -> None` | `async write(path, content) -> None` | `content: bytes \| AsyncIterator[bytes]` |
| `write_atomic(path, content)` | `async write_atomic(path, content)` | Same as write |
| `delete(path)` | `async delete(path)` | None |
| `delete_folder(path)` | `async delete_folder(path)` | None |
| `list_files(path) -> Iterator[FileInfo]` | `async list_files(path) -> AsyncIterator[FileInfo]` | **Changed** |
| `list_folders(path) -> Iterator[str]` | `async list_folders(path) -> AsyncIterator[str]` | **Changed** |
| `get_file_info(path) -> FileInfo` | `async get_file_info(path) -> FileInfo` | None |
| `get_folder_info(path) -> FolderInfo` | `async get_folder_info(path) -> FolderInfo` | None |
| `move(src, dst)` | `async move(src, dst)` | None |
| `copy(src, dst)` | `async copy(src, dst)` | None |
| `glob(pattern) -> Iterator[FileInfo]` | `async glob(pattern) -> AsyncIterator[FileInfo]` | **Changed** |
| `to_key(path) -> str` | `to_key(path) -> str` | **Stays sync** — no I/O |
| `close()` | `async aclose()` | Name changed to follow `aclose` convention |
| `unwrap(type) -> T` | `unwrap(type) -> T` | **Stays sync** — returns cached handle |
| `capabilities -> CapabilitySet` | `capabilities -> CapabilitySet` | **Stays sync** — property, no I/O |
| `name -> str` | `name -> str` | **Stays sync** — property, no I/O |

### 5.4 The streaming problem: `read()` and `BinaryIO`

The sync `read()` returns `BinaryIO` (a file-like object with `.read()`,
`.readline()`, `.seek()` etc.). There is no standard `AsyncBinaryIO` in Python.

**Options:**

**(a) Return `bytes` only:** Simplest, but loses streaming capability. Bad for
large files — entire file must fit in memory.

**(b) Return `AsyncIterator[bytes]`:** Async-friendly streaming. Each `yield`
is a chunk. Compatible with `async for chunk in stream:` patterns. Used by
aiohttp, httpx, and most async frameworks.

**(c) Define our own `AsyncReadStream` protocol:**
```python
class AsyncReadStream(Protocol):
    async def read(self, n: int = -1) -> bytes: ...
    async def aclose(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[bytes]: ...
    async def __anext__(self) -> bytes: ...
```

**Recommendation:** Use **(b) `AsyncIterator[bytes]`** for `read()` on
`AsyncBackend`. It's the most idiomatic pattern in async Python and avoids
defining a new protocol. Keep `read_bytes()` for the simple case (returns
`bytes`). This mirrors how httpx handles response streaming vs `response.text`.

The `SyncBackendAdapter` can convert a sync `BinaryIO` to an
`AsyncIterator[bytes]` by reading chunks in a thread:
```python
async def read(self, path: str) -> AsyncIterator[bytes]:
    stream = await asyncio.to_thread(self._sync.read, path)
    try:
        while True:
            chunk = await asyncio.to_thread(stream.read, 65536)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(stream.close)
```

### 5.5 Extension impact

| Extension | Async variant needed? | Approach |
|-----------|-----------------------|----------|
| `ext.batch` | Yes | `async_batch_delete()`, `async_batch_copy()`, `async_batch_exists()` — use `asyncio.TaskGroup` (3.11+) for structured concurrency with proper cancellation. Avoid `asyncio.gather()` — if one task fails, the others keep running (no structured cancellation). (Phase 3 decision: Python 3.10 lacks `asyncio.TaskGroup` — may require anyio or a Python >=3.11 floor bump for async batch ops. See §6 Q2.) |
| `ext.transfer` | Yes | `async_upload()`, `async_download()`, `async_transfer()` |
| `ext.observe` | Yes | `AsyncObservedStore(AsyncStore)` — same proxy pattern |
| `ext.arrow` | No | PyArrow FileSystemHandler is inherently sync (C++ layer) |
| `ext.glob` | Yes | `async_glob_files()` |
| `ext.otel` | Yes | `async_otel_observe()` wrapping `AsyncStore` |

### 5.6 Phased rollout

**Phase 1 — Core async surface (minimum viable):**
- `AsyncBackend` ABC
- `SyncBackendAdapter`
- `AsyncStore` with `__aenter__`/`__aexit__`
- `AsyncMemoryBackend` (for testing, zero deps)
- Spec, ADR, tests

**Phase 2 — Native async backends:**
- `AsyncS3Backend` (using s3fs native async)
- `AsyncAzureBackend` (using azure SDK aio)
- Optional: `AsyncSFTPBackend` (using asyncssh, new optional dep)

**Phase 3 — Async extensions:**
- `ext.async_batch` (or async variants in `ext.batch`)
- `ext.async_transfer`
- `AsyncObservedStore`

### 5.7 Naming and public API

```python
# New public API surface (Phase 1):
from remote_store import AsyncStore, AsyncBackend, SyncBackendAdapter

# Usage — existing sync backend in async context:
from remote_store.backends import LocalBackend

async def main():
    backend = LocalBackend(root="/data")
    async with AsyncStore(backend, root_path="reports") as store:
        data = await store.read_bytes("summary.csv")
        await store.write("output.csv", data, overwrite=True)
        async for info in store.list_files("", recursive=True):
            print(info.name)

# Usage — native async backend:
from remote_store.backends import AsyncS3Backend  # Phase 2

async def main():
    backend = AsyncS3Backend(bucket="my-bucket", region_name="us-east-1")
    async with AsyncStore(backend) as store:
        await store.write("key.txt", b"hello")
```

### 5.8 What stays sync (no async needed)

- `RemotePath` — pure validation, no I/O
- `Capability` / `CapabilitySet` — enum + set, no I/O
- `FileInfo` / `FolderInfo` — dataclasses, no I/O
- `BackendConfig` / `StoreProfile` / `RegistryConfig` — config objects
- All error types — `RemoteStoreError` hierarchy
- `to_key()` — string manipulation
- `unwrap()` — returns cached native handle
- `name` / `capabilities` — properties

---

## 6. Open Questions for ADR/RFC

1. **Should `AsyncStore` accept both `Backend` and `AsyncBackend`?**
   Recommendation: Yes, with auto-wrapping via `SyncBackendAdapter`. This
   maximizes convenience — users don't need to know about the adapter.

2. **Should we use `anyio` or stick to `asyncio`?**
   Recommendation: `asyncio` only for now. The rationale is simplicity (fewer
   abstractions, easier debugging), not dependency cost — our primary async
   audience (FastAPI, Starlette, httpx users) already has anyio installed
   transitively (see §2.11). trio demand for storage libraries is near-zero.
   Can be added later without breaking changes.

3. **Should async backends live in the same module as sync backends?**
   Recommendation: Separate modules — `backends/_async_s3.py` alongside
   `backends/_s3.py`. Keeps imports clean and allows optional dependency
   gating per async backend.

4. **Should `read()` return `AsyncIterator[bytes]` or a custom protocol?**
   Recommendation: `AsyncIterator[bytes]`. Standard, no new types, works with
   `async for`. Add `read_bytes()` for the simple case.

5. **Should `aclose()` be the name, or `close()`?**
   Recommendation: `aclose()` — follows Python convention (`aclose` on async
   generators, `aclose` on `asyncio.StreamWriter`, etc.). The `__aexit__` dunder
   calls `aclose()`.

6. **Should `SyncBackendAdapter.list_files()` materialize or stream?**
   Recommendation: Materialize in thread (collect to list, then yield). True
   async streaming across a thread boundary is complex and the listing is
   typically small. Add a `chunk_size` parameter if memory becomes an issue for
   very large listings.

7. **Should Phase 1 add any new optional dependencies?**
   Recommendation: No. Phase 1 uses only stdlib `asyncio`. New deps (asyncssh)
   come in Phase 2.

8. **Where does this live in the package?**
   Recommendation: Core async types in `src/remote_store/` (same level as
   `_store.py`, `_backend.py`). Async backends in `src/remote_store/backends/`.
   Async extensions in `src/remote_store/ext/`.

---

## 7. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Doubling maintenance surface** | Medium | Drift-protection tests (like OBS-007) ensure AsyncStore mirrors Store methods. Shared path validation and error model reduce duplication. |
| **Breaking the zero-dep core** | High | Phase 1 uses only stdlib `asyncio` (no new deps). Optional async deps (asyncssh) are extras in Phase 2. |
| **`SyncBackendAdapter` performance** | Low | Thread pool is fine for moderate concurrency. Native async backends (Phase 2) are the performance path. |
| **Iterator materialization in adapter** | Medium | Only affects wrapped sync backends doing large listings. Native async backends stream properly. Document the limitation. |
| **API surface confusion** | Medium | Clear naming: `Store` (sync), `AsyncStore` (async). No shared base class — they're separate types for separate use cases. |
| **Extension ecosystem fragmentation** | Medium | Async extensions follow same ADR-0008 rules. Pure Python extensions (batch, transfer) can offer both sync and async variants in the same module. |

---

## 8. References

### Python ecosystem
- [fsspec Async docs](https://filesystem-spec.readthedocs.io/en/latest/async.html)
- [SQLAlchemy asyncio docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [httpx Async Support](https://www.python-httpx.org/async/)
- [Azure SDK Python Design Guidelines](https://azure.github.io/azure-sdk/python_design.html)
- [aioboto3 GitHub](https://github.com/terricain/aioboto3)
- [aiobotocore event loop blocking](https://github.com/aio-libs/aiobotocore/issues/1023)
- [aiofiles PyPI](https://pypi.org/project/aiofiles/)
- [AsyncSSH docs](https://asyncssh.readthedocs.io/)
- [anyio docs](https://anyio.readthedocs.io/en/stable/basics.html)

### Internal
- DESIGN.md §7.3, §8, §9
- ADR-0001 (architecture)
- ADR-0003 (fsspec is implementation detail)
- ADR-0008 (extension architecture)
- ADR-0010 (observe proxy pattern)
