# Async API

The `remote_store.aio` namespace is the async counterpart of the core API. Its layout mirrors the [synchronous reference](https://docs.remotestore.dev/stable/reference/api/index.md): a Store, a Backend protocol, backend implementations, and extensions — each the async twin of its sync sibling, plus the adapters that bridge the two worlds.

For usage patterns (streaming, FastAPI integration, the thread-pool bridge), see the [Async Store Guide](https://docs.remotestore.dev/stable/guides/async/index.md).

## Sync ↔ async map

| Synchronous (`remote_store`)                                                                  | Asynchronous (`remote_store.aio`)                                                                            |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [`Store`](https://docs.remotestore.dev/stable/reference/api/store/index.md)                   | [`AsyncStore`](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md)                         |
| [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md)               | [`AsyncBackend`](https://docs.remotestore.dev/stable/reference/api/aio/backend/index.md)                     |
| [`MemoryBackend`](https://docs.remotestore.dev/stable/reference/api/backends/memory/index.md) | [`AsyncMemoryBackend`](https://docs.remotestore.dev/stable/reference/api/aio/backends/memory/index.md)       |
| [`AzureBackend`](https://docs.remotestore.dev/stable/reference/api/backends/azure/index.md)   | [`AsyncAzureBackend`](https://docs.remotestore.dev/stable/reference/api/aio/backends/azure/index.md)         |
| —                                                                                             | [`GraphBackend`](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/index.md) (async-only) |
| [`ext.write`](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md)    | [`aio.ext.write`](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md)           |

## Core

| Class                                                                                  | Description                                                            |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| [AsyncStore](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md)     | Async counterpart to `Store` with coroutine methods for all operations |
| [AsyncBackend](https://docs.remotestore.dev/stable/reference/api/aio/backend/index.md) | Abstract base class for native async backends                          |

## Backends

| Class                                                                                                | Description                                                 |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| [AsyncMemoryBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/memory/index.md) | In-memory async backend for testing                         |
| [AsyncAzureBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/azure/index.md)   | Native async Azure Blob Storage and ADLS Gen2               |
| [GraphBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/index.md)        | Microsoft Graph backend (OneDrive, SharePoint, Teams files) |

Graph is async-only

`GraphBackend` has no synchronous twin. It appears here, not in the [synchronous Backends](https://docs.remotestore.dev/stable/reference/api/backends/index.md) section. To drive it from sync code, wrap it with [`AsyncBackendSyncAdapter`](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md).

## Adapters & types

| Symbol                                                                                                             | Description                                                                  |
| ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| [SyncBackendAdapter](https://docs.remotestore.dev/stable/reference/api/aio/adapters/#syncbackendadapter)           | Wraps any synchronous backend for async use via thread-pool executor         |
| [AsyncBackendSyncAdapter](https://docs.remotestore.dev/stable/reference/api/aio/adapters/#asyncbackendsyncadapter) | Wraps any `AsyncBackend` as a synchronous `Backend` via a private event loop |
| [AsyncWritableContent](https://docs.remotestore.dev/stable/reference/api/aio/adapters/#asyncwritablecontent)       | Type alias: `bytes` or `AsyncIterator[bytes]`                                |

## Utilities

| Symbol                                                                                         | Description                                                           |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| [GraphAuth](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/#graphauth)   | MSAL token provider (client-credentials / device-code) for Graph      |
| [GraphUtils](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/#graphutils) | Resolve a Graph `drive_id` from OneDrive / SharePoint / Teams targets |

## Extensions

| Module                                                                                           | Description                                                     |
| ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| [aio.ext.write](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md) | Async write helpers with guaranteed client-side content hashing |

## See also

- [API Reference](https://docs.remotestore.dev/stable/reference/api/index.md) — the full reference index
- [Async Store Guide](https://docs.remotestore.dev/stable/guides/async/index.md) — usage patterns, streaming, FastAPI integration
- [Async-sync bridges](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md) — adapter behaviour contract
- [Concurrency](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) — thread safety and atomicity semantics
