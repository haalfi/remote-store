# AsyncMemoryBackend

In-memory async backend using a tree-indexed data structure. Zero dependencies, no filesystem access, no network. Designed as a drop-in async backend for unit testing, interactive exploration, and documentation examples. Supports all capabilities except `GLOB`.

## AsyncMemoryBackend

```
AsyncMemoryBackend()
```

In-memory async backend using a tree-indexed data structure.

Zero dependencies, no filesystem access, no network. Designed as a drop-in async backend for unit testing, interactive exploration, and documentation examples.

Supports all capabilities except `GLOB`. The full conformance suite passes with zero skips.

Note

`LAZY_READ` is included here but absent from `MemoryBackend` (the sync mirror). The sync backend buffers fully in memory; the async backend can yield chunks incrementally. The `mirrors` graph edge between the two does not imply capability parity.

### exists

```
exists(path: str) -> bool
```

Check if a file or folder exists.

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

### read

```
read(path: str) -> AsyncIterator[bytes]
```

Open a file for reading and return an async iterator of byte chunks.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `AsyncIterator[bytes]` – An async iterator yielding a single byte chunk (the full content).

Raises:

- `InvalidPath` – If path names an existing directory.
- `NotFound` – If the file does not exist.

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
- **`content`** (`AsyncWritableContent`) – Data to write (bytes or async iterator of bytes).
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-defined string metadata.

Returns:

- `WriteResult` – WriteResult with path, size, last_modified, and
- `WriteResult` – source="native" populated.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory.

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

Write content atomically (same as write for in-memory backend).

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`content`** (`AsyncWritableContent`) – Data to write.
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-defined string metadata.

Returns:

- `WriteResult` – WriteResult with path, size, last_modified, and
- `WriteResult` – source="native" populated.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory.

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

- `NotFound` – If the folder is missing and missing_ok is False.
- `DirectoryNotEmpty` – If non-empty and recursive is False.
- `InvalidPath` – If the path is empty or names an existing file (regardless of missing_ok).

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
- **`max_depth`** (`int | None`, default: `None` ) – Optional maximum folder depth to traverse.

Returns:

- `AsyncIterator[FileInfo]` – An async iterator of FileInfo objects.

### list_folders

```
list_folders(path: str) -> AsyncIterator[FolderEntry]
```

List immediate subfolders under `path`.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.

Returns:

- `AsyncIterator[FolderEntry]` – An async iterator of FolderEntry objects.

### iter_children

```
iter_children(
    path: str,
) -> AsyncIterator[FileInfo | FolderEntry]
```

Yield both files and folders under `path` in a single pass.

Parameters:

- **`path`** (`str`) – Backend-relative folder key, or "" for the root.

Returns:

- `AsyncIterator[FileInfo | FolderEntry]` – An async iterator of FileInfo (files) and FolderEntry (folders).

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

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `InvalidPath` – If src or dst is empty, src names a directory, or dst names an existing directory.

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

- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `InvalidPath` – If src or dst is empty, src names a directory, or dst names an existing directory.

## See also

- [MemoryBackend](https://docs.remotestore.dev/stable/reference/api/backends/memory/index.md) — synchronous counterpart
- [Async Store Guide](https://docs.remotestore.dev/stable/guides/async/index.md) — usage patterns
