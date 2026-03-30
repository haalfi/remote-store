# Backends

API reference for all storage backend classes.
Each backend implements the [`Backend`](../backend.md) protocol.
For usage guides, see [Backends](../../backends/index.md).

| Class | Description |
|-------|-------------|
| [LocalBackend](local.md) | Local filesystem storage |
| [MemoryBackend](memory.md) | In-process storage for testing |
| [ReadOnlyHttpBackend](http.md) | Read-only access to HTTP/HTTPS URLs |
| [S3Backend](s3.md) | Amazon S3 and S3-compatible services |
| [S3PyArrowBackend](s3-pyarrow.md) | S3 via PyArrow C++ for higher throughput |
| [SFTPBackend](sftp.md) | SSH/SFTP server storage via paramiko |
| [AzureBackend](azure.md) | Azure Blob Storage and ADLS Gen2 |
| [SQLBlobBackend](sql-blob.md) | SQL database blob storage via SQLAlchemy |
| [SQLQueryBackend](sql-query.md) | Read-only SQL query materialization via SQLAlchemy + PyArrow |

## See also

- [Backend guides](../../backends/index.md) — configuration and usage guides for all backends
- [Choosing a Backend](../../choosing-a-backend.md) — trade-offs and selection criteria
- [Capabilities Matrix](../../capabilities-matrix.md) — per-backend capability comparison
