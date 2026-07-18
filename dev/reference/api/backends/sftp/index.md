# SFTPBackend

API reference for `SFTPBackend` — stores files on any SSH/SFTP server using paramiko. Explicit host key verification and Azure Key Vault PEM support.

## SFTPBackend

```
SFTPBackend(
    host: str,
    *,
    port: int = 22,
    username: str | None = None,
    password: str | Secret | None = None,
    pkey: Any = None,
    base_path: str = "/",
    host_key_policy: HostKeyPolicy | str = STRICT,
    known_host_keys: str | None = None,
    host_keys_path: str | None = None,
    config: dict[str, Any] | None = None,
    timeout: int = 10,
    connect_kwargs: dict[str, Any] | None = None,
    retry: RetryPolicy | None = None,
)
```

SFTP backend using pure paramiko.

`move()` attempts `posix_rename` (atomic on POSIX-compliant servers), then falls back to `rename`, and finally to a stream copy followed by a delete. Because atomicity cannot be guaranteed across all servers, `ATOMIC_MOVE` is not declared.

Warning

**Not thread-safe for concurrent access.** This backend maintains a single SSH/SFTP connection (paramiko `SFTPClient`), which is not safe to call from multiple threads simultaneously. Concurrent calls via `SyncBackendAdapter` and `asyncio.gather` will race on the shared socket and may hang or corrupt responses. Create one `SFTPBackend` instance per thread if you need parallel operations.

Parameters:

- **`host`** (`str`) – SFTP server hostname (required, non-empty).
- **`port`** (`int`, default: `22` ) – SSH port (default: 22).
- **`username`** (`str | None`, default: `None` ) – SSH username.
- **`password`** (`str | Secret | None`, default: `None` ) – SSH password.
- **`pkey`** (`Any`, default: `None` ) – paramiko.PKey instance for key-based auth.
- **`base_path`** (`str`, default: `'/'` ) – Root path on the remote server (default: /).
- **`host_key_policy`** (`HostKeyPolicy | str`, default: `STRICT` ) – Host key verification policy (see SFTPUtils.HostKeyPolicy). Accepts enum value or string.
- **`known_host_keys`** (`str | None`, default: `None` ) – Known hosts string (code-level override).
- **`host_keys_path`** (`str | None`, default: `None` ) – Path to known_hosts file (default: ~/.ssh/known_hosts).
- **`config`** (`dict[str, Any] | None`, default: `None` ) – Optional config dict (may contain known_host_keys).
- **`timeout`** (`int`, default: `10` ) – SSH connection timeout in seconds.
- **`connect_kwargs`** (`dict[str, Any] | None`, default: `None` ) – Extra kwargs passed to SSHClient.connect().

### check_health

```
check_health() -> None
```

Confirm the SFTP connection works by `stat`-ing the base path.

Establishes the SSH/SFTP connection lazily if needed (retried at connection scope) and issues one `stat` round-trip.

Raises:

- `NotFound` – If the configured base path does not exist.
- `PermissionDenied` – If the server denies access to the base path.
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with SFTP-specific details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="sftp" and details containing
- `ResolutionPlan` – host, port, and base_path.

### exists

```
exists(path: str) -> bool
```

Return `True` if a file or folder exists at *path*; never `NotFound`.

Issues one `stat` round-trip; a missing path returns `False`.

Raises:

- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* is an existing regular file (`False` if absent or a folder).

Raises:

- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* is an existing directory (`False` if absent or a file).

Raises:

- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### read

```
read(path: str) -> BinaryIO
```

Open *path* for reading and return a buffered, streaming handle.

Reads lazily over the SFTP channel (wrapped in a `BufferedReader`), so memory stays constant regardless of file size. Because the read is deferred, *path* being a directory must be rejected before the handle is returned — a real OpenSSH server opens a directory for reading without error and only fails on the first read, which this streaming path never issues itself. So this one read path keeps an eager type check, unlike `read_bytes` (which reads immediately and classifies on failure).

Raises:

- `NotFound` – If the file does not exist, or a path component is itself a file.
- `InvalidPath` – If path names a directory.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails mid-read.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read and return the full file content as bytes.

Prefetches and materialises the whole file in memory (unlike the lazy `read` stream).

Directory rejection is lazy (unlike `read`, which stats eagerly): a directory target raises `InvalidPath` only because the read of it fails. This assumes the server either refuses to open a directory for reading or reports a non-zero directory `st_size` — both hold on OpenSSH, where a directory reports `st_size == 4096`. A non-standard server that opens a directory for reading *and* reports `st_size == 0` would make this return empty bytes rather than raising `InvalidPath`.

