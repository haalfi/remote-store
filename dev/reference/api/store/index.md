# Store

## Store

```
Store(backend: Backend, root_path: str = '')
```

A logical remote folder scoped to a root path.

All path arguments are validated and prefixed with `root_path` before being delegated to the backend. Supports the context-manager protocol (`with Store(...) as s:`) which calls `close()` on exit.

Parameters:

- **`backend`** (`Backend`) – Backend instance (Local, S3, SFTP, Azure, Memory).
- **`root_path`** (`str`, default: `''` ) – Prefix prepended to every path. "" means the backend root.

Root path creation

The root path does not need to exist before constructing the store. `write()` creates intermediate folders implicitly on all backends:

```
store = Store(backend, root_path="brand-new-folder")
store.write("hello.txt", b"works")  # folder created automatically
```

Thread safety

`Store` is immutable after construction and can be shared across threads. Backend thread safety depends on the backend implementation.

______________________________________________________________________

## Reading

Requires `Capability.READ`

All read methods raise `CapabilityNotSupported` on backends that do not declare this capability. Most backends declare it.

### read

```
read(path: str) -> BinaryIO
```

Return a readable binary stream positioned at the start of *path*.

The caller is responsible for closing the stream (or using a `with` block).

Parameters:

- **`path`** (`str`) – Store-relative file path.

Returns:

- `BinaryIO` – Readable binary stream positioned at byte 0.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path is empty, or if path names a directory.

Quality flag: `Capability.LAZY_READ`

When declared, data is fetched lazily — partial reads avoid loading the whole file. Without it, the backend may buffer content before returning the stream.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read the entire file into memory and return `bytes`.

Parameters:

- **`path`** (`str`) – Store-relative file path.

Returns:

- `bytes` – The file content as bytes.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path is empty, or if path names a directory.

Equivalent to `read(path).read()`.

### read_seekable

```
read_seekable(path: str) -> BinaryIO
```

Return a seekable binary stream for random-access reading.

Always returns a seekable stream. On backends that natively return seekable streams from `read()`, this is zero-overhead. On backends whose `read()` is forward-only, the stream comes either from an optimized native implementation as cheap as the passthrough -- the sync Azure backend uses HTTP Range requests, one ranged download per `read()`, with no temp-file spill -- or from a temporary-file spool that copies the object first (HTTP, and an async backend bridged to sync).

Use `read()` for sequential streaming. Use `read_seekable()` when you need `seek()` / `tell()` -- for example, when passing the stream to PyArrow or other analytical readers.

Parameters:

- **`path`** (`str`) – Store-relative file path.

Returns:

- `BinaryIO` – A seekable binary stream positioned at byte 0.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path is empty, or if path names a directory.

Quality flag: `Capability.SEEKABLE_READ`

When declared, the stream is natively seekable. Without it, the Store falls back to a `SpooledTemporaryFile` (RAM-first, spilling to disk beyond the threshold). Backends may provide a more efficient implementation — for example, Azure issues HTTP Range requests instead of spooling.

### read_text

```
read_text(
    path: str,
    *,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> str
```

Read the entire file and decode it as text.

Parameters:

- **`path`** (`str`) – Store-relative file path.
- **`encoding`** (`str`, default: `'utf-8'` ) – Text encoding, any name accepted by codecs.
- **`errors`** (`str`, default: `'strict'` ) – Error handler: "strict", "ignore", "replace", "backslashreplace". See codecs.register_error for custom handlers.

Returns:

- `str` – The file content as str.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path is empty, or if path names a directory.
- `UnicodeDecodeError` – If decoding fails with errors="strict".

Equivalent to `read_bytes(path).decode(encoding, errors)`.

______________________________________________________________________

## Writing

Requires `Capability.WRITE`

`write()` and `write_text()` raise `CapabilityNotSupported` on backends that do not declare this capability. Most backends declare it. `write_atomic()` and `open_atomic()` additionally require `Capability.ATOMIC_WRITE`.

Quality flag: `Capability.WRITE_RESULT_NATIVE`

When declared, the returned `WriteResult` fields (`etag`, `version_id`, `last_modified`, `digest`) are populated from the backend's write response. Without it, only locally computable fields are set.

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

Write binary content to *path*. Creates parent folders implicitly.

Parameters:

- **`path`** (`str`) – Store-relative file path.
- **`content`** (`WritableContent`) – bytes or readable binary stream (BinaryIO).
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when path exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-supplied key/value pairs to store alongside the file. Requires Capability.USER_METADATA. Keys must be non-empty ASCII strings with no leading underscore; total payload must not exceed 2048 bytes.

