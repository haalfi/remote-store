# Adapters & types

Bridges between the synchronous and asynchronous backend worlds, plus the async content type alias. The adapters let a sync backend run under [`AsyncStore`](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md) and an async backend run under the synchronous [`Store`](https://docs.remotestore.dev/stable/reference/api/store/index.md). See [Async-sync bridges](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md) for when to reach for each.

## SyncBackendAdapter

Wraps any synchronous `Backend` as an `AsyncBackend` by dispatching each blocking call to the default executor via `asyncio.to_thread`. `AsyncStore` auto-wraps sync backends on construction; explicit construction is only required when you want to introspect the adapter.

## SyncBackendAdapter

```
SyncBackendAdapter(backend: Backend)
```

Wraps a synchronous `Backend` as an `AsyncBackend`.

Every blocking call is dispatched to the default executor via `asyncio.to_thread`, keeping the event loop responsive.

Parameters:

- **`backend`** (`Backend`) – The synchronous backend instance to wrap.

### name

```
name: str
```

Backend identifier, forwarded from the wrapped backend.

### capabilities

```
capabilities: CapabilitySet
```

Capability set, forwarded from the wrapped backend.

### to_key

```
to_key(native_path: str) -> str
```

Convert a native path to a backend-relative key.

### native_path

```
native_path(path: str) -> str
```

Convert a backend-relative key to the native path.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a resolution plan for *path*.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return the native backend handle.

### exists

```
exists(path: str) -> bool
```

Check if a file or folder exists.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* is an existing file.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* is an existing folder.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read the full content of a file as bytes.

Raises:

- `InvalidPath` – If path names an existing directory.
- `NotFound` – If the file does not exist.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Get metadata for a file.

Raises:

- `InvalidPath` – If path names an existing directory.
- `NotFound` – If the file does not exist.

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Get metadata for a folder.

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

Raises:

- `InvalidPath` – If src names a directory or dst names an existing directory.
- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy a file.

Raises:

- `InvalidPath` – If src names a directory or dst names an existing directory.
- `NotFound` – If src does not exist.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete a file.

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

Raises:

- `InvalidPath` – If path names an existing file (regardless of missing_ok — a type mismatch is not a missing file).
- `NotFound` – If the folder is missing and missing_ok is False.
- `DirectoryNotEmpty` – If non-empty and recursive is False.

### check_health

```
check_health() -> None
```

Verify the backend is reachable.

### read

```
read(path: str) -> AsyncIterator[bytes]
```

Open a file for reading and yield chunks asynchronously.

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

Write content atomically via temp file + rename.

Raises:

- `CapabilityNotSupported` – If backend lacks ATOMIC_WRITE.
- `AlreadyExists` – If the file exists and overwrite is False.
- `InvalidPath` – If path names a directory.

### list_files

```
list_files(
    path: str,
    *,
    recursive: bool = False,
    max_depth: int | None = None,
) -> AsyncIterator[FileInfo]
```

List files under *path*.

### list_folders

```
list_folders(path: str) -> AsyncIterator[FolderEntry]
```

List immediate subfolders under *path*.

### glob

```
glob(pattern: str) -> AsyncIterator[FileInfo]
```

Match files against a glob pattern.

### iter_children

```
iter_children(
    path: str,
) -> AsyncIterator[FileInfo | FolderEntry]
```

Yield both files and folders under *path*.

### aclose

```
aclose() -> None
```

Release resources held by the wrapped backend.

## AsyncBackendSyncAdapter

Wraps any `AsyncBackend` as a synchronous `Backend` by running a private event loop on a dedicated daemon thread for the adapter's lifetime. See [Async-sync bridges](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md) for the full behaviour contract and the [async-to-sync adapter decision record](https://github.com/haalfi/remote-store/blob/master/sdd/adrs/0025-async-to-sync-backend-adapter.md) for the design rationale.

## AsyncBackendSyncAdapter

```
AsyncBackendSyncAdapter(async_backend: AsyncBackend)
```

Wraps an `AsyncBackend` as a synchronous `Backend`.

One private `asyncio` event loop per adapter instance, running on a dedicated daemon thread for the adapter's lifetime. Sync methods submit coroutines via `asyncio.run_coroutine_threadsafe` and block on the returned `concurrent.futures.Future`.

Construction does not enter the wrapped backend's async context manager -- callers that need `__aenter__` semantics should use `AsyncStore` directly.

Parameters:

- **`async_backend`** (`AsyncBackend`) – The async backend instance to wrap.

### name

```
name: str
```

Backend identifier, forwarded from the wrapped async backend.

### capabilities

```
capabilities: CapabilitySet
```

Capabilities reported by the wrapped backend, with stream-shape translation applied.

`SEEKABLE_READ` is masked off unconditionally — the chunk-pull stream this adapter returns is forward-only. `USER_METADATA` and `WRITE_RESULT_NATIVE` are forwarded from the inner async backend unchanged; the `write*()` methods accept and forward `metadata=`.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return a sync-safe native handle if the wrapped backend provides one.

By default raises `CapabilityNotSupported` because async-SDK handles are bound to the adapter's private event loop and cannot be used safely from the caller's thread.

Wrapped backends that can expose a sync-safe handle should implement `_SyncSafeHandleProvider` and return it from `_SyncSafeHandleProvider.sync_safe_unwrap`.

Parameters:

- **`type_hint`** (`type[T]`) – The type of handle to retrieve; passed through to \_SyncSafeHandleProvider.sync_safe_unwrap for backends that support the exemption.

Returns:

- `T` – A sync-safe handle of the type requested via type_hint.

Raises:

- `CapabilityNotSupported` – If the wrapped backend does not implement \_SyncSafeHandleProvider.

Example

```
class _SafeBackend(AsyncBackend, _SyncSafeHandleProvider):
    def sync_safe_unwrap(self, type_hint):
        return self._sync_client

adapter = AsyncBackendSyncAdapter(_SafeBackend())
client = adapter.unwrap(SyncClient)
```

### check_health

```
check_health() -> None
```

Submit a connectivity probe to the wrapped async backend.

Not a no-op: the probe is forwarded to the wrapped `AsyncBackend`, and any connectivity error it raises reaches the sync caller unchanged.

Returns:

- `None` – None on success.

Raises:

- `BackendUnavailable` – Or another backend-specific error if the wrapped backend's health check fails.
- `RuntimeError` – If the adapter is closed or called from a running event loop.

Example

```
try:
    adapter.check_health()
except BackendUnavailable:
    ...  # handle connectivity failure
```

### read

```
read(path: str) -> BinaryIO
```

Open *path* for reading and return a forward-only chunk-pull stream.

The returned stream pulls one async chunk per `read()` call; the file is never fully materialised in memory. At most one `__anext__` is in-flight at a time.

The stream is forward-only: `seekable()` returns `False` and no `seek` / `tell` / `fileno` methods are exposed. Closing via the context manager or `close()` submits `aclose()` on the underlying async iterator so backend resources are released promptly.

Parameters:

- **`path`** (`str`) – Backend-relative key of the file to read.

Returns:

- `BinaryIO` – A forward-only io.RawIOBase stream over the file
- `BinaryIO` – contents.

Raises:

- `RuntimeError` – If the adapter is closed or called from a running event loop.
- `NotFound` – If path does not exist (propagated verbatim from the wrapped backend).

Example

```
with adapter.read("data/report.csv") as stream:
    header = stream.read(512)
```

### close

```
close(timeout: float | None = 30.0) -> None
```

Drain in-flight work, stop the loop, and join the daemon thread.

Drain order: submit `aclose` on the wrapped backend → loop-drain in-flight tasks (repeating while new tasks appear, see below) → stop the private loop → join the daemon thread.

The drain step repeats `_drain_tasks` until the private loop is quiet, **narrowing** (not eliminating) the window where a caller that passed `_guard` *before* the closed flag was set can still submit a coroutine. Each pass snapshots outstanding tasks and waits for them; new tasks that arrive between snapshot and completion trigger another pass. A residual TOCTOU gap remains: a thread that passes `_guard` after the final empty-snapshot check but before the loop is stopped will have its coroutine silently discarded when the loop stops — eliminating this gap would require serialising all submits against a shutdown lock.

If *timeout* expires before the loop is drained, a single `WARNING` record is emitted (message stem `"AsyncBackendSyncAdapter close timed out"`) and the daemon thread is left for process-exit reaping. Idempotent: subsequent calls are no-ops.

Parameters:

- **`timeout`** (`float | None`, default: `30.0` ) – Maximum seconds to wait for in-flight work to finish and the background thread to join. None means wait indefinitely. Defaults to 30.0.

## AsyncWritableContent

## AsyncWritableContent

```
AsyncWritableContent = bytes | AsyncIterator[bytes]
```

## See also

- [AsyncStore](https://docs.remotestore.dev/stable/reference/api/aio/store/index.md) — the async Store the adapters plug into
- [AsyncBackend](https://docs.remotestore.dev/stable/reference/api/aio/backend/index.md) — the async backend protocol
- [Async-sync bridges](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md) — choosing a direction
