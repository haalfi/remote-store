# Troubleshooting

Common errors and their solutions when using `remote-store`.

## ImportError for optional dependencies

**Symptom:** `ImportError: No module named 'pyarrow'` (or `paramiko`,
`azure.storage.blob`, etc.)

**Cause:** Backend-specific dependencies are optional extras.

**Fix:** Install the extra for your backend:

```bash
pip install "remote-store[s3]"         # S3 backend (fsspec + s3fs)
pip install "remote-store[s3-pyarrow]" # S3-PyArrow backend
pip install "remote-store[sftp]"       # SFTP backend (paramiko)
pip install "remote-store[azure]"      # Azure backend
pip install "remote-store[all]"        # Everything
```

## Windows file-locking errors (WinError 32)

**Symptom:** `PermissionError: [WinError 32] The process cannot access the file
because it is being used by another process`

**Cause:** An unclosed stream from `store.read()` keeps a file handle open.
On Windows (unlike Unix), open handles prevent deletion and cleanup.

**Fix:** Always close streams or use a context manager:

```python
# Good
stream = store.read("data.csv")
try:
    content = stream.read()
finally:
    stream.close()

# Better
with store.read("data.csv") as stream:
    content = stream.read()
```

## Unicode / cp1252 encoding errors on Windows

**Symptom:** `UnicodeEncodeError: 'charmap' codec can't encode character`

**Cause:** Windows console uses cp1252 by default. Characters like em dashes,
arrows, or box-drawing characters crash `print()`.

**Fix:** Use ASCII-only characters in print statements. For Polars DataFrames,
use `iter_rows(named=True)` with manual formatting instead of `print(df)`.

## SFTP host-key verification failure

**Symptom:** `SSHException: Server host key not found` or similar.

**Cause:** Paramiko requires host-key verification by default.

**Fix:** Configure the host-key policy in your backend config:

```python
config = {
    "backends": {
        "my-sftp": {
            "type": "sftp",
            "host": "sftp.example.com",
            "username": "user",
            "password": "pass",
            "host_key_policy": "auto",  # or path to known_hosts
        }
    },
    "stores": {"default": {"backend": "my-sftp"}},
}
```

## Azure: HNS vs flat namespace

**Symptom:** `move()` or `copy()` fails on Azure with unexpected errors.

**Cause:** Azure Blob Storage has two modes: flat namespace (default) and
hierarchical namespace (HNS / ADLS Gen2). Some operations behave differently.

**Fix:** Ensure your storage account type matches your expectations. HNS
accounts support true directory operations; flat namespace accounts simulate
them. The Azure backend handles both, but HNS is recommended for data lake
workloads.

## S3 endpoint configuration for MinIO / local S3

**Symptom:** Connection errors when using MinIO or another S3-compatible service.

**Cause:** The default S3 endpoint points to AWS. Local services need an
explicit endpoint URL.

**Fix:**

```python
config = {
    "backends": {
        "minio": {
            "type": "s3",
            "bucket": "my-bucket",
            "endpoint_url": "http://localhost:9000",
            "key": "minioadmin",
            "secret": "minioadmin",
        }
    },
    "stores": {"default": {"backend": "minio"}},
}
```

## CapabilityNotSupported error

**Symptom:** `CapabilityNotSupported: Backend 'memory' does not support GLOB`

**Cause:** Not all backends support every operation. Memory and SFTP lack
native glob.

**Fix:** Check capabilities before calling, or use the portable fallback:

```python
from remote_store import Capability, glob_files

if Capability.GLOB in store.capabilities():
    results = store.glob("**/*.csv")
else:
    results = glob_files(store, "**/*.csv")
```

See the [Capabilities Matrix](capabilities-matrix.md) for the full
backend x capability table.

## See also

- [Getting Started](getting-started.md) -- installation and quick start
- [Choosing a Backend](choosing-a-backend.md) -- picking the right backend
- [Error Handling example](examples/error-handling.md)
