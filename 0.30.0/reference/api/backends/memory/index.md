# MemoryBackend

API reference for `MemoryBackend` — stores files in an in-process data structure. No filesystem access, no network. Ideal for testing and prototyping.

## MemoryBackend

```
MemoryBackend()
```

In-memory backend using a tree-indexed data structure.

Zero dependencies, no filesystem access, no network. Designed as a drop-in backend for unit testing, interactive exploration, and documentation examples.

All capabilities except `GLOB` are supported. The full conformance suite passes with zero skips.

Every mutating operation runs under a single process-wide lock, so `write`, `write_atomic`, `move`, and `copy` are atomic with respect to concurrent callers in the same process (`ATOMIC_MOVE` is advertised).

### exists

```
exists(path: str) -> bool
```

Return `True` if a file or folder exists at *path*; never `NotFound`.

The root (`""`) always exists.

Raises:

- `InvalidPath` – If path is absolute or contains a .. segment.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* is an existing file (`False` for the root or a folder).

Raises:

- `InvalidPath` – If path is absolute or contains a .. segment.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* is an existing folder; the root is always a folder.

Raises:

- `InvalidPath` – If path is absolute or contains a .. segment.

### read

```
read(path: str) -> BinaryIO
```

Return a binary stream over the stored bytes for *path*.

The value materialises in memory rather than streaming (`LAZY_READ` is not advertised): the returned stream wraps a copy of the resident bytes, so peak memory scales with the object size. Access is guarded by a single process-wide lock.

Raises:

- `NotFound` – If no file exists at path.
- `InvalidPath` – If path names a folder.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Return the full stored content of *path* as bytes.

Copies the resident value out under the lock; like `read` it holds the whole object in memory.

Raises:

- `NotFound` – If no file exists at path.
- `InvalidPath` – If path names a folder.

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

Store *content* at *path*, creating parent folders implicitly.

The whole body is buffered into memory before the store (streams are drained fully first — no lazy write), and the swap-in happens under a single process-wide lock, so the write is atomic with respect to concurrent callers in the same process.

Raises:

- `AlreadyExists` – If a file exists at path and overwrite is False.
- `InvalidPath` – If path is empty or names a folder, or an ancestor of path exists as a file.

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

Store *content* at *path* atomically (delegates to `write`).

Memory writes are already atomic under the process-wide lock, so this is exactly `write`; the whole body is buffered first.

Raises:

- `AlreadyExists` – If a file exists at path and overwrite is False.
- `InvalidPath` – If path is empty or names a folder, or an ancestor of path exists as a file.

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]
```

Yield an in-memory buffer committed to *path* atomically on clean exit.

Writes accumulate in a `BytesIO`; on exit the buffer is stored via `write` under the process-wide lock, so *path* updates in one atomic step. An exception before exit leaves *path* untouched.

Raises:

- `AlreadyExists` – If a file exists at path and overwrite is False.
- `InvalidPath` – If path is empty, or (on commit) names a folder or has a file ancestor.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete the file at *path*.

Raises:

- `NotFound` – If no file exists at path and missing_ok is False.
- `InvalidPath` – If path is empty or names a folder (a type mismatch missing_ok does not silence).

### delete_folder

```
delete_folder(
    path: str,
    *,
    recursive: bool = False,
    missing_ok: bool = False,
) -> None
```

Delete the folder at *path*.

`recursive=True` detaches the whole subtree in one locked step; `recursive=False` removes only an empty folder.

Raises:

- `NotFound` – If no folder exists at path and missing_ok is False.
- `InvalidPath` – If path is empty or names a file.
- `DirectoryNotEmpty` – If the folder is non-empty and recursive is False.

### list_files

```
list_files(
    path: str,
    *,
    recursive: bool = False,
    max_depth: int | None = None,
) -> Iterator[FileInfo]
```

Yield files under *path*.

A missing or non-folder *path* yields nothing. The tree is snapshotted under the lock and iterated outside it, so a long listing does not hold the lock; `recursive` walks the whole subtree (`max_depth` prunes it).

### list_folders

```
list_folders(path: str) -> Iterator[FolderEntry]
```

Yield immediate subfolders of *path* as `FolderEntry` records.

A missing or non-folder *path* yields nothing; children are snapshotted under the lock and yielded outside it.

### iter_children

```
iter_children(
    path: str,
) -> Iterator[FileInfo | FolderEntry]
```

Yield the immediate files and folders under *path* in one snapshot.

Overrides the base two-pass default: takes one locked snapshot of the directory and yields `FileInfo` for files and `FolderEntry` for folders. A missing or non-folder *path* yields nothing.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return metadata for the file at *path* from the in-memory node.

Raises:

- `NotFound` – If no file exists at path (including the empty path).
- `InvalidPath` – If path names a folder.

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Return aggregate metadata for the folder at *path*.

File count, total size, and latest modification time are computed by walking the whole subtree, so cost scales with the number of descendants.

Raises:

- `NotFound` – If no folder exists at path.
- `InvalidPath` – If path names a file.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename the file *src* to *dst* by re-linking the tree node.

Detach-from-source and attach-to-destination happen in one locked step, so the move is atomic with respect to concurrent callers (`ATOMIC_MOVE` is advertised) and the payload is never copied. `src == dst` verifies the source is a file and is otherwise a no-op.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst is empty, src names a folder, or dst names an existing folder.
- `AlreadyExists` – If dst is an existing file and overwrite is False.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy the file *src* to *dst* with an independent byte buffer.

The destination receives a fresh `bytearray` copy of the source bytes, all in one locked step (atomic). `src == dst` is a no-op.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst is empty, src names a folder, or dst names an existing folder.
- `AlreadyExists` – If dst is an existing file and overwrite is False.

## See also

- [Memory Backend Guide](https://docs.remotestore.dev/stable/guides/backends/memory/index.md) — usage patterns, configuration, and examples
- [Memory Backend example](https://docs.remotestore.dev/stable/tutorial/examples/memory-backend/index.md) — in-memory backend in action
