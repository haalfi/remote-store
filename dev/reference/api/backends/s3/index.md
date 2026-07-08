# S3Backend

API reference for `S3Backend` — stores files on Amazon S3 or any S3-compatible service (MinIO, DigitalOcean Spaces, etc.).

## S3Backend

```
S3Backend(
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

S3-compatible object storage backend using s3fs.

`move()` is implemented as a server-side copy followed by a delete. This is non-atomic: a crash or network error between the two steps may leave both source and destination present. `ATOMIC_MOVE` is not declared.

Parameters:

- **`bucket`** (`str`) – S3 bucket name (required, non-empty).
- **`endpoint_url`** (`str | None`, default: `None` ) – Custom endpoint URL (e.g. for MinIO).
- **`key`** (`str | Secret | None`, default: `None` ) – AWS access key ID.
- **`secret`** (`str | Secret | None`, default: `None` ) – AWS secret access key.
- **`region_name`** (`str | None`, default: `None` ) – AWS region name.
- **`tls_ca_bundle`** (`str | None`, default: `None` ) – Path to a PEM CA bundle file. Falls back to AWS_CA_BUNDLE / REQUESTS_CA_BUNDLE / SSL_CERT_FILE.
- **`client_options`** (`dict[str, Any] | None`, default: `None` ) – Additional options passed to s3fs.
- **`reject_write_under_file_ancestor`** (`bool`, default: `False` ) – If True, write / write_atomic / open_atomic / move / copy HEAD each slash-aligned ancestor of the target path and raise InvalidPath on the first regular-file hit, matching the cross-backend contract that hierarchical filesystems enforce natively. Default False: each nested-path write otherwise pays one HEAD per ancestor; paths without slashes short-circuit.

### check_health

```
check_health() -> None
```

Confirm the bucket is reachable and credentials valid via one `HeadBucket`.

Raises:

- `NotFound` – If the bucket does not exist.
- `PermissionDenied` – If the credentials are rejected or lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### exists

```
exists(path: str) -> bool
```

Return `True` if an object or prefix exists at *path*; never `NotFound`.

Raises:

- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* is an existing object (`False` if absent or a prefix).

Raises:

- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* is an existing virtual folder (a common prefix).

Raises:

- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### read

```
read(path: str) -> BinaryIO
```

Open *path* for reading and return a streaming handle.

s3fs reads the object lazily in range-backed chunks, so memory stays constant regardless of size.

Raises:

- `NotFound` – If the object does not exist.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read and return the full object content as bytes.

Downloads the whole object into memory (unlike the lazy `read` stream).

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

Write *content* to *path* as an S3 object.

The upload commits atomically — a reader sees either the old object or the new one, never a partial. A streamed write that fails mid-body aborts the multipart upload rather than finalising a truncated object, so no partial object is ever left at *path*.

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

Write *content* to *path* atomically (delegates to `write`).

An S3 `PUT` is already atomic, so this is exactly `write`.

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

Writes spool to a temporary file (up to 8 MB in memory, then on disk); on clean exit the buffer is uploaded in a single atomic `PUT`. An exception before exit leaves *path* untouched.

Raises:

- `AlreadyExists` – If the object exists and overwrite is False.
- `InvalidPath` – With the opt-in, if an ancestor of path exists as an object.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete the object at *path*.

Raises:

- `NotFound` – If the object does not exist and missing_ok is False.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### delete_folder

```
delete_folder(
    path: str,
    *,
    recursive: bool = False,
    missing_ok: bool = False,
) -> None
```

Delete the virtual folder at *path*.

`recursive=True` removes every object under the prefix; this is a best-effort multi-object delete, not atomic, so an interruption can leave the prefix partially deleted. `recursive=False` removes the prefix only when it has no contents.

Raises:

- `NotFound` – If no object exists under path and missing_ok is False.
- `DirectoryNotEmpty` – If the prefix is non-empty and recursive is False.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return metadata for the object at *path* from one `HeadObject`.

The HEAD is issued with `ChecksumMode=ENABLED` so a stored checksum surfaces as the `FileInfo` digest.

Raises:

- `NotFound` – If the object does not exist.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename the object *src* to *dst*.

Implemented as a server-side copy followed by a delete of *src*. This is not atomic — a crash or network error between the two steps can leave both *src* and *dst* present — so `ATOMIC_MOVE` is not declared. `src == dst` is a no-op.

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

Copy the object *src* to *dst* via a server-side `CopyObject`.

The bytes are copied entirely server-side (never through the client). Like `move`, the operation carries no cross-operation atomicity guarantee. `src == dst` is a no-op.

Raises:

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `InvalidPath` – With the opt-in, if an ancestor of dst exists as an object.
- `PermissionDenied` – If the credentials lack access.
- `BackendUnavailable` – On a transport or service failure, or after close().

## See also

- [S3 Backend Guide](https://docs.remotestore.dev/stable/guides/backends/s3/index.md) — usage patterns, configuration, and examples
- [S3 Backend example](https://docs.remotestore.dev/stable/tutorial/examples/s3-backend/index.md) — S3 backend in action
