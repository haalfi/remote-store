# AsyncBackend

`AsyncBackend` is the abstract base class for native async backends — the async counterpart of [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md). Subclass it to implement a backend that talks to its store with `async`/`await`. It lives in `remote_store.aio`.

## AsyncBackend

Bases: `ABC`

Abstract base class for all async storage backends.

Every backend must implement all abstract methods. Backend-native exceptions must never leak -- they must be mapped to `remote_store` errors.

Implementing an async backend

Subclass `AsyncBackend` and implement all abstract methods. Map every backend-native exception to a `remote_store` error — native exceptions must never leak to callers.

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

## Existence

### exists

```
exists(path: str) -> bool
```

Check if a file or folder exists. Never raises `NotFound`.

Parameters:

- **`path`** (`str`) – Backend-relative key, or "" for the root.

Returns:

- `bool` – True if a file or folder exists at path.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if `path` is an existing file.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `bool` – True if path exists and is a file.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if `path` is an existing folder.

Parameters:

- **`path`** (`str`) – Backend-relative key, or "" for the root.

Returns:

- `bool` – True if path exists and is a folder.

## Reading

Requires `Capability.READ`

All read methods raise `CapabilityNotSupported` on backends that do not declare this capability. Most backends declare it.

### read

```
read(path: str) -> AsyncIterator[bytes]
```

Open a file for reading and return an async iterator of byte chunks.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `AsyncIterator[bytes]` – An async iterator yielding byte chunks.

Raises:

- `InvalidPath` – If path names an existing directory.
- `NotFound` – If the file does not exist.

Quality flag: `Capability.LAZY_READ`

When declared, data is fetched lazily — partial reads avoid loading the whole file. Without it, the backend may buffer content before returning the stream.

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

- `InvalidPath` – If path names an existing directory.
- `NotFound` – If the file does not exist.

## Writing

Requires `Capability.WRITE`

`write()` raises `CapabilityNotSupported` on backends that do not declare this capability. Most backends declare it. `write_atomic()` additionally requires `Capability.ATOMIC_WRITE`.

Quality flag: `Capability.WRITE_RESULT_NATIVE`

When declared, the returned `WriteResult` rich fields (`etag`, `version_id`, `last_modified`, `digest`) are populated from the backend's write response — each only when that response carries it, so a native backend may leave some, or even all, of them `None`. SFTP, for instance, declares the flag but its write response carries no metadata, so it returns every rich field `None` (call `get_file_info()` for the metadata). Without the flag, only locally computable fields are set.

### write

