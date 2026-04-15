# Async/Sync Bridge Adapters

`remote-store` ships two adapter classes that bridge the gap between
synchronous and asynchronous code.  Both are in the `remote_store` package;
choose the one that matches the direction you need.

## Decision table

| Question | `SyncBackendAdapter` | `AsyncBackendSyncAdapter` |
|---|---|---|
| **Direction** | Sync backend → usable from async code | Async backend → usable from sync code |
| **You have…** | A `Backend` (sync) | An `AsyncBackend` (async-native) |
| **You need to call it from…** | `async` functions / `AsyncStore` | Ordinary sync functions / `Store` |
| **Typical consumer** | `AsyncStore` wrapping a local or SFTP backend | Sync code (or a `Store`) driving `AsyncAzureBackend` |

## `SyncBackendAdapter` — sync → async

```python
--8<-- "examples/snippets/async_sync_bridges.py:sync-to-async"
```

Use this when you have an existing sync backend and want to drive it from
async code without rewriting it.

## `AsyncBackendSyncAdapter` — async → sync

```python
--8<-- "examples/snippets/async_sync_bridges.py:async-to-sync"
```

Use this when you have an async-native backend (e.g. `AsyncAzureBackend`)
but your calling code is synchronous.

**Constraints to keep in mind:**

- Cannot be called from a running event loop — use `AsyncStore` instead.
- `read()` returns a forward-only stream (`seekable()` is `False`).
- `close(timeout=…)` drains in-flight work before stopping the private loop;
  always call it (or use the context manager) to avoid daemon-thread leaks.

## See also

- [API reference](api/aio.md) — `AsyncBackendSyncAdapter`, `SyncBackendAdapter`, `AsyncStore`
- [Async guide](async.md) — `AsyncStore`, native async backends, and the
  `SyncBackendAdapter` direction
- [ADR-0025](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0025-async-to-sync-backend-adapter.md)
  — decision record for `AsyncBackendSyncAdapter`
- [spec 029 § AsyncBackendSyncAdapter](https://github.com/haalfi/remote-store/blob/master/sdd/specs/029-async-store-backend-api.md)
  — full invariant list (ASYNC-080…093)
