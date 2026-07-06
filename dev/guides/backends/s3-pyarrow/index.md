# S3-PyArrow Backend

Drop-in alternative to the [S3 backend](https://docs.remotestore.dev/stable/guides/backends/s3/index.md) optimized for analytical workloads. Uses [PyArrow's C++ S3 filesystem](https://arrow.apache.org/docs/python/generated/pyarrow.fs.S3FileSystem.html) for data-path operations (reads, writes, copies) and s3fs for control-path operations (listing, metadata, deletion). This enables Tier 1 PyArrow integration — Parquet column pruning, I/O coalescing, and GIL-free reads — while keeping the same API.

## Installation

```
pip install "remote-store[s3-pyarrow]"
```

This pulls in both `s3fs` and `pyarrow`.

## Usage

```
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

| Option           | Type   | Description                                                      |
| ---------------- | ------ | ---------------------------------------------------------------- |
| `bucket`         | `str`  | S3 bucket name (required)                                        |
| `key`            | `str`  | AWS access key ID                                                |
| `secret`         | `str`  | AWS secret access key                                            |
| `region_name`    | `str`  | AWS region name                                                  |
| `endpoint_url`   | `str`  | Custom endpoint for S3-compatible services                       |
| `tls_ca_bundle`  | `str`  | Path to a PEM CA bundle file for custom/self-signed certificates |
| `client_options` | `dict` | Additional options passed to s3fs (control-path)                 |

## Custom TLS Certificates

Use `tls_ca_bundle` when connecting to S3-compatible services with custom or self-signed certificates. The parameter applies to both the PyArrow data path (`tls_ca_file_path`) and the s3fs control path (`client_kwargs.verify`).

```
backend = S3PyArrowBackend(
    bucket="my-bucket",
    endpoint_url="https://minio.internal:9000",
    tls_ca_bundle="/etc/ssl/certs/internal-ca.pem",
)
```

If not set, falls back to env vars: `AWS_CA_BUNDLE` > `REQUESTS_CA_BUNDLE` > `SSL_CERT_FILE`. See the [S3 backend guide](https://docs.remotestore.dev/stable/guides/backends/s3/#custom-tls-certificates) for the full fallback chain and config examples.

## When to use S3-PyArrow vs S3

| Scenario                                 | Recommended backend                  |
| ---------------------------------------- | ------------------------------------ |
| General-purpose file storage             | `s3`                                 |
| Sequential byte streaming (read/write)   | `s3` (faster at every file size)     |
| Analytical workloads (Parquet, datasets) | `s3-pyarrow` (Tier 1 column pruning) |
| Minimal dependencies                     | `s3` (only needs `s3fs`)             |
| PyArrow already in your stack            | `s3-pyarrow` (zero extra deps)       |

S3-PyArrow's C++ data path adds per-call overhead for sequential reads compared to the regular S3 backend. The advantage is native PyArrow integration: when PyArrow reads Parquet files through the [adapter](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md), it uses C++ range requests and I/O coalescing directly — no Python in the loop.

Both backends lack `ATOMIC_MOVE`, but they differ on `USER_METADATA`: the regular S3 backend declares it (write calls accept `metadata=` and store it as S3 object metadata), while S3-PyArrow does not. Code that passes `metadata=` to write methods will get `CapabilityNotSupported` on the PyArrow backend. For workloads that do not use object metadata, switching is safe — change the `type` in your config.

## Escape Hatch

Access the underlying filesystems when you need protocol-level features:

```
from pyarrow.fs import S3FileSystem as PyArrowS3
import s3fs

# PyArrow filesystem (data path)
pa_fs = backend.unwrap(PyArrowS3)

# s3fs filesystem (control path)
s3_fs = backend.unwrap(s3fs.S3FileSystem)
```

## Caveats

- **`move()` is not atomic.** Like the S3 backend, move is copy + delete. A crash between the two steps leaves duplicates.
- **`overwrite=False` has a TOCTOU race.** The exists-check and write are separate API calls. Concurrent writers can both pass the check and overwrite each other.

See the [Concurrency and Atomicity Guarantees](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) guide for details and workarounds.

## See also

- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md)
- [Example script](https://docs.remotestore.dev/stable/tutorial/examples/s3-pyarrow-backend/index.md)

## API Reference

## S3PyArrowBackend

```
S3PyArrowBackend(
    bucket: str,
    *,
    endpoint_url: str | None = None,
    key: str | Secret | None = None,
    secret: str | Secret | None = None,
    region_name: str | None = None,
    tls_ca_bundle: str | None = None,
    client_options: dict[str, Any] | None = None,
    retry: RetryPolicy | None = None,
    reject_write_under_file_ancestor: bool = False,
)
```

Bases: `_S3Base`

Hybrid S3 backend: PyArrow for reads/writes/copies, s3fs for listing/metadata.

Drop-in alternative to `S3Backend` with the same constructor signature. Uses PyArrow's C++ S3 filesystem for data-path operations (higher throughput for large files) and s3fs for control-path operations (listing, metadata, deletion).

`move()` is implemented as a PyArrow copy followed by an s3fs delete. This is non-atomic: a crash or network error between the two steps may leave both source and destination present. `ATOMIC_MOVE` is not declared.

Parameters:

- **`bucket`** (`str`) – S3 bucket name (required, non-empty).
- **`endpoint_url`** (`str | None`, default: `None` ) – Custom endpoint URL (e.g. for MinIO).
- **`key`** (`str | Secret | None`, default: `None` ) – AWS access key ID.
- **`secret`** (`str | Secret | None`, default: `None` ) – AWS secret access key.
- **`region_name`** (`str | None`, default: `None` ) – AWS region name.
- **`tls_ca_bundle`** (`str | None`, default: `None` ) – Path to a PEM CA bundle file. Falls back to AWS_CA_BUNDLE / REQUESTS_CA_BUNDLE / SSL_CERT_FILE.
- **`client_options`** (`dict[str, Any] | None`, default: `None` ) – Additional options passed to s3fs.
- **`reject_write_under_file_ancestor`** (`bool`, default: `False` ) – If True, write / write_atomic / open_atomic / move / copy HEAD each slash-aligned ancestor of the target path and raise InvalidPath on the first regular-file hit, matching the cross-backend contract that hierarchical filesystems enforce natively. Default False: each nested-path write otherwise pays one HEAD per ancestor; paths without slashes short-circuit.