```
write(
    path: str,
    content: AsyncWritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write content to a file.

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`content`** (`AsyncWritableContent`) – Data to write.
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-defined string metadata.

Returns:

- `WriteResult` – A WriteResult with size, path, and optional native fields.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or if any slash-aligned ancestor of path exists as a regular file. Flat-namespace backends (S3, Azure non-HNS, SQL) cannot detect a file ancestor in O(1) and skip the check by default; the per-backend reject_write_under_file_ancestor opt-in enables it.

Backend-conditional argument: `metadata=`

Passing `metadata` raises `CapabilityNotSupported` on backends that do not declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

### write_atomic

```
write_atomic(
    path: str,
    content: AsyncWritableContent,
    *,
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult
```

Write content atomically via temp file + rename.

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`content`** (`AsyncWritableContent`) – Data to write.
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-defined string metadata.

Returns:

- `WriteResult` – A WriteResult with size, path, and optional native fields.

Raises:

- `CapabilityNotSupported` – If backend lacks ATOMIC_WRITE.
- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or if any slash-aligned ancestor of path exists as a regular file (see write).

Requires `Capability.ATOMIC_WRITE`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

Backend-conditional argument: `metadata=`

Passing `metadata` raises `CapabilityNotSupported` on backends that do not declare `Capability.USER_METADATA`. Passing `None` or `{}` is safe on all backends.

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
- `InvalidPath` – If the path is empty, or if path names a directory (regardless of missing_ok).

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

- `InvalidPath` – If path names an existing file (regardless of missing_ok — a type mismatch is not a missing file).
- `NotFound` – If the folder is missing and missing_ok is False.
- `DirectoryNotEmpty` – If non-empty and recursive is False.

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
) -> AsyncIterator[FileInfo]
```

List files under `path`.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.
- **`recursive`** (`bool`, default: `False` ) – If True, include files in all subdirectories.
- **`max_depth`** (`int | None`, default: `None` ) – Optional maximum folder depth to traverse. When set, backends that support native depth limiting prune traversal early. Backends that ignore this parameter still produce correct results -- the Store applies client-side filtering as a safety net. None (default) defers to recursive.

Returns:

- `AsyncIterator[FileInfo]` – An async iterator of FileInfo objects.

Backend-conditional argument: `max_depth=`

Backends with native depth limiting prune traversal early. Backends that do not support it still return correct results — the Store applies client-side filtering as a safety net.

### list_folders

```
list_folders(path: str) -> AsyncIterator[FolderEntry]
```

List immediate subfolders under `path`.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.

Returns:

- `AsyncIterator[FolderEntry]` – An async iterator of FolderEntry objects with .name and .path.

### iter_children

```
iter_children(
    path: str,
) -> AsyncIterator[FileInfo | FolderEntry]
```

Yield both files and folders under `path` in a single pass.

Files are yielded as `FileInfo` objects, folders as `FolderEntry` objects. The default implementation chains `list_files()` and `list_folders()`. Backends that can fetch both in a single I/O call should override this for efficiency.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.

Returns:

- `AsyncIterator[FileInfo | FolderEntry]` – An async iterator of FileInfo (files) and FolderEntry (folders).

### glob

```
glob(pattern: str) -> AsyncIterator[FileInfo]
```

Match files against a glob pattern.

Non-abstract -- backends with native glob support override this and add `Capability.GLOB` to their capability set.

Parameters:

- **`pattern`** (`str`) – Glob pattern (e.g., "data/\*.csv", "\*\*/\*.txt").

Raises:

- `CapabilityNotSupported` – If the backend lacks GLOB.

Requires `Capability.GLOB`

`glob()` raises `CapabilityNotSupported` on backends that do not declare this capability.

## Metadata

Requires `Capability.METADATA`

`get_file_info()` requires `Capability.METADATA`. `get_folder_info()` requires `Capability.METADATA` without `max_depth`, or `Capability.LIST` when `max_depth` is set.

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

- `InvalidPath` – If path names an existing directory.
- `NotFound` – If the file does not exist.

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

- `InvalidPath` – If path names an existing file.
- `NotFound` – If the folder does not exist.

Capability depends on `max_depth`

Without `max_depth`: requires `Capability.METADATA`. With `max_depth` set: requires `Capability.LIST` — works on backends that lack `METADATA`.

## File Operations

Requires `Capability.MOVE` / `Capability.COPY`

`move()` requires `Capability.MOVE`; `copy()` requires `Capability.COPY`. Each raises `CapabilityNotSupported` on backends that do not declare the respective capability.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename a file.

`src == dst` is a no-op (the file is preserved unchanged).

Parameters:

- **`src`** (`str`) – Backend-relative source key.
- **`dst`** (`str`) – Backend-relative destination key.
- **`overwrite`** (`bool`, default: `False` ) – If True, replace any existing file at dst.

Raises:

- `InvalidPath` – If src names a directory, dst names an existing directory, or any slash-aligned ancestor of dst exists as a regular file.
- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.

Requires `Capability.MOVE`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

Quality flag: `Capability.ATOMIC_MOVE`

When declared, `move()` is guaranteed atomic under concurrent access. Check `store.supports(Capability.ATOMIC_MOVE)` to query at runtime.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy a file.

`src == dst` is a no-op (the file is preserved unchanged).

Parameters:

- **`src`** (`str`) – Backend-relative source key.
- **`dst`** (`str`) – Backend-relative destination key.
- **`overwrite`** (`bool`, default: `False` ) – If True, replace any existing file at dst.

Raises:

- `InvalidPath` – If src names a directory, dst names an existing directory, or any slash-aligned ancestor of dst exists as a regular file.
- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.

Requires `Capability.COPY`

Raises `CapabilityNotSupported` on backends that do not declare this capability.

## Lifecycle

### aclose

```
aclose() -> None
```

Release resources. Default is a no-op.

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

The inverse of `to_key()`. The default implementation is the identity function -- backends with a native root (bucket, base_path) override this to prepend their prefix.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `str` – Backend-native path usable with the native handle from unwrap().

### to_key

```
to_key(native_path: str) -> str
```

Convert a backend-native path to a backend-relative key.

Strips the backend's own root/prefix from the path. The default implementation is the identity function -- backends with a native root (filesystem path, bucket prefix, base_path) override this.

Parameters:

- **`native_path`** (`str`) – Absolute or backend-native path string.

Returns:

- `str` – Path relative to the backend's root.

## See also

- [Backend](https://docs.remotestore.dev/stable/reference/api/backend/index.md) — synchronous counterpart
- [AsyncStore](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md) — the async Store that drives an `AsyncBackend`
- [Adapters](https://docs.remotestore.dev/stable/reference/api/aio/adapters/index.md) — bridge sync ↔ async backend implementations
- [Async Store Guide](https://docs.remotestore.dev/stable/guides/async/index.md) — usage patterns and FastAPI integration
