# Async API

The `remote_store.aio` namespace is the async counterpart of the core API.
Its layout mirrors the [synchronous reference](../index.md): a Store, a
Backend protocol, backend implementations, and extensions — each the async
twin of its sync sibling, plus the adapters that bridge the two worlds.

For usage patterns (streaming, FastAPI integration, the thread-pool bridge),
see the [Async Store Guide](../../../guides/async.md).

## Sync ↔ async map

| Synchronous (`remote_store`) | Asynchronous (`remote_store.aio`) |
|------------------------------|-----------------------------------|
| [`Store`](../store.md) | [`AsyncStore`](store.md) |
| [`Backend`](../backend.md) | [`AsyncBackend`](backend.md) |
| [`MemoryBackend`](../backends/memory.md) | [`AsyncMemoryBackend`](backends/memory.md) |
| [`AzureBackend`](../backends/azure.md) | [`AsyncAzureBackend`](backends/azure.md) |
| — | [`GraphBackend`](backends/graph.md) (async-only) |
| [`ext.write`](../extensions/write.md) | [`aio.ext.write`](extensions/write.md) |

## Core

| Class | Description |
|-------|-------------|
| [AsyncStore](store.md) | Async counterpart to `Store` with coroutine methods for all operations |
| [AsyncBackend](backend.md) | Abstract base class for native async backends |

## Backends

| Class | Description |
|-------|-------------|
| [AsyncMemoryBackend](backends/memory.md) | In-memory async backend for testing |
| [AsyncAzureBackend](backends/azure.md) | Native async Azure Blob Storage and ADLS Gen2 |
| [GraphBackend](backends/graph.md) | Microsoft Graph backend (OneDrive, SharePoint, Teams files) |

!!! info "Graph is async-only"
    `GraphBackend` has no synchronous twin. It appears here, not in the
    [synchronous Backends](../backends/index.md) section. To drive it from
    sync code, wrap it with [`AsyncBackendSyncAdapter`](adapters.md).

## Adapters & types

| Symbol | Description |
|--------|-------------|
| [SyncBackendAdapter](adapters.md#syncbackendadapter) | Wraps any synchronous backend for async use via thread-pool executor |
| [AsyncBackendSyncAdapter](adapters.md#asyncbackendsyncadapter) | Wraps any `AsyncBackend` as a synchronous `Backend` via a private event loop |
| [AsyncWritableContent](adapters.md#asyncwritablecontent) | Type alias: `bytes` or `AsyncIterator[bytes]` |

## Utilities

| Symbol | Description |
|--------|-------------|
| [GraphAuth](backends/graph.md#graphauth) | MSAL token provider (client-credentials / device-code) for Graph |
| [GraphUtils](backends/graph.md#graphutils) | Resolve a Graph `drive_id` from OneDrive / SharePoint / Teams targets |

## Extensions

| Module | Description |
|--------|-------------|
| [aio.ext.write](extensions/write.md) | Async write helpers with guaranteed client-side content hashing |

## See also

- [API Reference](../index.md) — the full reference index
- [Async Store Guide](../../../guides/async.md) — usage patterns, streaming, FastAPI integration
- [Async-sync bridges](../../../guides/async-sync-bridges.md) — adapter behaviour contract
- [Concurrency](../../../explanation/concurrency.md) — thread safety and atomicity semantics
