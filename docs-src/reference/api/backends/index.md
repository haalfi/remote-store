# Backends

API reference for all storage backend classes.
Each backend implements the [`Backend`](../backend.md) protocol.
For usage guides, see [Backends](../../../guides/backends/index.md).

| Class | Description |
|-------|-------------|
| [LocalBackend](local.md) | Local filesystem storage |
| [MemoryBackend](memory.md) | In-process storage for testing |
| [S3Backend](s3.md) | Amazon S3 and S3-compatible services |
| [S3PyArrowBackend](s3-pyarrow.md) | S3 via PyArrow C++ for higher throughput |
| [AzureBackend](azure.md) | Azure Blob Storage and ADLS Gen2 |
| [SFTPBackend](sftp.md) | SSH/SFTP server storage via paramiko |
| [ReadOnlyHttpBackend](http.md) | Read-only access to HTTP/HTTPS URLs |
| [SQLBlobBackend](sql-blob.md) | SQL database blob storage via SQLAlchemy |
| [SQLQueryBackend](sql-query.md) | Read-only SQL query materialization via SQLAlchemy + PyArrow |

## Async-native backends

These backends run natively on the event loop under
[`AsyncStore`](../aio/store.md); they live in `remote_store.aio.backends`.
Any synchronous backend above also works under `AsyncStore` via the
thread-pool [`SyncBackendAdapter`](../aio/adapters.md).

| Class | Description |
|-------|-------------|
| [AsyncMemoryBackend](../aio/backends/memory.md) | In-memory async backend for testing |
| [AsyncAzureBackend](../aio/backends/azure.md) | Native async Azure Blob Storage and ADLS Gen2 |
| [GraphBackend](../aio/backends/graph.md) | Microsoft Graph backend (OneDrive, SharePoint, Teams files) — async-only |

## See also

- [Backend guides](../../../guides/backends/index.md) — configuration and usage guides for all backends
- [Choosing a Backend](../../../guides/choosing-a-backend.md) — trade-offs and selection criteria
- [Capabilities Matrix](../../capabilities-matrix.md) — per-backend capability comparison
