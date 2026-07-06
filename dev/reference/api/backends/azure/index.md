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

## See also

- [Azure Backend Guide](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) — usage patterns, configuration, and examples
- [AzureUtils](https://docs.remotestore.dev/stable/reference/api/azure-utils/index.md) — discover an account's HNS status with `detect_hns()`
- [Azure Backend example](https://docs.remotestore.dev/stable/tutorial/examples/azure-backend/index.md) — Azure backend in action