Returns:

- `WriteResult` – WriteResult with at least path and size populated.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path is empty.
- `ValueError` – If metadata fails shape validation (keys and values must be str with bounded total size).
- `CapabilityNotSupported` – If metadata is non-empty and the backend lacks USER_METADATA.

Backend-conditional argument: `metadata=`

Passing `metadata` raises `CapabilityNotSupported` on backends that do not declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

### write_text

```
write_text(
    path: str,
    text: str,
    *,
    encoding: str = "utf-8",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write a string to *path*, encoded with the given encoding.

Parameters:

- **`path`** (`str`) – Store-relative file path.
- **`text`** (`str`) – The string to write.
- **`encoding`** (`str`, default: `'utf-8'` ) – Text encoding.
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when path exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-supplied key/value pairs (see write()).

Returns:

- `WriteResult` – WriteResult.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path is empty.

Equivalent to `write(path, text.encode(encoding), overwrite=overwrite, metadata=metadata)`.

Backend-conditional argument: `metadata=`

Passing `metadata` raises `CapabilityNotSupported` on backends that do not declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

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

Write binary content to *path* atomically.

If the write fails or is interrupted, *path* is not left in a partial state.

Parameters:

- **`path`** (`str`) – Store-relative file path.
- **`content`** (`WritableContent`) – bytes or readable binary stream (BinaryIO).
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when path exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-supplied key/value pairs (see write()).

Returns:

- `WriteResult` – WriteResult.

Raises:

- `CapabilityNotSupported` – If backend lacks ATOMIC_WRITE.
- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path is empty.

Requires `Capability.ATOMIC_WRITE`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

Backend-conditional argument: `metadata=`

Passing `metadata` raises `CapabilityNotSupported` on backends that do not declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

Info

Most backends implement this as temp-file + rename. See the [Backend Behavior Matrix](#backend-behavior-matrix) for details.

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]
```

Context manager that yields a writable binary stream.

The file is committed atomically on successful exit; on exception the partial write is discarded.

Parameters:

- **`path`** (`str`) – Store-relative file path.
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when path exists.

Returns:

- `Iterator[BinaryIO]` – Writable binary stream.

Raises:

- `CapabilityNotSupported` – If the backend lacks ATOMIC_WRITE.
- `AlreadyExists` – If path exists and overwrite is False.
- `InvalidPath` – If path is empty.

```
with store.open_atomic("data/output.bin", overwrite=True) as f:
    f.write(b"chunk 1")
    f.write(b"chunk 2")
# file is now visible at data/output.bin
```

Requires `Capability.ATOMIC_WRITE`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

______________________________________________________________________

## Deleting

Requires `Capability.DELETE`

All delete methods raise `CapabilityNotSupported` on backends that do not declare this capability.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete a single file.

Parameters:

- **`path`** (`str`) – Store-relative file path.
- **`missing_ok`** (`bool`, default: `False` ) – If True, silently succeeds when path does not exist.

Raises:

- `NotFound` – If the file is missing and missing_ok is False.
- `InvalidPath` – If path is empty, or if path names a directory (regardless of missing_ok).

### delete_folder

```
delete_folder(
    path: str,
    *,
    recursive: bool = False,
    missing_ok: bool = False,
) -> None
```

Delete a folder.

Parameters:

- **`path`** (`str`) – Store-relative folder path. Must not be "" (root).
- **`recursive`** (`bool`, default: `False` ) – If True, delete all contents first. If False, raises DirectoryNotEmpty when folder is non-empty.
- **`missing_ok`** (`bool`, default: `False` ) – If True, silently succeeds when path does not exist.

Raises:

- `NotFound` – If the folder is missing and missing_ok is False.
- `DirectoryNotEmpty` – If the folder is non-empty and recursive is False.
- `InvalidPath` – If path is empty (cannot delete the store root), or if path names a file (use delete instead).

______________________________________________________________________

## Listing and Iteration

Requires `Capability.LIST`

All listing methods raise `CapabilityNotSupported` on backends that do not declare this capability.

### list_files

```
list_files(
    path: str,
    *,
    recursive: bool = False,
    pattern: str | None = None,
    max_depth: int | None = None,
) -> Iterator[FileInfo]
```

Yield `FileInfo` objects for files under *path*.

Parameters:

- **`path`** (`str`) – Store-relative folder path.
- **`recursive`** (`bool`, default: `False` ) – Descend into subfolders. Ignored when max_depth is set.
- **`pattern`** (`str | None`, default: `None` ) – Glob pattern to filter filenames (e.g. "\*.csv"). Matched against each file's name (basename only). For full path-based patterns, use ext.glob.glob_files().
- **`max_depth`** (`int | None`, default: `None` ) – Maximum folder depth to include. 0 means files directly in path only; 1 adds files in its immediate subfolders, and so on. None (default) defers to recursive. When set, recursive is ignored.

