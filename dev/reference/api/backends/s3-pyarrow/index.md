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

### read

```
read(path: str) -> BinaryIO
```

Open *path* for reading and return a streaming handle.

Uses PyArrow's `open_input_file` (higher throughput for large objects) rather than the s3fs reader; still lazy, so memory stays constant.

Raises:

- `NotFound` – If the object does not exist.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read and return the full object content as bytes (via PyArrow).

Raises:

- `NotFound` – If the object does not exist.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### write

```
write(
    path: str,
    content: WritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write *content* to *path*, streaming straight to a multipart upload.

Unlike `S3Backend.write`, a plain streamed write here is **not** atomic: PyArrow's output stream exposes no abort, so a failure mid-body finalises a *truncated* object at *path*. Use `write_atomic` when readers must never observe a partial object. A `bytes` payload (no streaming) commits in one shot.

Raises:

- `AlreadyExists` – If the object exists and overwrite is False.
- `InvalidPath` – With the reject_write_under_file_ancestor opt-in, if an ancestor of path exists as an object.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### write_atomic

```
write_atomic(
    path: str,
    content: WritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write *content* to *path* atomically by buffering before upload.

The whole body is buffered first (a `bytes` payload is already materialised and delegates straight through), so a source failure happens off the wire and leaves no object at *path* — closing the atomicity gap in the plain streaming `write`.

Raises:

- `AlreadyExists` – If the object exists and overwrite is False.
- `InvalidPath` – With the opt-in, if an ancestor of path exists as an object.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]
```

Yield a writable buffer committed to *path* atomically on clean exit.

Writes spool to a temporary file (up to 8 MB in memory, then on disk) and upload only on clean exit, so *path* never holds a partial object. An exception before exit leaves *path* untouched.

Raises:

- `AlreadyExists` – If the object exists and overwrite is False.
- `InvalidPath` – With the opt-in, if an ancestor of path exists as an object.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename the object *src* to *dst*.

Existence checks and the delete go through s3fs; the copy is a PyArrow `copy_file`. Copy-then-delete is not atomic — a failure between the two steps can leave both *src* and *dst* present — so `ATOMIC_MOVE` is not declared. `src == dst` is a no-op.

Raises:

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `InvalidPath` – With the opt-in, if an ancestor of dst exists as an object.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy the object *src* to *dst* via a PyArrow `copy_file`.

Like `move`, the operation carries no cross-operation atomicity guarantee. `src == dst` is a no-op.

Raises:

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `InvalidPath` – With the opt-in, if an ancestor of dst exists as an object.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

## See also

- [S3-PyArrow Backend Guide](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md) — usage patterns, configuration, and examples
- [S3-PyArrow Backend example](https://docs.remotestore.dev/stable/tutorial/examples/s3-pyarrow-backend/index.md) — S3-PyArrow backend in action