Raises:

- `NotFound` – If the file does not exist, or a path component is itself a file.
- `InvalidPath` – If path names a directory (subject to the server assumption above).
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails mid-read.

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

Write *content* to *path*, streaming it over the SFTP channel.

The bytes are streamed straight to the destination file (no temp-and-rename), so a dropped connection mid-write can leave a partial or truncated file there — use `write_atomic` when readers must never see a half-written file. Missing parent directories are created first (one `stat` per ancestor).

The returned `WriteResult` carries `size` (counted during upload) and `source="native"`, but every rich field — `last_modified`, `etag`, `version_id`, `digest` — is `None`: SFTP's write response carries no metadata at all, and the backend does not stat afterwards to fetch any. Call `get_file_info` when the metadata is needed.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor of path exists as a regular file.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails mid-write.

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

Write *content* to *path* atomically via a temp file plus server rename.

Readers never observe a partial file: the body is streamed to a hidden temp file in the destination directory, then promoted with `posix_rename` (atomic on POSIX-compliant servers). Servers without `posix_rename` fall back to a plain `rename` (non-atomic overwrite: the target is removed first), and the temp file is cleaned up on failure.

As in `write`, the returned `WriteResult` carries `size` and `source="native"` but leaves every rich field (`last_modified` / `etag` / `version_id` / `digest`) `None`.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor of path exists as a regular file.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]
```

Yield a writable handle promoted to *path* atomically on clean exit.

Writes stream to a hidden temp file in the destination directory; on clean exit it is promoted with `posix_rename` (atomic on POSIX servers, falling back to `rename`), and on any exception the temp file is removed and *path* is left untouched.

Raises:

- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor of path exists as a regular file.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete the file at *path*.

Raises:

- `NotFound` – If the file does not exist (or a path component is itself a file) and missing_ok is False.
- `InvalidPath` – If path names a directory (use delete_folder).
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

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

`recursive=True` walks and removes the subtree bottom-up (one round-trip per entry — not atomic; an interruption can leave the tree partially removed). `recursive=False` removes only an empty folder after checking it has no entries.

Raises:

- `NotFound` – If the folder does not exist and missing_ok is False.
- `InvalidPath` – If path names a file, not a folder.
- `DirectoryNotEmpty` – If the folder is non-empty and recursive is False.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

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

Lazily walks the remote directory (`listdir_attr`); a missing *path* yields nothing. `recursive` descends via one directory-listing round-trip per folder (`max_depth` bounds the descent). Failures other than a missing path surface as `RemoteStoreError` during iteration.

### list_folders

```
list_folders(path: str) -> Iterator[FolderEntry]
```

Yield immediate subfolders of *path* as `FolderEntry` records.

One directory-listing round-trip; a missing *path* yields nothing, and other failures surface as `RemoteStoreError` during iteration.

### iter_children

```
iter_children(
    path: str,
) -> Iterator[FileInfo | FolderEntry]
```

Yield the immediate files and folders under *path* in one listing.

Overrides the base two-pass default with a single `listdir_attr` round-trip, yielding `FileInfo` for files and `FolderEntry` for folders. A missing *path* yields nothing; other failures surface as `RemoteStoreError` during iteration.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return metadata for the file at *path* from a single `stat` round-trip.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory, not a file.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Return aggregate metadata for the folder at *path*.

File count, total size, and latest modification time are gathered by recursively walking the whole subtree (one listing round-trip per folder), so cost scales with the number of descendants.

Raises:

- `NotFound` – If the folder does not exist.
- `InvalidPath` – If path names a file, not a folder.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename the file *src* to *dst*.

Tries `posix_rename` first (atomic on POSIX-compliant servers), then a plain `rename`, and finally a stream copy-then-delete. Because the outcome depends on server support, atomicity is not guaranteed across all servers and `ATOMIC_MOVE` is not declared. `src == dst` is a no-op; missing parent directories of *dst* are created first.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or an ancestor of dst exists as a regular file.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy the file *src* to *dst* by streaming through the client.

SFTP has no server-side copy, so the bytes round-trip through the client (download then upload); this is not atomic — an interruption can leave a partial file at *dst*. `src == dst` is a no-op; missing parent directories of *dst* are created first.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or an ancestor of dst exists as a regular file.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If the server denies access (EACCES).
- `BackendUnavailable` – If the SSH/SFTP connection cannot be established or fails.

## See also

- [SFTP Backend Guide](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md) — usage patterns, configuration, and examples
- [SFTP Backend example](https://docs.remotestore.dev/stable/tutorial/examples/sftp-backend/index.md) — SFTP backend in action
