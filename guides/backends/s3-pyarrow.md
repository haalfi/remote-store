# S3-PyArrow Backend

Drop-in alternative to the [S3 backend](s3.md) that uses [PyArrow's C++ S3 filesystem](https://arrow.apache.org/docs/python/generated/pyarrow.fs.S3FileSystem.html) for data-path operations (reads, writes, copies) and s3fs for control-path operations (listing, metadata, deletion). This gives higher throughput for large files while keeping the same API.

## Installation

```bash
pip install remote-store[s3-pyarrow]
```

This pulls in both `s3fs` and `pyarrow`.

## Usage

```python
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={
        "s3pa": BackendConfig(
            type="s3-pyarrow",
            options={
                "bucket": "my-bucket",
                "key": "AWS_ACCESS_KEY_ID",
                "secret": "AWS_SECRET_ACCESS_KEY",
                "endpoint_url": "https://s3.amazonaws.com",
            },
        ),
    },
    stores={"data": StoreProfile(backend="s3pa", root_path="data")},
)

with Registry(config) as registry:
    store = registry.get_store("data")
    store.write("report.csv", b"col1,col2\n1,2\n")
```

## Options

Same constructor signature as the S3 backend:

| Option | Type | Description |
|--------|------|-------------|
| `bucket` | `str` | S3 bucket name (required) |
| `key` | `str` | AWS access key ID |
| `secret` | `str` | AWS secret access key |
| `region_name` | `str` | AWS region name |
| `endpoint_url` | `str` | Custom endpoint for S3-compatible services |
| `client_options` | `dict` | Additional options passed to s3fs (control-path) |

## When to use S3-PyArrow vs S3

| Scenario | Recommended backend |
|----------|-------------------|
| General-purpose file storage | `s3` |
| Large file reads/writes (100 MB+) | `s3-pyarrow` |
| Minimal dependencies | `s3` (only needs `s3fs`) |
| PyArrow already in your stack | `s3-pyarrow` (zero extra deps) |

Both backends support all capabilities and are fully interchangeable — switch by changing the `type` in your config.

## Escape Hatch

Access the underlying filesystems when you need protocol-level features:

```python
from pyarrow.fs import S3FileSystem as PyArrowS3
import s3fs

# PyArrow filesystem (data path)
pa_fs = backend.unwrap(PyArrowS3)

# s3fs filesystem (control path)
s3_fs = backend.unwrap(s3fs.S3FileSystem)
```
