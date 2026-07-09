# API Reference

Complete reference for all public exports of `remote-store`.

Symbols below are grouped by role. The import path is `remote_store` unless a group says otherwise: storage backends live in `remote_store.backends`, extensions in `remote_store.ext`, and the entire async surface in `remote_store.aio` (see the [Async section](#async), whose layout mirrors this page).

Feeding this to a coding agent?

[`llms-api.txt`](https://docs.remotestore.dev/stable/llms-api.txt) carries this entire surface as one code-shaped skeleton — every signature, type annotation, and docstring (backends, async, and extensions included), with bodies elided — in a single file for an agent's context.

## Core

| Class                                                                           | Description                                      |
| ------------------------------------------------------------------------------- | ------------------------------------------------ |
| [Store](https://docs.remotestore.dev/stable/reference/api/store/index.md)       | Main entry point for all file operations         |
| [ProxyStore](https://docs.remotestore.dev/stable/reference/api/proxy/index.md)  | Base class for building Store middleware         |
| [Registry](https://docs.remotestore.dev/stable/reference/api/registry/index.md) | Creates and manages backend instances and stores |
| [Backend](https://docs.remotestore.dev/stable/reference/api/backend/index.md)   | Abstract base class for storage backends         |

## Backends

Synchronous storage backends (`remote_store.backends`). Native async backends — including the async-only Microsoft Graph backend — live under [Async › Backends](https://docs.remotestore.dev/stable/reference/api/aio/backends/index.md).

| Class                                                                                              | Description                                                  |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| [LocalBackend](https://docs.remotestore.dev/stable/reference/api/backends/local/index.md)          | Local filesystem storage                                     |
| [MemoryBackend](https://docs.remotestore.dev/stable/reference/api/backends/memory/index.md)        | In-process storage for testing                               |
| [ReadOnlyHttpBackend](https://docs.remotestore.dev/stable/reference/api/backends/http/index.md)    | Read-only access to HTTP/HTTPS URLs                          |
| [S3Backend](https://docs.remotestore.dev/stable/reference/api/backends/s3/index.md)                | Amazon S3 and S3-compatible services                         |
| [S3PyArrowBackend](https://docs.remotestore.dev/stable/reference/api/backends/s3-pyarrow/index.md) | S3 via PyArrow C++ for higher throughput                     |
| [SFTPBackend](https://docs.remotestore.dev/stable/reference/api/backends/sftp/index.md)            | SSH/SFTP server storage via paramiko                         |
| [AzureBackend](https://docs.remotestore.dev/stable/reference/api/backends/azure/index.md)          | Azure Blob Storage and ADLS Gen2                             |
| [SQLBlobBackend](https://docs.remotestore.dev/stable/reference/api/backends/sql-blob/index.md)     | SQL database blob storage via SQLAlchemy                     |
| [SQLQueryBackend](https://docs.remotestore.dev/stable/reference/api/backends/sql-query/index.md)   | Read-only SQL query materialization via SQLAlchemy + PyArrow |

## Async

The `remote_store.aio` namespace — the async counterpart of the core API, laid out to mirror this page. See the [async overview](https://docs.remotestore.dev/stable/reference/api/aio/index.md) for the full sync ↔ async map.

| Class                                                                                                              | Description                                                                  |
| ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| [AsyncStore](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md)                                 | Async counterpart to `Store` with coroutine methods for all operations       |
| [AsyncBackend](https://docs.remotestore.dev/stable/reference/api/aio/backend/index.md)                             | Abstract base class for native async backends                                |
| [SyncBackendAdapter](https://docs.remotestore.dev/stable/reference/api/aio/adapters/#syncbackendadapter)           | Wraps any synchronous backend for async use via thread-pool executor         |
| [AsyncBackendSyncAdapter](https://docs.remotestore.dev/stable/reference/api/aio/adapters/#asyncbackendsyncadapter) | Wraps any `AsyncBackend` as a synchronous `Backend` via a private event loop |
| [AsyncMemoryBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/memory/index.md)               | In-memory async backend for testing                                          |
| [AsyncAzureBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/azure/index.md)                 | Native async Azure Blob Storage and ADLS Gen2                                |
| [GraphBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/index.md)                      | Microsoft Graph backend (OneDrive, SharePoint, Teams files)                  |
| [AsyncWritableContent](https://docs.remotestore.dev/stable/reference/api/aio/adapters/#asyncwritablecontent)       | Type alias: `bytes` or `AsyncIterator[bytes]`                                |

## Utilities

| Class                                                                                          | Description                                                           |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| [SFTPUtils](https://docs.remotestore.dev/stable/reference/api/sftp-utils/index.md)             | Key loading and host-key verification helpers for SFTP                |
| [AzureUtils](https://docs.remotestore.dev/stable/reference/api/azure-utils/index.md)           | One-shot HNS detection helper for Azure accounts                      |
| [GraphAuth](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/#graphauth)   | MSAL token provider (client-credentials / device-code) for Graph      |
| [GraphUtils](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/#graphutils) | Resolve a Graph `drive_id` from OneDrive / SharePoint / Teams targets |

## Configuration

| Class                                                                                                                 | Description                                         |
| --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| [RegistryConfig](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.RegistryConfig)               | Top-level configuration holding backends and stores |
| [BackendConfig](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.BackendConfig)                 | Configuration for a single backend                  |
| [StoreProfile](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.StoreProfile)                   | Configuration for a single store                    |
| [RetryPolicy](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.RetryPolicy)                     | Retry policy for backend operations                 |
| [Secret](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.Secret)                               | Sensitive string wrapper with masked repr           |
| [SecretRedactionFilter](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.SecretRedactionFilter) | Logging filter that redacts secrets                 |
| [resolve_env](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.resolve_env)                     | Resolve `${VAR}` placeholders in config dicts       |

## Path & Models

| Class                                                                                                   | Description                                                                |
| ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| [RemotePath](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.RemotePath)         | Validated, immutable path value object                                     |
| [ResolutionPlan](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.ResolutionPlan) | Frozen introspection result from `resolve()`                               |
| [ContentDigest](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.ContentDigest)   | Verified content digest with known algorithm                               |
| [FileInfo](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.FileInfo)             | Metadata for a file (name, size, modified time)                            |
| [WriteResult](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.WriteResult)       | Immutable snapshot of a completed write operation                          |
| [FolderEntry](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.FolderEntry)       | Folder identity returned by listing operations                             |
| [FolderInfo](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.FolderInfo)         | Aggregated folder metadata (file count, total size); satisfies `PathEntry` |
| [PathEntry](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.PathEntry)           | Protocol for uniform listing (name + path)                                 |

## Capabilities

| Class                                                                                                       | Description                            |
| ----------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| [Capability](https://docs.remotestore.dev/stable/reference/api/capabilities/#remote_store.Capability)       | Enum of backend capabilities           |
| [CapabilitySet](https://docs.remotestore.dev/stable/reference/api/capabilities/#remote_store.CapabilitySet) | Set of capabilities a backend supports |

## Errors

| Class                                                                                                                   | Description                              |
| ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| [RemoteStoreError](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.RemoteStoreError)             | Base exception                           |
| [NotFound](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.NotFound)                             | File or folder not found                 |
| [AlreadyExists](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.AlreadyExists)                   | File already exists (no overwrite)       |
| [PermissionDenied](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.PermissionDenied)             | Insufficient permissions                 |
| [InvalidPath](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.InvalidPath)                       | Path validation failed                   |
| [CapabilityNotSupported](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.CapabilityNotSupported) | Backend lacks required capability        |
| [BackendUnavailable](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.BackendUnavailable)         | Backend could not be reached             |
| [DirectoryNotEmpty](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.DirectoryNotEmpty)           | Non-recursive delete on non-empty folder |
| [ResourceLocked](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.ResourceLocked)                 | Resource locked by another session       |

## Introspection

| Symbol                                                                                              | Description                                                |
| --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [info](https://docs.remotestore.dev/stable/reference/api/info/#remote_store.info)                   | Runtime introspection of available backends and extensions |
| [InfoResult](https://docs.remotestore.dev/stable/reference/api/info/#remote_store.InfoResult)       | TypedDict for the `info()` return value                    |
| [BackendInfo](https://docs.remotestore.dev/stable/reference/api/info/#remote_store.BackendInfo)     | TypedDict for a single backend entry in `InfoResult`       |
| [ExtensionInfo](https://docs.remotestore.dev/stable/reference/api/info/#remote_store.ExtensionInfo) | TypedDict for a single extension entry in `InfoResult`     |

## Functions

| Function                                                                                                      | Description                    |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| [register_backend](https://docs.remotestore.dev/stable/reference/api/registry/#remote_store.register_backend) | Register a custom backend type |

## Extensions

| Module                                                                                           | Description                                                     |
| ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| [ext.arrow](https://docs.remotestore.dev/stable/reference/api/extensions/arrow/index.md)         | PyArrow `FileSystemHandler` adapter for Store                   |
| [ext.batch](https://docs.remotestore.dev/stable/reference/api/extensions/batch/index.md)         | Batch delete, copy, and exists operations                       |
| [ext.cache](https://docs.remotestore.dev/stable/reference/api/extensions/cache/index.md)         | Store-level caching middleware with TTL                         |
| [ext.dagster](https://docs.remotestore.dev/stable/reference/api/extensions/dagster/index.md)     | Dagster IO Manager adapter for Store                            |
| [ext.glob](https://docs.remotestore.dev/stable/reference/api/extensions/glob/index.md)           | Portable glob pattern matching fallback                         |
| [ext.integrity](https://docs.remotestore.dev/stable/reference/api/extensions/integrity/index.md) | Checksum computation and verification helpers                   |
| [ext.observe](https://docs.remotestore.dev/stable/reference/api/extensions/observe/index.md)     | Callback hooks for store operations                             |
| [ext.otel](https://docs.remotestore.dev/stable/reference/api/extensions/otel/index.md)           | OpenTelemetry bridge for ext.observe                            |
| [ext.partition](https://docs.remotestore.dev/stable/reference/api/extensions/partition/index.md) | Hive-style partition path helpers                               |
| [ext.pydantic](https://docs.remotestore.dev/stable/reference/api/extensions/pydantic/index.md)   | Pydantic model to RegistryConfig adapter                        |
| [ext.streams](https://docs.remotestore.dev/stable/reference/api/extensions/streams/index.md)     | Composable BinaryIO wrappers for progress and checksums         |
| [ext.transfer](https://docs.remotestore.dev/stable/reference/api/extensions/transfer/index.md)   | Upload, download, and cross-store transfer                      |
| [ext.write](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md)         | Write helpers with guaranteed client-side content hashing       |
| [aio.ext.write](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md) | Async write helpers with guaranteed client-side content hashing |
| [ext.yaml](https://docs.remotestore.dev/stable/reference/api/extensions/yaml/index.md)           | YAML config loader (PyYAML / ruamel.yaml)                       |