Returns:

- `Iterator[FileInfo]` – Iterator of FileInfo with store-relative paths.

Raises:

- `ValueError` – If max_depth is negative.

Backend-conditional argument: `max_depth=`

Backends with native depth limiting prune traversal early. Backends that do not support it still return correct results — the Store applies client-side filtering as a safety net.

### list_folders

```
list_folders(
    path: str,
    *,
    pattern: str | None = None,
    max_depth: int | None = None,
) -> Iterator[FolderEntry]
```

Yield subfolders of *path* as `FolderEntry` objects.

Parameters:

- **`path`** (`str`) – Store-relative folder path.
- **`pattern`** (`str | None`, default: `None` ) – Glob pattern to filter folder names (e.g. "raw\_\*"). Matched against each folder's name (basename only) via fnmatch.fnmatch. Filters yielded results only — does not prune BFS traversal, so non-matching folders are still descended into.
- **`max_depth`** (`int | None`, default: `None` ) – Maximum folder depth to include. None or 0 returns immediate children only (default). 1 adds grandchildren, and so on. BFS traversal runs first; pattern filters what is yielded.

Returns:

- `Iterator[FolderEntry]` – Iterator of FolderEntry with .name and .path (store-relative).

Raises:

- `ValueError` – If max_depth is negative.

Backend-conditional argument: `max_depth=`

Backends with native depth limiting prune traversal early. Backends that do not support it still return correct results — the Store applies client-side filtering as a safety net.

### iter_children

```
iter_children(
    path: str,
) -> Iterator[FileInfo | FolderEntry]
```

Yield all immediate children (files and folders) of *path* in a single pass.

Files are yielded as `FileInfo`, folders as `FolderEntry`. Both have `.name` and `.path` attributes (satisfying the `PathEntry` protocol) so callers can iterate uniformly.

Parameters:

- **`path`** (`str`) – Store-relative folder path.

Returns:

- `Iterator[FileInfo | FolderEntry]` – Iterator of FileInfo (files) and FolderEntry (folders).

### glob

```
glob(pattern: str) -> Iterator[FileInfo]
```

Yield files matching a glob *pattern*, using the backend's native glob implementation.

Requires `Capability.GLOB`.

Parameters:

- **`pattern`** (`str`) – Glob pattern (e.g. "data/\*\*/\*.parquet").

Returns:

- `Iterator[FileInfo]` – Iterator of FileInfo with store-relative paths.

Raises:

- `CapabilityNotSupported` – If the backend lacks GLOB.

Requires `Capability.GLOB`

`glob()` raises `CapabilityNotSupported` on backends that do not declare this capability. Check `store.supports(Capability.GLOB)` before calling.

Ordering and laziness

**Ordering is backend-defined** and may vary between backends (e.g. lexicographic on S3, OS-dependent on local filesystems). Callers must not depend on any particular order.

**Results are yielded lazily.** Backends may use pagination internally. Memory usage stays bounded for large directories.

______________________________________________________________________

## File Operations

Requires `Capability.MOVE` / `Capability.COPY`

`move()` requires `Capability.MOVE`; `copy()` requires `Capability.COPY`. Each raises `CapabilityNotSupported` on backends that do not declare the respective capability.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move (rename) a file from *src* to *dst*.

File-only -- to move a folder, iterate its contents.

Parameters:

- **`src`** (`str`) – Source file path.
- **`dst`** (`str`) – Destination file path.
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when dst exists.

Raises:

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists and overwrite is False.
- `InvalidPath` – If src or dst is empty, or if src names a directory.

Requires `Capability.MOVE`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

Atomicity

Atomicity is backend-dependent. Local uses `os.replace` (atomic on same filesystem). S3 and Azure use copy-then-delete (not atomic). SFTP atomicity depends on the server. Check `store.supports(Capability.ATOMIC_MOVE)` to query this at runtime.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy a file from *src* to *dst*.

File-only -- to copy a folder, iterate its contents.

Parameters:

- **`src`** (`str`) – Source file path.
- **`dst`** (`str`) – Destination file path.
- **`overwrite`** (`bool`, default: `False` ) – If False, raises AlreadyExists when dst exists.

Raises:

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists and overwrite is False.
- `InvalidPath` – If src or dst is empty, or if src names a directory.

Requires `Capability.COPY`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

