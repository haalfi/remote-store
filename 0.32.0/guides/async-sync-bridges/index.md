# Async/Sync Bridge Adapters

`remote-store` ships two adapter classes that bridge the gap between synchronous and asynchronous code. Both are in the `remote_store` package; choose the one that matches the direction you need.

## Decision table

| Question                      | `SyncBackendAdapter`                          | `AsyncBackendSyncAdapter`                            |
| ----------------------------- | --------------------------------------------- | ---------------------------------------------------- |
| **Direction**                 | Sync backend → usable from async code         | Async backend → usable from sync code                |
| **You have…**                 | A `Backend` (sync)                            | An `AsyncBackend` (async-native)                     |
| **You need to call it from…** | `async` functions / `AsyncStore`              | Ordinary sync functions / `Store`                    |
| **Typical consumer**          | `AsyncStore` wrapping a local or SFTP backend | Sync code (or a `Store`) driving `AsyncAzureBackend` |

## `SyncBackendAdapter` — sync → async

```
from remote_store.aio import AsyncStore, SyncBackendAdapter  # noqa: F811
from remote_store.backends import MemoryBackend  # noqa: F811

backend = MemoryBackend()
async_backend = SyncBackendAdapter(backend)

async with AsyncStore(async_backend) as store:
    await store.write("report.csv", b"col,val\n1,2")
    content = await store.read_bytes("report.csv")
```

Use this when you have an existing sync backend and want to drive it from async code without rewriting it.

## `AsyncBackendSyncAdapter` — async → sync

```
from remote_store import AsyncBackendSyncAdapter, Store  # noqa: F811
from remote_store.aio import AsyncMemoryBackend  # noqa: F811

async_backend = AsyncMemoryBackend()

with AsyncBackendSyncAdapter(async_backend) as adapter:
    store = Store(adapter)
    store.write("report.csv", b"col,val\n1,2")
    content = store.read_bytes("report.csv")
```

Use this when you have an async-native backend (e.g. `AsyncAzureBackend`) but your calling code is synchronous.

### Constraints to keep in mind

- Cannot be called from a running event loop — use `AsyncStore` instead.
- `read()` returns a forward-only stream (`seekable()` is `False`).
- `close(timeout=…)` drains in-flight work before stopping the private loop; always call it (or use the context manager) to avoid daemon-thread leaks.

## See also

- [API reference](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md) — `AsyncBackendSyncAdapter`, `SyncBackendAdapter`, `AsyncStore`
- [Async guide](https://docs.remotestore.dev/stable/guides/async/index.md) — `AsyncStore`, native async backends, and the `SyncBackendAdapter` direction
- [Async-to-sync adapter decision record](https://docs.remotestore.dev/stable/explanation/design/adrs/0025-async-to-sync-backend-adapter/index.md)
- [Async backend API spec](https://docs.remotestore.dev/stable/explanation/design/specs/029-async-store-backend-api/index.md) — `AsyncBackendSyncAdapter` invariants
