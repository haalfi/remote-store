# AzureBackend

API reference for `AzureBackend` — stores files in Azure Blob Storage and ADLS Gen2. Behavior adapts to the declared `hns` value (Hierarchical Namespace); there is no runtime auto-detection.

## AzureBackend

```
AzureBackend(
    container: str,
    *,
    hns: bool | None = None,
    account_name: str | None = None,
    account_url: str | None = None,
    account_key: str | Secret | None = None,
    sas_token: str | Secret | None = None,
    connection_string: str | Secret | None = None,
    credential: Any | None = None,
    client_options: dict[str, Any] | None = None,
    retry: RetryPolicy | None = None,
    max_concurrency: int = 1,
    reject_write_under_file_ancestor: bool = False,
)
```

Azure Storage backend.

Uses the Blob SDK for non-HNS accounts (plain Blob Storage, Azurite) and the DataLake SDK for HNS accounts (ADLS Gen2) to get atomic rename and real directory support.

Whether the account is HNS (ADLS Gen2) is declared explicitly via the required `hns` argument -- the backend does not probe for it.

`move()` on non-HNS accounts is implemented as a server-side copy followed by a blob delete. This is non-atomic: a failure between the two steps may leave both source and destination present. HNS accounts use `rename_file` which *is* atomic, so an HNS instance could in principle advertise `ATOMIC_MOVE`. The capability is deliberately not declared per-instance: `CAPABILITIES` is a single class-level set shared by HNS and non-HNS instances alike, so it reports the guarantee common to both rather than varying by the declared `hns` value.

Parameters:

