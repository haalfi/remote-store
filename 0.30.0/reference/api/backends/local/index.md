# LocalBackend

API reference for `LocalBackend` — stores files on the local filesystem. Built-in, no extra dependencies required.

## LocalBackend

```
LocalBackend(root: str)
```

Local filesystem backend using only the Python standard library.

`move()` uses `shutil.move`, which calls `os.rename` for same-filesystem moves (atomic) but falls back to copy-then-delete for cross-filesystem moves (not atomic). `ATOMIC_MOVE` is declared because within-root moves are always same-filesystem.

Parameters:

- **`root`** (`str`) – Absolute path to the root directory on the local filesystem.

### check_health

```
check_health() -> None
```

Confirm the root directory exists and is readable.

A lightweight two-syscall probe (`exists` then `os.access`) that touches no file content and is safe to call repeatedly.

Raises:

- `NotFound` – If the root directory does not exist.
- `PermissionDenied` – If the root directory exists but is not readable.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with local filesystem details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="local" and details containing
- `ResolutionPlan` – root and absolute_path.

### exists

```
exists(path: str) -> bool
```

Return `True` if a file or folder exists at *path*; never `NotFound`.

Returns `False` when a path component is itself a file, since the directory descent cannot proceed.

Raises:

- `InvalidPath` – If path escapes the backend root.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* is an existing regular file.

`False` if *path* is absent, names a directory, or has a file as an ancestor component.

Raises:

- `InvalidPath` – If path escapes the backend root.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* is an existing directory.

`False` if *path* is absent, names a file, or has a file as an ancestor component.

Raises:

- `InvalidPath` – If path escapes the backend root.

### read

```
read(path: str) -> BinaryIO
```

Open *path* for reading and return a lazy binary stream.

The stream reads on demand from the open file handle, so memory stays constant regardless of file size.

Raises:

- `NotFound` – If the file does not exist, or a path component is itself a file (the directory descent fails with ENOTDIR).
- `InvalidPath` – If path names a directory.
- `PermissionDenied` – If the OS denies read access to the file.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read and return the full file content as bytes.

Materialises the whole file in memory (unlike the lazy `read` stream), so size is bounded by available memory.

Raises:

- `NotFound` – If the file does not exist, or a path component is itself a file (ENOTDIR on descent).
- `InvalidPath` – If path names a directory.
- `PermissionDenied` – If the OS denies read access to the file.

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

Write *content* to *path*, creating parent directories as needed.

The bytes land directly at the final path (no temp-and-rename), so a crash or error mid-write can leave a partial or truncated file there — use `write_atomic` when readers must never observe a half-written file.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor of path exists as a regular file.
- `PermissionDenied` – If the OS denies write access.

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

Write *content* to *path* atomically via a temp file plus `os.replace`.

Readers never observe a partial file: the body is written to a temporary file in the destination directory and atomically renamed over *path* on success (the temp file is removed on error). The rename is atomic because the temp file shares *path*'s directory, hence its filesystem.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor of path exists as a regular file.
- `PermissionDenied` – If the OS denies write access.

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]
```

Yield a writable stream promoted to *path* atomically on clean exit.

Writes go to a temp file in *path*'s directory; on normal exit it is atomically renamed over *path* (`os.replace`), and on any exception the temp file is removed and *path* is left untouched. Readers therefore never see a partially written file.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor of path exists as a regular file.
- `PermissionDenied` – If the OS denies write access.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete the file at *path*.

Raises:

- `NotFound` – If the file does not exist (or a path component is itself a file) and missing_ok is False.
- `InvalidPath` – If path names a directory — a type mismatch that missing_ok does not silence (use delete_folder).
- `PermissionDenied` – If the OS denies the unlink.

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

`recursive=True` removes the folder and its whole subtree (`shutil.rmtree`); this is not atomic — an error partway through can leave the tree partially deleted. `recursive=False` removes only an empty folder (`rmdir`).

Raises:

- `NotFound` – If the folder does not exist and missing_ok is False.
- `InvalidPath` – If path names a file, not a folder.
- `DirectoryNotEmpty` – If the folder is non-empty and recursive is False.
- `PermissionDenied` – If the OS denies removal.

### glob

```
glob(pattern: str) -> Iterator[FileInfo]
```

Yield files matching *pattern* under the root, one at a time.

Lazily walks `Path.glob`; entries that escape the root through a symlink are skipped rather than returned, and directories are omitted — only files are yielded.

### list_files

```
list_files(
    path: str,
    *,
    recursive: bool = False,
    max_depth: int | None = None,
) -> Iterator[FileInfo]
```

Yield files under *path*, one `FileInfo` at a time.

Lazy: entries are produced as the directory is scanned, so listing a large tree holds only the current entry in memory. A missing or non-folder *path* yields nothing (no error). With `recursive` and `max_depth` set, traversal is pruned at the depth bound during the `os.walk` rather than filtered afterwards.

### list_folders

```
list_folders(path: str) -> Iterator[FolderEntry]
```

Yield immediate subfolders of *path* as `FolderEntry` records.

Lazy single-level scan; a missing or non-folder *path* yields nothing.

### iter_children

```
iter_children(
    path: str,
) -> Iterator[FileInfo | FolderEntry]
```

Yield the immediate files and folders under *path* in one scan.

Overrides the base (which chains `list_files` and `list_folders`, two passes) to walk the directory once, yielding `FileInfo` for files and `FolderEntry` for folders. A missing or non-folder *path* yields nothing.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return metadata for the file at *path* from a single `stat`.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory, not a file.

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Return aggregate metadata for the folder at *path*.

File count, total size, and latest modification time are computed by walking the entire subtree and `stat`-ing every file, so cost is O(files-in-subtree) — not a constant-time lookup.

Raises:

- `NotFound` – If the folder does not exist.
- `InvalidPath` – If path names a file, not a folder.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename the file *src* to *dst*.

Atomic when *src* and *dst* are on the same filesystem (`os.rename` via `shutil.move`) — which within a single root they always are, so `ATOMIC_MOVE` is declared. A cross-filesystem move (e.g. a bind-mounted subtree) falls back to copy-then-delete, which is not atomic. `src == dst` is a no-op; parent directories of *dst* are created as needed.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or an ancestor of dst exists as a regular file.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If the OS denies the operation.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy the file *src* to *dst*, preserving mode and mtime (`copy2`).

Not atomic: content is streamed to *dst*, so a crash mid-copy can leave a partial file at the destination. `src == dst` is a no-op; parent directories of *dst* are created as needed.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or an ancestor of dst exists as a regular file.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If the OS denies the operation.

## See also

- [Local Backend Guide](https://docs.remotestore.dev/stable/guides/backends/local/index.md) — usage patterns, configuration, and examples
- [File Operations example](https://docs.remotestore.dev/stable/tutorial/examples/file-operations/index.md) — full Store API demo using LocalBackend
