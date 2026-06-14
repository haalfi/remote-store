# Async backends

API reference for the native async storage backend classes in
`remote_store.aio.backends`. Each implements the
[`AsyncBackend`](../backend.md) protocol and runs on the event loop without a
thread-pool bridge.

| Class | Description |
|-------|-------------|
| [AsyncMemoryBackend](memory.md) | In-memory async backend for testing |
| [AsyncAzureBackend](azure.md) | Native async Azure Blob Storage and ADLS Gen2 |
| [GraphBackend](graph.md) | Microsoft Graph backend (OneDrive, SharePoint, Teams files) |

!!! info "Sync backends run under `AsyncStore` too"
    A native async backend is only needed when you want true non-blocking
    I/O. Any synchronous [backend](../../backends/index.md) works under
    [`AsyncStore`](../store.md) via the thread-pool
    [`SyncBackendAdapter`](../adapters.md), which `AsyncStore` applies
    automatically.

## See also

- [Backends](../../backends/index.md) — the synchronous backend classes
- [Async Store Guide](../../../../guides/async.md) — usage patterns
- [Capabilities Matrix](../../../capabilities-matrix.md) — per-backend capability comparison
