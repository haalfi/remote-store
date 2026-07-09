# Backend

## Backend

Bases: `ABC`

Abstract base class for all storage backends.

Every backend must implement all abstract methods. Backend-native exceptions must never leak — they must be mapped to `remote_store` errors.

Implementing a backend

Subclass `Backend` and implement all abstract methods. Map every backend-native exception to a `remote_store` error — native exceptions must never leak to callers.

______________________________________________________________________

## Identity

### name

```
name: str
```

Unique identifier for this backend type (e.g. `'local'`, `'s3'`).

### capabilities

```
capabilities: CapabilitySet
```

Declared capabilities of this backend.

______________________________________________________________________

## Checking Existence

### exists

```
exists(path: str) -> bool
```

Check if a file or folder exists. Never raises `NotFound`.

Returns `False` if any ancestor of *path* is a file (file-as-directory-component), as traversal cannot proceed.

Parameters:

- **`path`** (`str`) – Backend-relative key, or "" for the root.

Returns:

- `bool` – True if a file or folder exists at path. False if the path
- `bool` – does not exist or if any ancestor is a file instead of a directory.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if `path` is an existing file.

Returns `False` if the path does not exist, or if any ancestor of *path* is a file (file-as-directory-component).

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `bool` – True if path exists and is a file. False if the path does not
- `bool` – exist or if any ancestor is a file instead of a directory.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if `path` is an existing folder.

Returns `False` if the path does not exist, or if any ancestor of *path* is a file (file-as-directory-component).

Parameters:

- **`path`** (`str`) – Backend-relative key, or "" for the root.

Returns:

- `bool` – True if path exists and is a folder. False if the path does not
- `bool` – exist or if any ancestor is a file instead of a directory.

______________________________________________________________________

## Reading

Requires `Capability.READ`

All read methods raise `CapabilityNotSupported` on backends that do not declare this capability. Most backends declare it.

### read

```
read(path: str) -> BinaryIO
```

Open a file for reading and return a binary stream.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `BinaryIO` – A readable binary stream.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory, not a file.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read the full content of a file as bytes.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `bytes` – The file content.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory, not a file.

### read_seekable

```
read_seekable(path: str) -> BinaryIO
```

Open a file for random-access reading and return a seekable stream.

The default implementation delegates to `read()`. If the returned stream is already seekable, it is returned as-is. Otherwise, the stream is spooled into a `SpooledTemporaryFile` (up to 8 MB in RAM, beyond that on disk) and returned positioned at byte 0.

Backends MAY override to provide an optimized implementation. For example, `AzureBackend` returns a range reader that issues HTTP Range requests on each `read()` call.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `BinaryIO` – A seekable binary stream positioned at byte 0.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory, not a file.

Default implementation

The default spools the stream into a `SpooledTemporaryFile` (up to 8 MB in RAM, beyond that on disk) when the backend stream is not already seekable. Override for efficiency when the backend supports range reads.

______________________________________________________________________

## Writing

Requires `Capability.WRITE`

`write()` raises `CapabilityNotSupported` on backends that do not declare this capability. Most backends declare it.

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

Write content to a file.

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`content`** (`WritableContent`) – Data to write.
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-supplied key/value pairs to store alongside the file. Only honoured when the backend declares USER_METADATA.

Returns:

- `WriteResult` – A WriteResult with at least path and size populated.
- `WriteResult` – Backends declaring WRITE_RESULT_NATIVE also populate etag,
- `WriteResult` – last_modified, and where available digest and version_id.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or if any slash-aligned ancestor of path exists as a regular file. Flat-namespace backends (S3, Azure non-HNS, SQL) cannot detect a file ancestor in O(1) and skip the check by default; the per-backend reject_write_under_file_ancestor opt-in enables it.

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

Write content atomically via temp file + rename.

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`content`** (`WritableContent`) – Data to write.
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-supplied key/value pairs (see write()).

