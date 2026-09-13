# Async backends

API reference for the native async storage backend classes in `remote_store.aio.backends`. Each implements the [`AsyncBackend`](https://docs.remotestore.dev/stable/reference/api/aio/backend/index.md) protocol and runs on the event loop without a thread-pool bridge.

| Class                                                                                                | Description                                                 |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| [AsyncMemoryBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/memory/index.md) | In-memory async backend for testing                         |
| [AsyncAzureBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/azure/index.md)   | Native async Azure Blob Storage and ADLS Gen2               |
| [GraphBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/index.md)        | Microsoft Graph backend (OneDrive, SharePoint, Teams files) |

Sync backends run under `AsyncStore` too

A native async backend is only needed when you want true non-blocking I/O. Any synchronous [backend](https://docs.remotestore.dev/stable/reference/api/backends/index.md) works under [`AsyncStore`](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md) via the thread-pool [`SyncBackendAdapter`](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md), which `AsyncStore` applies automatically.

## See also

- [Backends](https://docs.remotestore.dev/stable/reference/api/backends/index.md) — the synchronous backend classes
- [Async Store Guide](https://docs.remotestore.dev/stable/guides/async/index.md) — usage patterns
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — per-backend capability comparison
