# S3PyArrowBackend

API reference for `S3PyArrowBackend` — drop-in alternative to `S3Backend` that uses PyArrow's C++ S3 filesystem for higher throughput on large files.

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

## See also

- [S3-PyArrow Backend Guide](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md) — usage patterns, configuration, and examples
- [S3-PyArrow Backend example](https://docs.remotestore.dev/stable/tutorial/examples/s3-pyarrow-backend/index.md) — S3-PyArrow backend in action