Returns:

- `WriteResult` – A WriteResult (same contract as write()).

Raises:

- `CapabilityNotSupported` – If backend lacks ATOMIC_WRITE.
- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or if any slash-aligned ancestor of path exists as a regular file (see write).

Requires `Capability.ATOMIC_WRITE`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

Backend-conditional argument: `metadata=`

Passing `metadata` raises `CapabilityNotSupported` on backends that do not declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> AbstractContextManager[BinaryIO]
```

Yield a writable file object backed by a temporary location.

On successful exit the temp file is atomically promoted to *path*. On exception the temp file is removed and *path* is untouched.

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.

Raises:

- `AlreadyExists` – If path exists and overwrite is False.
- `InvalidPath` – If path names a directory, or if any slash-aligned ancestor of path exists as a regular file (see write).
- `CapabilityNotSupported` – If the backend lacks ATOMIC_WRITE.

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

Delete a file.

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`missing_ok`** (`bool`, default: `False` ) – If True, do not raise when the file is absent.

Raises:

- `NotFound` – If the file is missing and missing_ok is False.
- `InvalidPath` – If path names a directory (type mismatch is not silenced by missing_ok).

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

- **`path`** (`str`) – Backend-relative key.
- **`recursive`** (`bool`, default: `False` ) – If True, delete all contents first.
- **`missing_ok`** (`bool`, default: `False` ) – If True, do not raise when absent.

Raises:

- `NotFound` – If the folder is missing and missing_ok is False.
- `InvalidPath` – If path names a file, not a folder.
- `DirectoryNotEmpty` – If non-empty and recursive is False.

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
    max_depth: int | None = None,
) -> Iterator[FileInfo]
```

List files under `path`.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.
- **`recursive`** (`bool`, default: `False` ) – If True, include files in all subdirectories.
- **`max_depth`** (`int | None`, default: `None` ) – Optional maximum folder depth to traverse. When set, backends that support native depth limiting prune traversal early. Backends that ignore this parameter still produce correct results — the Store applies client-side filtering as a safety net. None (default) defers to recursive.

Returns:

- `Iterator[FileInfo]` – An iterator of FileInfo objects.

Backend-conditional argument: `max_depth=`

Backends with native depth limiting prune traversal early. Backends that do not support it still return correct results — the Store applies client-side filtering as a safety net.

### list_folders

```
list_folders(path: str) -> Iterator[FolderEntry]
```

List immediate subfolders under `path`.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.

Returns:

- `Iterator[FolderEntry]` – An iterator of FolderEntry objects with .name and .path.

### iter_children

```
iter_children(
    path: str,
) -> Iterator[FileInfo | FolderEntry]
```

Yield both files and folders under `path` in a single pass.

Files are yielded as `FileInfo` objects, folders as `FolderEntry` objects. The default implementation chains `list_files()` and `list_folders()`. Backends that can fetch both in a single I/O call should override this for efficiency.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.

Returns:

- `Iterator[FileInfo | FolderEntry]` – An iterator of FileInfo (files) and FolderEntry (folders).

Default implementation

Chains `list_files()` then `list_folders()`. Override when the backend can fetch both in a single I/O call.

### glob

```
glob(pattern: str) -> Iterator[FileInfo]
```

Match files against a glob pattern.

Non-abstract — backends with native glob support override this and add `Capability.GLOB` to their capability set.

Parameters:

- **`pattern`** (`str`) – Glob pattern (e.g., "data/\*.csv", "\*\*/\*.txt").

Raises:

- `CapabilityNotSupported` – If the backend lacks GLOB.

Requires `Capability.GLOB`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

Non-abstract

The default raises `CapabilityNotSupported`. Backends that provide native glob support override this and declare `Capability.GLOB`.

______________________________________________________________________

## Metadata

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Get metadata for a file.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `FileInfo` – A FileInfo with size, modification time, etc.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory, not a file.

