# Backends

`remote-store` uses a pluggable backend system. Each backend implements the `Backend` abstract class and declares its capabilities.

## Supported Backends

| Backend | Status | Install |
|---------|--------|---------|
| [Local filesystem](local.md) | Built-in | `pip install remote-store` |
| [Amazon S3 / MinIO](s3.md) | Built-in | `pip install remote-store[s3]` |
| [S3 (PyArrow)](s3-pyarrow.md) | Built-in | `pip install remote-store[s3-pyarrow]` |
| [SFTP / SSH](sftp.md) | Built-in | `pip install remote-store[sftp]` |
| Azure Blob / ADLS | Planned | |

## Custom Backends

You can register your own backend using `register_backend`:

```python
from remote_store import register_backend, Backend

class MyBackend(Backend):
    ...

register_backend("my-backend", MyBackend)
```

See the [Backend API reference](../api/backend.md) for the full interface to implement.
