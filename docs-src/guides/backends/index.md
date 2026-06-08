# Backends

`remote-store` uses a pluggable backend system. Each backend implements the
`Backend` abstract class and declares its capabilities. Pick a backend based
on where your files live, install the optional extra, and everything else
stays the same — the `Store` API is identical across all backends.

## Supported Backends

| Backend | Status | Install |
|---------|--------|---------|
| [Local filesystem](local.md) | Built-in | `pip install remote-store` |
| [Memory](memory.md) | Built-in | `pip install remote-store` |
| [HTTP/HTTPS (read-only)](http.md) | Built-in | `pip install remote-store` |
| [Amazon S3 / MinIO](s3.md) | Built-in | `pip install "remote-store[s3]"` |
| [S3 (PyArrow)](s3-pyarrow.md) | Built-in | `pip install "remote-store[s3-pyarrow]"` |
| [SFTP / SSH](sftp.md) | Built-in | `pip install "remote-store[sftp]"` |
| [Azure Blob / ADLS](azure.md) | Built-in | `pip install "remote-store[azure]"` |
| [Microsoft Graph (OneDrive / SharePoint / Teams)](graph.md) | Built-in (async-only) | `pip install "remote-store[graph]"` |
| [SQL Blob (SQLite, PostgreSQL, ...)](sql-blob.md) | Built-in | `pip install "remote-store[sql]"` |
| [SQL Query (read-only)](sql-query.md) | Built-in | `pip install "remote-store[sql-query]"` |

## Custom Backends

You can register your own backend using `register_backend`:

```python
from remote_store import register_backend, Backend

class MyBackend(Backend):
    ...

register_backend("my-backend", MyBackend)
```

See the [Backend API reference](../../reference/api/backend.md) for the full interface to
implement, and the [Build Your Own Backend](../custom-backend-guide.md) guide
for a step-by-step walkthrough.

## See also

- [Choosing a Backend](../choosing-a-backend.md) — decision guide with trade-offs
- [Capabilities Matrix](../../reference/capabilities-matrix.md) — full backend x capability table
