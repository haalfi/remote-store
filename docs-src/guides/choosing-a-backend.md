# Choosing a Backend

This guide helps you pick the right `remote-store` backend for your use case.

## Decision tree

1. **Local filesystem?** Use **Local**.
   Fast, full capabilities, zero config. Best for development and single-machine
   workflows.

2. **In-process testing or caching?** Use **Memory**.
   No disk I/O, instant setup/teardown, ideal for unit tests and ephemeral
   caches. Lacks native glob (use `ext.glob` fallback).

3. **S3-compatible object store (AWS S3, MinIO, Ceph, etc.)?**
    - Need **analytical workloads** (Parquet column pruning, PyArrow datasets)?
      Use **S3-PyArrow**. Native C++ `FileSystem` for PyArrow, GIL-free reads.
    - Otherwise use **S3** (fsspec-based). Faster for sequential reads/writes,
      lighter dependency footprint, same API surface.

4. **Azure Blob Storage or ADLS Gen2?** Use **Azure**.
   Supports both flat and HNS (hierarchical namespace) accounts — declare which
   via the required `hns` option. Connection string, SAS token, or
   DefaultAzureCredential auth. Analytical random access (Parquet footer reads,
   PyArrow column pruning) is efficient despite Azure not declaring
   `SEEKABLE_READ`: `read_seekable()` uses a native HTTP-Range reader on the
   sync backend — see the
   [Azure guide](backends/azure.md#streaming-and-seekable-reads).

5. **OneDrive, SharePoint, or Microsoft Teams files (Microsoft Graph)?** Use **Graph**.
   **Async-only** — construct via `AsyncStore(backend=GraphBackend(...))`; there is
   no sync wrapper or config `type=` string. Device-code or client-credential auth
   via MSAL; onboarding is the main hurdle, so start from the
   [setup guide](backends/graph-setup.md). Lacks native glob and seekable reads.

6. **SSH/SFTP server?** Use **SFTP**.
   Legacy systems, on-prem file servers. Supports password and key-based auth.
   Lacks native glob (use `ext.glob` fallback).

7. **Store blobs in a relational database (SQLite, PostgreSQL, etc.)?** Use **SQLBlob**.
   Broad capability set — read, write, list, move, copy, glob, and atomic writes.
   Useful for embedded storage, metadata-heavy workloads, or environments where a
   database is already available.

8. **Materialize SQL queries as files (read-only)?** Use **SQLQuery**.
   Executes a SQL query and exposes the result as Parquet, CSV, or Arrow IPC.
   Read and metadata only. Useful for ETL pipelines and data exports.

9. **Read-only HTTP/HTTPS endpoint?** Use **HTTP**.
   Public data, static file servers, REST APIs. Read and metadata only — no
   write, list, or delete. Zero required dependencies (stdlib `urllib`);
   optional `requests` or `httpx` transports for connection pooling.

## Trade-offs at a glance

| Backend | Dependencies | Glob | Throughput | Best for |
|---------|-------------|:----:|-----------|----------|
| [Local](backends/local.md) | None | Native | Disk-bound | Dev, single machine |
| [Memory](backends/memory.md) | None | Fallback | In-process | Tests, caches |
| [S3](backends/s3.md) | `s3fs` | Native | Network | General S3 workloads |
| [S3-PyArrow](backends/s3-pyarrow.md) | `pyarrow` | Native | Network | Parquet, PyArrow datasets |
| [Azure](backends/azure.md) | `azure-storage-blob` | Native | Network | Azure workloads |
| [Graph](backends/graph.md) | `httpx` + `msal` | Fallback | Network | OneDrive / SharePoint / Teams (async-only) |
| [SFTP](backends/sftp.md) | `paramiko` | Fallback | Network | Legacy, on-prem |
| [HTTP](backends/http.md) | None | — | Network | Read-only public data |
| [SQLBlob](backends/sql-blob.md) | `sqlalchemy` | Native | DB-bound | Embedded, metadata-heavy |
| [SQLQuery](backends/sql-query.md) | `sqlalchemy` + `pyarrow` | Native | DB-bound | Read-only ETL exports |

## Switching backends at runtime

The whole point of `remote-store` is that your application code stays the same
regardless of backend. Switch via configuration:

```toml
# dev.toml
[backends.storage]
type = "local"
base_path = "./data"

[stores.default]
backend = "storage"

# prod.toml
[backends.storage]
type = "s3"
bucket = "my-bucket"

[stores.default]
backend = "storage"
```

```python
from remote_store import RegistryConfig, Registry

config = RegistryConfig.from_toml("dev.toml")  # or "prod.toml"
registry = Registry(config)
store = registry.get_store("default")
# Same API regardless of backend
```

Config-driven switching covers the sync backends. The async-only **Graph**
backend has no config `type=` string — construct it directly via
`AsyncStore(backend=GraphBackend(...))` (see the [Graph guide](backends/graph.md)).

## See also

- [Capabilities Matrix](../reference/capabilities-matrix.md) — full backend x capability
  table
- [Backends guide](backends/index.md) — per-backend configuration details
- [Performance guide](../explanation/performance.md) — benchmark data across backends