Metadata preservation

Metadata preservation is backend-dependent. S3 copies metadata; local preserves metadata (`copy2`); SFTP does not (stream copy).

______________________________________________________________________

## Metadata

Partially requires `Capability.METADATA`

`head()` and `get_file_info()` require `Capability.METADATA`. `get_folder_info()` requires `Capability.METADATA` without `max_depth`, or `Capability.LIST` when `max_depth` is set. `exists()`, `is_file()`, and `is_folder()` are always available.

### head

```
head(path: str) -> WriteResult
```

Return a `WriteResult` snapshot of *path* via a metadata lookup.

Gated on `Capability.METADATA` only — works on read-only backends that declare `METADATA`. The returned `WriteResult` has `source="sidecar"` (populated from a `get_file_info()` call, not from a write response).

Parameters:

- **`path`** (`str`) – Store-relative file path.

Returns:

- `WriteResult` – WriteResult with source="sidecar".

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path is empty, or if path names a directory.
- `CapabilityNotSupported` – If the backend lacks METADATA.

Requires `Capability.METADATA`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

### exists

```
exists(path: str) -> bool
```

Return `True` if *path* exists (file or folder).

Never raises `NotFound` — returns `False` for missing paths instead. Also returns `False` if any ancestor of *path* is a file (file-as-directory-component), as traversal cannot proceed.

Parameters:

- **`path`** (`str`) – Store-relative path.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* exists and is a file.

Returns `False` if any ancestor of *path* is a file (file-as-directory-component).

Parameters:

- **`path`** (`str`) – Store-relative path.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* exists and is a folder.

Returns `False` if any ancestor of *path* is a file (file-as-directory-component).

Parameters:

- **`path`** (`str`) – Store-relative path.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return a `FileInfo` with size, modification time, and content type for a single file.

Parameters:

- **`path`** (`str`) – Store-relative file path.

Returns:

- `FileInfo` – FileInfo.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path is empty, or if path names a directory.

Requires `Capability.METADATA`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

### get_folder_info

```
get_folder_info(
    path: str, *, max_depth: int | None = None
) -> FolderInfo
```

Return a `FolderInfo` with aggregated size and file count for a folder.

Parameters:

- **`path`** (`str`) – Store-relative folder path.
- **`max_depth`** (`int | None`, default: `None` ) – Maximum folder depth to aggregate. 0 means files directly in path only; 1 adds files in its immediate subfolders, and so on. None (default) performs a full recursive traversal via the backend.

Returns:

- `FolderInfo` – FolderInfo.

Raises:

- `NotFound` – If the folder does not exist.
- `InvalidPath` – If path names a file (use get_file_info instead).
- `ValueError` – If max_depth is negative.

Capability depends on `max_depth`

Without `max_depth`: requires `Capability.METADATA`. With `max_depth` set: requires `Capability.LIST` — works on backends that lack `METADATA`.

Backend-conditional argument: `max_depth=`

Backends with native depth limiting prune traversal early. Backends that do not support it still return correct results — the Store applies client-side filtering as a safety net.

______________________________________________________________________

## Introspection

### resolve

```
resolve(key: str) -> ResolutionPlan
```

Return a `ResolutionPlan` describing how *key* maps to storage.

Delegates to the backend's `resolve()` and rebases the key so that `plan.key` is the store-relative key, not the backend-relative path.

Parameters:

- **`key`** (`str`) – Store-relative path. "" resolves the store root.

Returns:

- `ResolutionPlan` – A frozen ResolutionPlan.

Info

