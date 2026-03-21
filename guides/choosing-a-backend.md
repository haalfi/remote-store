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
    - Need **maximum throughput** or PyArrow/Parquet integration? Use **S3-PyArrow**.
      C++ I/O via PyArrow, zero-copy reads, native `FileSystem` escape hatch.
    - Otherwise use **S3** (fsspec-based). Lighter dependency footprint, same
      API surface.

4. **Azure Blob Storage or ADLS Gen2?** Use **Azure**.
   Supports both flat and HNS (hierarchical namespace) accounts. Connection
   string, SAS token, or DefaultAzureCredential auth.

5. **SSH/SFTP server?** Use **SFTP**.
   Legacy systems, on-prem file servers. Supports password and key-based auth.
   Lacks native glob (use `ext.glob` fallback).

6. **Read-only HTTP/HTTPS endpoint?** Use **HTTP**.
   Public data, static file servers, REST APIs. Read and metadata only — no
   write, list, or delete. Zero required dependencies (stdlib `urllib`);
   optional `requests` or `httpx` transports for connection pooling.

## Trade-offs at a glance

| Backend | Dependencies | Glob | Throughput | Best for |
|---------|-------------|:----:|-----------|----------|
| [Local](backends/local.md) | None | Native | Disk-bound | Dev, single machine |
| [Memory](backends/memory.md) | None | Fallback | In-process | Tests, caches |
| [S3](backends/s3.md) | `s3fs` | Native | Network | General S3 workloads |
| [S3-PyArrow](backends/s3-pyarrow.md) | `pyarrow` | Native | High (C++) | Data lake, Parquet |
| [SFTP](backends/sftp.md) | `paramiko` | Fallback | Network | Legacy, on-prem |
| [Azure](backends/azure.md) | `azure-storage-blob` | Native | Network | Azure workloads |
| [HTTP](backends/http.md) | None | — | Network | Read-only public data |

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

## See also

- [Capabilities Matrix](capabilities-matrix.md) — full backend x capability
  table
- [Backends guide](backends/index.md) — per-backend configuration details
- [Performance guide](performance.md) — benchmark data across backends
