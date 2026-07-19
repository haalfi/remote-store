# Backends

API reference for all storage backend classes. Each backend implements the [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md) protocol. For usage guides, see [Backends](https://docs.remotestore.dev/stable/guides/backends/index.md).

| Class                                                                                              | Description                                                  |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| [LocalBackend](https://docs.remotestore.dev/stable/reference/api/backends/local/index.md)          | Local filesystem storage                                     |
| [MemoryBackend](https://docs.remotestore.dev/stable/reference/api/backends/memory/index.md)        | In-process storage for testing                               |
| [S3Backend](https://docs.remotestore.dev/stable/reference/api/backends/s3/index.md)                | Amazon S3 and S3-compatible services                         |
| [S3PyArrowBackend](https://docs.remotestore.dev/stable/reference/api/backends/s3-pyarrow/index.md) | S3 via PyArrow C++ for higher throughput                     |
| [AzureBackend](https://docs.remotestore.dev/stable/reference/api/backends/azure/index.md)          | Azure Blob Storage and ADLS Gen2                             |
| [SFTPBackend](https://docs.remotestore.dev/stable/reference/api/backends/sftp/index.md)            | SSH/SFTP server storage via paramiko                         |
| [ReadOnlyHttpBackend](https://docs.remotestore.dev/stable/reference/api/backends/http/index.md)    | Read-only access to HTTP/HTTPS URLs                          |
| [SQLBlobBackend](https://docs.remotestore.dev/stable/reference/api/backends/sql-blob/index.md)     | SQL database blob storage via SQLAlchemy                     |
| [SQLQueryBackend](https://docs.remotestore.dev/stable/reference/api/backends/sql-query/index.md)   | Read-only SQL query materialization via SQLAlchemy + PyArrow |

## Async-native backends

These backends run natively on the event loop under [`AsyncStore`](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md); they live in `remote_store.aio.backends`. Any synchronous backend above also works under `AsyncStore` via the thread-pool [`SyncBackendAdapter`](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md).

| Class                                                                                                | Description                                                              |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| [AsyncMemoryBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/memory/index.md) | In-memory async backend for testing                                      |
| [AsyncAzureBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/azure/index.md)   | Native async Azure Blob Storage and ADLS Gen2                            |
| [GraphBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/graph/index.md)        | Microsoft Graph backend (OneDrive, SharePoint, Teams files) — async-only |

## See also

- [Backend guides](https://docs.remotestore.dev/stable/guides/backends/index.md) — configuration and usage guides for all backends
- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md) — trade-offs and selection criteria
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — per-backend capability comparison