`resolve()` is a pure introspection method — it performs no I/O and is never called implicitly by other Store methods. The returned [`ResolutionPlan`](https://docs.remotestore.dev/stable/reference/api/models/index.md) describes how a key maps to its storage location.

______________________________________________________________________

## Lifecycle

### ping

```
ping() -> None
```

Verify that the backend is reachable.

Raises:

- `PermissionDenied` – If credentials are invalid.
- `NotFound` – If the bucket, container, or root path does not exist.
- `BackendUnavailable` – If the backend cannot be reached.

### close

```
close() -> None
```

Release backend resources.

Called automatically when used as a context manager.

### child

```
child(subpath: str) -> Store
```

Return a new `Store` scoped to *subpath* under the current root.

The child shares the same backend instance.

Parameters:

- **`subpath`** (`str`) – Path segment to append to the current root.

Returns:

- `Store` – Store.

Raises:

- `InvalidPath` – If subpath is empty, contains .. segments, or includes null bytes.

```
data = store.child("data/2024")
data.list_files("")  # lists files under <root>/data/2024/
```

______________________________________________________________________

## Interop (Backend-Specific)

Backend-specific methods

Methods in this section expose backend internals. Using them ties your code to a specific backend. For portable alternatives, use the methods above.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return the backend's native client object, cast to *type_hint*.

Parameters:

- **`type_hint`** (`type[T]`) – The expected type of the native client (e.g. pyarrow.fs.FileSystem).

Returns:

- `T` – The native client.

Raises:

- `CapabilityNotSupported` – If the backend cannot provide the requested type.

```
arrow_fs = store.unwrap(pyarrow.fs.FileSystem)
```

### native_path

```
native_path(key: str) -> str
```

Convert a store-relative *key* to the backend's native path representation.

Inverse of `to_key()`.

Parameters:

- **`key`** (`str`) – Store-relative path.

Returns:

- `str` – Backend-native path (e.g. S3 object key, local filesystem path).

### to_key

```
to_key(path: str) -> str
```

Convert a backend-native *path* to a store-relative key.

Inverse of `native_path()`.

Parameters:

- **`path`** (`str`) – Backend-native path string.

Returns:

- `str` – Store-relative key.

Raises:

- `InvalidPath` – If the path does not belong to this store.

### supports

```
supports(capability: Capability) -> bool
```

Check whether the backend supports a given `Capability`.

Parameters:

- **`capability`** (`Capability`) – A Capability enum member.

Returns:

- `bool` – True if the backend declares this capability.

```
if store.supports(Capability.GLOB):
    results = store.glob("**/*.csv")
```

Info

`supports()` itself is portable — it works on all backends. Only the capability-gated methods it guards are backend-specific.

______________________________________________________________________

## Backend Behavior Matrix

How key operations behave across backends. Verify against actual code before relying on these in production.

| Behavior                    | [Local](https://docs.remotestore.dev/stable/guides/backends/local/index.md) | [Memory](https://docs.remotestore.dev/stable/guides/backends/memory/index.md) | [S3](https://docs.remotestore.dev/stable/guides/backends/s3/index.md) | [S3-PyArrow](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md) | [Azure](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) | [Graph](https://docs.remotestore.dev/stable/guides/backends/graph/index.md)¹ | [SFTP](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md) | [HTTP](https://docs.remotestore.dev/stable/guides/backends/http/index.md) | [SQLBlob](https://docs.remotestore.dev/stable/guides/backends/sql-blob/index.md) | [SQLQuery](https://docs.remotestore.dev/stable/guides/backends/sql-query/index.md) |
| --------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `move()` atomicity          | Atomic (same FS)                                                            | Atomic                                                                        | Copy+delete                                                           | Copy+delete                                                                           | Copy+delete                                                                 | Server-side, not atomic                                                      | Server-dependent                                                          | —                                                                         | Atomic (SQL transaction)                                                         | —                                                                                  |
| `copy()` preserves metadata | Yes (`copy2`)                                                               | —                                                                             | Yes                                                                   | Yes                                                                                   | Yes                                                                         | —                                                                            | —                                                                         | —                                                                         | Yes                                                                              | —                                                                                  |
| `write_atomic()` mechanism  | temp+rename                                                                 | Direct (atomic)                                                               | Direct PUT (atomic)                                                   | Direct PUT (atomic)                                                                   | Direct PUT or temp+rename                                                   | Direct PUT / upload session (service-atomic)                                 | temp+rename                                                               | —                                                                         | Direct (atomic)                                                                  | —                                                                                  |
| Native `glob()`             | Yes                                                                         | —                                                                             | Yes                                                                   | Yes                                                                                   | Yes                                                                         | —                                                                            | —                                                                         | —                                                                         | Yes (SQL GLOB/LIKE)                                                              | Yes (in-memory)                                                                    |
| `list_files()` ordering     | OS-dependent                                                                | Insertion order                                                               | Lexicographic                                                         | Lexicographic                                                                         | Lexicographic                                                               | Service-dependent                                                            | OS-dependent                                                              | —                                                                         | DB-dependent                                                                     | Lexicographic                                                                      |

¹ Graph is **async-only** — it has no sync `Store` wrapper. Its column describes the behavior seen through [`AsyncStore`](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md), or through [`AsyncBackendSyncAdapter`](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md) when driven from sync code.

## See also

- [Getting Started](https://docs.remotestore.dev/stable/tutorial/getting-started/index.md) — step-by-step guide to reading and writing files
- [Concurrency](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) — thread safety, atomic writes, and move semantics
- [Quickstart example](https://docs.remotestore.dev/stable/tutorial/examples/quickstart/index.md) — minimal config, write, and read
