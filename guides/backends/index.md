# Backends

`remote-store` uses a pluggable backend system. Each backend implements the
`Backend` abstract class and declares its capabilities. Pick a backend based
on where your files live, install the optional extra, and everything else
stays the same -- the `Store` API is identical across all backends.

## Supported Backends

| Backend | Status | Install |
|---------|--------|---------|
| [Local filesystem](local.md) | Built-in | `pip install remote-store` |
| [Memory](memory.md) | Built-in | `pip install remote-store` |
| [Amazon S3 / MinIO](s3.md) | Built-in | `pip install "remote-store[s3]"` |
| [S3 (PyArrow)](s3-pyarrow.md) | Built-in | `pip install "remote-store[s3-pyarrow]"` |
| [SFTP / SSH](sftp.md) | Built-in | `pip install "remote-store[sftp]"` |
| [Azure Blob / ADLS](azure.md) | Built-in | `pip install "remote-store[azure]"` |

## Custom Backends

You can register your own backend using `register_backend`:

```python
from remote_store import register_backend, Backend

class MyBackend(Backend):
    ...

register_backend("my-backend", MyBackend)
```

See the `Backend` class in `src/remote_store/_backend.py` for the full
interface to implement.

## See also

- [Choosing a Backend](../choosing-a-backend.md) -- decision guide with trade-offs
- [Capabilities Matrix](../capabilities-matrix.md) -- full backend x capability table