- **`container`** (`str`) – Azure Storage container name (required, non-empty).
- **`hns`** (`bool | None`, default: `None` ) – Whether the storage account has Hierarchical Namespace enabled (ADLS Gen2). Required -- there is no default and no runtime auto-detection. Pass True for ADLS Gen2 accounts (atomic rename, real directories) or False for flat Blob Storage. Use AzureUtils.detect_hns() to discover the value once if you do not already know it.
- **`account_name`** (`str | None`, default: `None` ) – Storage account name.
- **`account_url`** (`str | None`, default: `None` ) – Full account URL (e.g. https://myaccount.dfs.core.windows.net).
- **`account_key`** (`str | Secret | None`, default: `None` ) – Storage account key.
- **`sas_token`** (`str | Secret | None`, default: `None` ) – Shared Access Signature token.
- **`connection_string`** (`str | Secret | None`, default: `None` ) – Azure Storage connection string.
- **`credential`** (`Any | None`, default: `None` ) – Any credential object (e.g. DefaultAzureCredential()).
- **`client_options`** (`dict[str, Any] | None`, default: `None` ) – Additional options passed to service clients. The library sets max_single_put_size, max_block_size, and min_large_block_upload_threshold defaults for streaming memory discipline; user-supplied values take precedence.
- **`retry`** (`RetryPolicy | None`, default: `None` ) – Retry policy for transient failures.
- **`max_concurrency`** (`int`, default: `1` ) – Maximum number of parallel connections for uploads and downloads (default 1 -- sequential).
- **`reject_write_under_file_ancestor`** (`bool`, default: `False` ) – If True, write / write_atomic / open_atomic / move / copy HEAD each slash-aligned ancestor of the target path on non-HNS accounts and raise InvalidPath on the first regular-file hit, matching the cross-backend contract that hierarchical filesystems enforce natively. On HNS accounts the kwarg short-circuits: hdi_isfolder rejects the operation natively, and the backend detects the file ancestor on that rejection and re-raises it as InvalidPath, so HNS delivers the cross-backend contract with or without the kwarg set. Default False: enabling the check adds one HEAD per ancestor per nested-path write; paths without slashes short-circuit.

### check_health

```
check_health() -> None
```

Verify the backend is reachable and credentials are valid.

Raises:

- `PermissionDenied` – If credentials are invalid.
- `NotFound` – If the container does not exist.
- `BackendUnavailable` – If the backend cannot be reached.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with Azure-specific details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="azure" and details containing
- `ResolutionPlan` – container and account_url.

### exists

```
exists(path: str) -> bool
```

Return `True` if a blob or folder exists at *path*; never `NotFound`.

Probes the blob first (one HEAD); if absent, probes for a folder (an HNS directory, or any blob under the `path/` prefix on flat accounts). The root always exists.

Raises:

- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### is_file

```
is_file(path: str) -> bool
```

Return `True` if *path* is an existing blob (not an HNS directory marker).

One HEAD round-trip; a missing blob or an `hdi_isfolder` directory returns `False`.

Raises:

- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### is_folder

```
is_folder(path: str) -> bool
```

Return `True` if *path* is an existing folder (HNS directory or non-HNS prefix).

The root is always a folder. Costs one directory HEAD (HNS) or a one-item prefix listing (flat).

Raises:

- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### read

```
read(path: str) -> BinaryIO
```

Open *path* for reading and return a streaming handle.

Streams the blob body in chunks, so memory stays constant regardless of size. On HNS accounts one extra HEAD confirms *path* is a file (not an `hdi_isfolder` directory) before streaming.

Raises:

- `NotFound` – If the blob does not exist.
- `InvalidPath` – If path names a directory.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### read_seekable

```
read_seekable(path: str) -> BinaryIO
```

Open *path* for random-access reading and return a seekable handle.

Overrides the base spool: instead of buffering the whole blob, each `read()` issues one HTTP Range request (`download_blob(offset=, length=)`), so only the byte ranges actually read are fetched — ideal for Parquet column pruning.

Raises:

- `NotFound` – If the blob does not exist.
- `InvalidPath` – If path names a directory.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### read_bytes

```
read_bytes(path: str) -> bytes
```

Read and return the full blob content as bytes.

Downloads the whole blob into memory (unlike the lazy `read` stream).

Raises:

- `NotFound` – If the blob does not exist.
- `InvalidPath` – If path names a directory (HNS).
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

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

Write *content* to *path* as a blob.

The content is uploaded with `upload_blob` on both flat and HNS accounts — a block-blob upload that becomes visible only when its final commit succeeds, never as a partially written blob. On flat (non-HNS) accounts this is an atomic replace. On hierarchical-namespace (HNS) accounts a guaranteed atomic replace is not assured; use `write_atomic` there when readers must never observe an intermediate state.

Raises:

- `AlreadyExists` – If the blob exists and overwrite is False.
- `InvalidPath` – If path names a directory, or (with the reject_write_under_file_ancestor opt-in, or natively on HNS) an ancestor exists as a file.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

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

Write *content* to *path* atomically.

Readers never observe a partial file. On flat accounts this is the plain `PUT` (already atomic). On HNS it streams to a hidden temp file and promotes it with an atomic `rename_file` (the temp file is cleaned up on failure).

Raises:

- `AlreadyExists` – If the blob exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor exists as a file.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### open_atomic

```
open_atomic(
    path: str, *, overwrite: bool = False
) -> Iterator[BinaryIO]
```

Yield a writable buffer promoted to *path* atomically on clean exit.

Writes spool to a temporary file (up to 8 MB in memory, then on disk). On flat accounts the buffer is committed with one `PUT`; on HNS it is uploaded to a temp blob and promoted with an atomic `rename_file`. An exception before exit leaves *path* untouched.

Raises:

- `AlreadyExists` – If the blob exists and overwrite is False.
- `InvalidPath` – If path names a directory, or an ancestor exists as a file.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### delete

```
delete(path: str, *, missing_ok: bool = False) -> None
```

Delete the blob at *path*.

Raises:

- `NotFound` – If the blob does not exist (or, on HNS, a path component is itself a file) and missing_ok is False.
- `InvalidPath` – If path names a directory (HNS; use delete_folder).
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

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
- `InvalidPath` – If path names a file (use delete instead).
- `DirectoryNotEmpty` – If non-empty and recursive is False.

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

Lazily pages the service listing (`walk_blobs`/`list_blobs` on flat accounts, `get_paths` on HNS); a missing path or a path under a file ancestor yields nothing. `recursive` lists the whole prefix (`max_depth` prunes client-side).

Raises:

- `PermissionDenied` – If credentials are rejected or lack access (401/403), surfaced during iteration.
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure, surfaced during iteration.

### list_folders

```
list_folders(path: str) -> Iterator[FolderEntry]
```

Yield immediate subfolders of *path* as `FolderEntry` records.

One paged prefix listing (`walk_blobs` common-prefixes on flat accounts, non-recursive `get_paths` on HNS); a missing path yields nothing.

Raises:

- `PermissionDenied` – If credentials are rejected or lack access (401/403), surfaced during iteration.
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure, surfaced during iteration.

### iter_children

```
iter_children(
    path: str,
) -> Iterator[FileInfo | FolderEntry]
```

Yield the immediate files and folders under *path* in one paged listing.

Overrides the base two-pass default with a single `walk_blobs` (flat) or `get_paths` (HNS) pass, yielding `FileInfo` for files and `FolderEntry` for folders. A missing path yields nothing.

Raises:

- `PermissionDenied` – If credentials are rejected or lack access (401/403), surfaced during iteration.
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure, surfaced during iteration.

### glob

```
glob(pattern: str) -> Iterator[FileInfo]
```

Match files against a glob pattern.

Parameters:

- **`pattern`** (`str`) – Glob pattern (e.g., "data/\*.csv", "\*\*/\*.txt").

Returns:

- `Iterator[FileInfo]` – An iterator of matching FileInfo objects.

### get_file_info

```
get_file_info(path: str) -> FileInfo
```

Return file metadata for `path`.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory (HNS: hdi_isfolder=true).

### get_folder_info

```
get_folder_info(path: str) -> FolderInfo
```

Return aggregate metadata for the folder at *path*.

File count, total size, and latest modification time are gathered by paging the whole subtree listing, so cost scales with the number of descendants.

Raises:

- `NotFound` – If the folder does not exist.
- `InvalidPath` – If path names a file, not a folder.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename the file *src* to *dst*.

On HNS accounts this is a single native `rename_file` (atomic). On flat accounts it is a server-side copy followed by a delete — not atomic, so a failure between the two steps can leave both *src* and *dst* present; `ATOMIC_MOVE` is therefore not declared. `src == dst` is a no-op.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or an ancestor of dst exists as a file.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy the file *src* to *dst* via a server-side copy.

Issues `start_copy_from_url` so the bytes never pass through the client. The copy is not atomic — a failure can leave a partial destination. `src == dst` is a no-op.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory, or an ancestor of dst exists as a file.
- `AlreadyExists` – If dst exists, src != dst, and overwrite is False.
- `PermissionDenied` – If credentials are rejected or lack access (401/403).
- `BackendUnavailable` – On throttling (429), 5xx, or transport failure.

## See also

- [Azure Backend Guide](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) — usage patterns, configuration, and examples
- [AzureUtils](https://docs.remotestore.dev/stable/reference/api/azure-utils/index.md) — discover an account's HNS status with `detect_hns()`
- [Azure Backend example](https://docs.remotestore.dev/stable/tutorial/examples/azure-backend/index.md) — Azure backend in action
