# Async API

The `remote_store.aio` module provides native `async`/`await` support
for store operations. See [Store](store.md) for the synchronous
counterpart. Phase 1 covers the core primitives; native async backends
(S3, Azure) are planned for Phase 2.

---

## AsyncStore

::: remote_store.aio.AsyncStore
    options:
      members: false

---

## AsyncBackend

::: remote_store.aio.AsyncBackend

---

## SyncBackendAdapter

::: remote_store.aio.SyncBackendAdapter
    options:
      members: false

---

## AsyncMemoryBackend

::: remote_store.aio.AsyncMemoryBackend
    options:
      members: false

---

## AsyncWritableContent

::: remote_store.aio.AsyncWritableContent

---

## See also

- [Async Store Guide](../async.md) -- usage patterns, streaming, FastAPI integration
- [Example: Async Store](../examples/async-store.md) -- runnable demo script
- [Store](store.md) -- synchronous counterpart
- [Concurrency](../concurrency.md) -- thread safety and atomicity semantics
