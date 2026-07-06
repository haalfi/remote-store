# Backends

`remote-store` uses a pluggable backend system. Each backend implements the `Backend` abstract class and declares its capabilities. Pick a backend based on where your files live, install the optional extra, and everything else stays the same — the `Store` API is identical across all backends.

## Supported Backends

| Backend                                                                                                               | Status                | Install                                  |
| --------------------------------------------------------------------------------------------------------------------- | --------------------- | ---------------------------------------- |
| [Local filesystem](https://docs.remotestore.dev/stable/guides/backends/local/index.md)                                | Built-in              | `pip install remote-store`               |
| [Memory](https://docs.remotestore.dev/stable/guides/backends/memory/index.md)                                         | Built-in              | `pip install remote-store`               |
| [HTTP/HTTPS (read-only)](https://docs.remotestore.dev/stable/guides/backends/http/index.md)                           | Built-in              | `pip install remote-store`               |
| [Amazon S3 / MinIO](https://docs.remotestore.dev/stable/guides/backends/s3/index.md)                                  | Built-in              | `pip install "remote-store[s3]"`         |
| [S3 (PyArrow)](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md)                               | Built-in              | `pip install "remote-store[s3-pyarrow]"` |
| [SFTP / SSH](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md)                                       | Built-in              | `pip install "remote-store[sftp]"`       |
| [Azure Blob / ADLS](https://docs.remotestore.dev/stable/guides/backends/azure/index.md)                               | Built-in              | `pip install "remote-store[azure]"`      |
| [Microsoft Graph (OneDrive / SharePoint / Teams)](https://docs.remotestore.dev/stable/guides/backends/graph/index.md) | Built-in (async-only) | `pip install "remote-store[graph]"`      |
| [SQL Blob (SQLite, PostgreSQL, ...)](https://docs.remotestore.dev/stable/guides/backends/sql-blob/index.md)           | Built-in              | `pip install "remote-store[sql]"`        |
| [SQL Query (read-only)](https://docs.remotestore.dev/stable/guides/backends/sql-query/index.md)                       | Built-in              | `pip install "remote-store[sql-query]"`  |

## Custom Backends

You can register your own backend using `register_backend`:

```
from remote_store import register_backend, Backend

class MyBackend(Backend):
    ...

register_backend("my-backend", MyBackend)
```

See the [Backend API reference](https://docs.remotestore.dev/stable/reference/api/backend/index.md) for the full interface to implement, and the [Build Your Own Backend](https://docs.remotestore.dev/stable/guides/custom-backend-guide/index.md) guide for a step-by-step walkthrough.

## See also

- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md) — decision guide with trade-offs
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — full backend x capability table