Requires `Capability.METADATA`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Get metadata for a folder.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.

Returns:

- `FolderInfo` – A FolderInfo with file count, total size, etc.

Raises:

- `NotFound` – If the folder does not exist.
- `InvalidPath` – If path names a file, not a folder.

Requires `Capability.METADATA`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

______________________________________________________________________

## File Operations

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename a file.

When `src == dst` the call is a no-op (data preserved).

Parameters:

- **`src`** (`str`) – Backend-relative source key.
- **`dst`** (`str`) – Backend-relative destination key.
- **`overwrite`** (`bool`, default: `False` ) – If True, replace any existing file at dst.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or if any slash-aligned ancestor of dst exists as a regular file.
- `AlreadyExists` – If dst exists and overwrite is False.

Requires `Capability.MOVE`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy a file.

When `src == dst` the call is a no-op (data preserved).

Parameters:

- **`src`** (`str`) – Backend-relative source key.
- **`dst`** (`str`) – Backend-relative destination key.
- **`overwrite`** (`bool`, default: `False` ) – If True, replace any existing file at dst.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or if any slash-aligned ancestor of dst exists as a regular file.
- `AlreadyExists` – If dst exists and overwrite is False.

Requires `Capability.COPY`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

______________________________________________________________________

## Introspection

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` describing how *path* maps to storage.

Pure introspection -- no I/O is performed. Backends override this to populate `details` with backend-specific context.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – A frozen ResolutionPlan with kind, backend,
- `ResolutionPlan` – key, native_path, and details.

______________________________________________________________________

## Lifecycle

### check_health

```
check_health() -> None
```

Verify the backend is reachable and credentials are valid.

The default implementation is a no-op (always succeeds). Backends override this to perform a lightweight, non-destructive connectivity check using the cheapest possible read-only operation.

Raises:

- `PermissionDenied` – If credentials are invalid.
- `NotFound` – If the bucket, container, or root path does not exist.
- `BackendUnavailable` – If the backend cannot be reached.

### close

```
close() -> None
```

Release resources. Default is a no-op.

Whether the backend may be reused afterwards is the `close_is_terminal` posture: the default backend is reusable; terminal backends raise `BackendUnavailable` on use-after-close.

______________________________________________________________________

## Interop (Backend-Specific)

Backend-specific methods

Methods in this section expose backend internals. Using them ties your code to a specific backend. For portable alternatives, use the methods above.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return the native backend handle if it matches the requested type.

Parameters:

- **`type_hint`** (`type[T]`) – The expected type (e.g., fsspec.AbstractFileSystem).

Raises:

- `CapabilityNotSupported` – If backend cannot provide the requested type.

### native_path

```
native_path(path: str) -> str
```

Convert a backend-relative key to the backend-native path.

The inverse of `to_key()`. The default implementation is the identity function — backends with a native root (bucket, base_path) override this to prepend their prefix.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `str` – Backend-native path usable with the native handle from unwrap().

### to_key

```
to_key(native_path: str) -> str
```

Convert a backend-native path to a backend-relative key.

Strips the backend's own root/prefix from the path. The default implementation is the identity function — backends with a native root (filesystem path, bucket prefix, base_path) override this.

Parameters:

- **`native_path`** (`str`) – Absolute or backend-native path string.

Returns:

- `str` – Path relative to the backend's root.

**Related types:** [`CapabilitySet`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md), [`FileInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md), [`FolderInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md), [`FolderEntry`](https://docs.remotestore.dev/stable/reference/api/models/index.md), [`ResolutionPlan`](https://docs.remotestore.dev/stable/reference/api/models/index.md).

## See also

- [Build Your Own Backend](https://docs.remotestore.dev/stable/guides/custom-backend-guide/index.md) — step-by-step guide to implementing a custom backend
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — per-backend capability comparison
- [Errors](https://docs.remotestore.dev/stable/reference/api/errors/index.md) — error types backends must raise
