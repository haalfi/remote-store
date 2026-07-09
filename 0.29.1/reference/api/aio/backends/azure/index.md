# AsyncAzureBackend

Native async Azure Storage backend. Uses the async Blob SDK for non-HNS accounts (plain Blob Storage, Azurite) and the async DataLake SDK for HNS accounts (ADLS Gen2) to get atomic rename and real directory support. Whether the account is HNS is declared via the required `hns` argument; use `AzureUtils.adetect_hns()` to discover it once if unknown.

## AsyncAzureBackend

```
AsyncAzureBackend(
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

Async Azure Storage backend.

Uses the async Blob SDK for non-HNS accounts (plain Blob Storage, Azurite) and the async DataLake SDK for HNS accounts (ADLS Gen2) to get atomic rename and real directory support. Whether the account is HNS is declared explicitly via the required `hns` argument -- the backend does not probe for it.

Parameters:

- **`container`** (`str`) – Azure Storage container name (required, non-empty).
- **`hns`** (`bool | None`, default: `None` ) – Whether the storage account has Hierarchical Namespace enabled (ADLS Gen2). Required -- there is no default and no runtime auto-detection. Pass True for ADLS Gen2 accounts (atomic rename, real directories) or False for flat Blob Storage. Use AzureUtils.adetect_hns() to discover the value once if you do not already know it.
- **`account_name`** (`str | None`, default: `None` ) – Storage account name.
- **`account_url`** (`str | None`, default: `None` ) – Full account URL (e.g. https://myaccount.dfs.core.windows.net).
- **`account_key`** (`str | Secret | None`, default: `None` ) – Storage account key.
- **`sas_token`** (`str | Secret | None`, default: `None` ) – Shared Access Signature token.
- **`connection_string`** (`str | Secret | None`, default: `None` ) – Azure Storage connection string.
- **`credential`** (`Any | None`, default: `None` ) – Any credential object (e.g. DefaultAzureCredential()).
- **`client_options`** (`dict[str, Any] | None`, default: `None` ) – Additional options passed to service clients. The library sets max_single_put_size, max_block_size, and min_large_block_upload_threshold defaults for streaming memory discipline; user-supplied values take precedence.
- **`retry`** (`RetryPolicy | None`, default: `None` ) – Retry policy for transient failures.
- **`max_concurrency`** (`int`, default: `1` ) – Maximum number of parallel connections for uploads and downloads (default 1 -- sequential).
- **`reject_write_under_file_ancestor`** (`bool`, default: `False` ) – If True, write / write_atomic / move / copy HEAD each slash-aligned ancestor of the target path on non-HNS accounts and raise InvalidPath on the first regular-file hit, matching the cross-backend contract that hierarchical filesystems enforce natively. On HNS accounts the kwarg short-circuits: hdi_isfolder rejects the operation natively, and the backend detects the file ancestor on that rejection and re-raises it as InvalidPath, so HNS delivers the cross-backend contract with or without the kwarg set. Default False.

### name

```
name: str
```

Unique identifier for this backend type.

### capabilities

```
capabilities: CapabilitySet
```

Declared capabilities of this backend.

### check_health

```
check_health() -> None
```

Verify the backend is reachable and credentials are valid.

Raises:

- `PermissionDenied` – If credentials are invalid.
- `NotFound` – If the container does not exist.
- `BackendUnavailable` – If the backend cannot be reached.

### to_key

```
to_key(native_path: str) -> str
```

Convert a backend-native path to a backend-relative key.

Parameters:

- **`native_path`** (`str`) – Absolute or backend-native path string.

Returns:

- `str` – Path relative to the backend's root.

### native_path

```
native_path(path: str) -> str
```

Convert a backend-relative key to the backend-native path.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `str` – Backend-native path (container/path).

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with Azure-specific details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="async-azure" and details containing
- `ResolutionPlan` – container and account_url.

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

- `AsyncIterator[bytes]` – An async iterator yielding byte chunks.

Raises:

- `NotFound` – If the file does not exist.
- `InvalidPath` – If path names a directory (HNS accounts only).

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
- `InvalidPath` – If path names a directory (HNS accounts only).

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

- `WriteResult` – WriteResult with native Azure fields (etag, last_modified,
- `WriteResult` – etc.) populated from the SDK upload response.

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

For non-HNS accounts, direct upload is atomic (PUT semantics). For HNS accounts, write to temp file via DFS then atomic rename.

Parameters:

- **`path`** (`str`) – Backend-relative key.
- **`content`** (`AsyncWritableContent`) – Data to write.
- **`overwrite`** (`bool`, default: `False` ) – If False, raise if file already exists.
- **`metadata`** (`Mapping[str, str] | None`, default: `None` ) – Optional user-defined string metadata.

Returns:

- `WriteResult` – WriteResult with native Azure fields populated from the SDK
- `WriteResult` – response (non-HNS) or from get_file_properties() after rename
- `WriteResult` – (HNS).

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
- `InvalidPath` – If path names a directory (HNS accounts only).

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

### glob

```
glob(pattern: str) -> AsyncIterator[FileInfo]
```

Match files against a glob pattern.

Parameters:

- **`pattern`** (`str`) – Glob pattern (e.g., "data/\*.csv", "\*\*/\*.txt").

Returns:

- `AsyncIterator[FileInfo]` – An async iterator of matching FileInfo objects.

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

- `InvalidPath` – If path names a directory (HNS: hdi_isfolder=true).
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

- `NotFound` – If the folder does not exist.
- `InvalidPath` – If path names a file (use get_file_info instead).

### move

```
move(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Move or rename a file.

Parameters:

- **`src`** (`str`) – Backend-relative source key.
- **`dst`** (`str`) – Backend-relative destination key.
- **`overwrite`** (`bool`, default: `False` ) – If True, replace any existing file at dst.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory (HNS only).
- `AlreadyExists` – If dst exists and overwrite is False.

### copy

```
copy(
    src: str, dst: str, *, overwrite: bool = False
) -> None
```

Copy a file.

Parameters:

- **`src`** (`str`) – Backend-relative source key.
- **`dst`** (`str`) – Backend-relative destination key.
- **`overwrite`** (`bool`, default: `False` ) – If True, replace any existing file at dst.

Raises:

- `NotFound` – If src does not exist.
- `InvalidPath` – If src or dst names a directory (HNS only).
- `AlreadyExists` – If dst exists and overwrite is False.

### aclose

```
aclose() -> None
```

Release all Azure SDK client resources.

### unwrap

```
unwrap(type_hint: type[T]) -> T
```

Return the native async FileSystemClient if it matches the requested type.

Parameters:

- **`type_hint`** (`type[T]`) – The expected type.

Returns:

- `T` – The native async client instance matching type_hint.

Raises:

- `CapabilityNotSupported` – If backend cannot provide the requested type.

## See also

- [AzureBackend](https://docs.remotestore.dev/stable/reference/api/backends/azure/index.md) — synchronous counterpart
- [Azure Backend Guide](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) — configuration and usage
- [Azure HNS setup](https://docs.remotestore.dev/stable/guides/backends/azure-hns-setup/index.md) — ADLS Gen2 provisioning
