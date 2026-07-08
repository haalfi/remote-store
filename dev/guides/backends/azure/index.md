# Azure Backend

The Azure backend stores files in Azure Blob Storage and Azure Data Lake Storage (ADLS) Gen2 using [`azure-storage-file-datalake`](https://learn.microsoft.com/en-us/python/api/azure-storage-file-datalake/) directly. You declare whether the account has Hierarchical Namespace (HNS) enabled via the required `hns` option; HNS accounts get atomic rename and real directories on ADLS Gen2, while plain Blob Storage accounts (`hns=False`) remain fully functional.

## Installation

```
pip install "remote-store[azure]"
```

This pulls in `azure-storage-file-datalake` and `azure-identity` (for `DefaultAzureCredential`).

## Usage

```
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={
        "my-azure": BackendConfig(
            type="azure",
            options={
                "container": "my-container",
                "hns": True,  # ADLS Gen2; use False for plain Blob Storage
                "account_name": "mystorageaccount",
            },
        ),
    },
    stores={"data": StoreProfile(backend="my-azure", root_path="datasets")},
)

with Registry(config) as registry:
    store = registry.get_store("data")
    store.write("report.csv", b"col1,col2\n1,2\n")
    data = store.read_bytes("report.csv")
```

### Direct construction

```
from remote_store.backends import AzureBackend

# Account key. `hns` is required: True for ADLS Gen2, False for plain Blob Storage.
backend = AzureBackend(
    container="my-container",
    hns=True,
    account_name="mystorageaccount",
    account_key="...",
)

# SAS token
backend = AzureBackend(
    container="my-container",
    hns=True,
    account_name="mystorageaccount",
    sas_token="sv=2023-11-03&...",
)

# Connection string
backend = AzureBackend(
    container="my-container",
    hns=False,
    connection_string="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;",
)

# DefaultAzureCredential (auto-resolves env vars, managed identity, CLI login, etc.)
backend = AzureBackend(
    container="my-container",
    hns=True,
    account_name="mystorageaccount",
)
```

If you do not know whether an account is HNS-enabled, discover it once with [`AzureUtils.detect_hns()`](#discovering-hns-status) and pass the result.

## Options

| Option                             | Type          | Default      | Description                                                                                                                                                                    |
| ---------------------------------- | ------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `container`                        | `str`         | *(required)* | Azure Storage container name                                                                                                                                                   |
| `hns`                              | `bool`        | *(required)* | Whether the account has Hierarchical Namespace (ADLS Gen2) enabled. No default and no auto-detection — see [HNS vs Non-HNS](#hns-vs-non-hns)                                   |
| `account_name`                     | `str`         | `None`       | Storage account name (builds URL automatically)                                                                                                                                |
| `account_url`                      | `str`         | `None`       | Full account URL (e.g. `https://myaccount.dfs.core.windows.net`)                                                                                                               |
| `account_key`                      | `str`         | `None`       | Storage account key                                                                                                                                                            |
| `sas_token`                        | `str`         | `None`       | Shared Access Signature token                                                                                                                                                  |
| `connection_string`                | `str`         | `None`       | Azure Storage connection string                                                                                                                                                |
| `credential`                       | `Any`         | `None`       | Any credential object (e.g. `DefaultAzureCredential()`)                                                                                                                        |
| `client_options`                   | `dict`        | `None`       | Extra kwargs passed to service clients (see [Upload tuning](#upload-tuning))                                                                                                   |
| `retry`                            | `RetryPolicy` | `None`       | Retry policy for transient failures                                                                                                                                            |
| `max_concurrency`                  | `int`         | `1`          | Parallel connections for uploads/downloads (>1 benefits large files)                                                                                                           |
| `reject_write_under_file_ancestor` | `bool`        | `False`      | If `True`, reject writes whose path nests under an existing regular file (non-HNS HEADs each ancestor; HNS rejects natively). Adds one HEAD per ancestor per nested-path write |

`hns` must be declared explicitly, and at least one of `account_name`, `account_url`, or `connection_string` must be provided.

## Authentication

The backend resolves credentials in this order:

1. **`account_key`** — if provided, used directly
1. **`sas_token`** — if provided, used directly
1. **`credential`** — any credential object (e.g. `DefaultAzureCredential()`)
1. **`DefaultAzureCredential`** — auto-detected from environment (requires `azure-identity`)

`DefaultAzureCredential` automatically tries environment variables, managed identity, Azure CLI, and other sources. See the [Azure Identity docs](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential) for details.

## HNS vs Non-HNS

You declare whether the account has Hierarchical Namespace (HNS) enabled via the required `hns` option. The backend adapts its behavior to the declared value:

| Feature                         | `hns=True` (ADLS Gen2)    | `hns=False` (Blob Storage)    |
| ------------------------------- | ------------------------- | ----------------------------- |
| Directories                     | Real entities             | Virtual (prefix-based)        |
| `write_atomic`                  | Temp file + atomic rename | Direct upload (PUT is atomic) |
| `move`                          | Atomic `rename_file`      | Copy + delete                 |
| `delete_folder(recursive=True)` | Single recursive delete   | Iterate + delete each blob    |

`hns` has no default and is never auto-detected. Declaring it makes the backend deterministic from construction: no account-level network call decides which semantics apply, so a transient failure or a propagation-delayed authorization response can never silently degrade an HNS account to flat behavior.

### Discovering HNS status

If you do not know an account's HNS status, discover it once with the fail-loud helper and pass the result:

```
from remote_store.backends import AzureUtils, AzureBackend

is_hns = AzureUtils.detect_hns(
    account_name="mystorageaccount",
    account_key="...",
)
backend = AzureBackend(container="my-container", hns=is_hns, account_name="mystorageaccount", account_key="...")
```

`AzureUtils.detect_hns()` issues a single account-info call and returns a `bool`. It raises on a probe error rather than guessing. An async sibling, `AzureUtils.adetect_hns(...)`, is available for async code.

Note that non-HNS `move()` (copy + delete) is not atomic and `overwrite=False` has a TOCTOU race on all account types. See the [Concurrency and Atomicity Guarantees](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) guide for details.

## File Metadata

`get_file_info()` and `list_files()` return `FileInfo` objects with the following fields populated by the Azure backend:

| Field    | Source                                        | Notes                                                                                                |
| -------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `etag`   | `BlobProperties.etag`                         | Double-quotes stripped; lowercased.                                                                  |
| `digest` | `BlobProperties.content_settings.content_md5` | Populated as `ContentDigest("md5", <hex>)` when the blob has a stored Content-MD5; `None` otherwise. |

## Write Results

The Azure backend declares `WRITE_RESULT_NATIVE` and `USER_METADATA`. Write operations return a [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/index.md) with `etag` and `last_modified` populated from the upload response. `digest` is populated as `ContentDigest("md5", <hex>)` when Azure echoes back `Content-MD5` in the upload response, and `None` otherwise. On HNS accounts, `write_atomic` always returns `digest=None`: it commits via a temp-file upload plus an atomic rename, and the backend reads only `etag` and `last_modified` from the post-rename properties — not a `Content-MD5` (the sibling `write` populates `digest` from its upload response on the same account). For a guaranteed digest regardless of method or backend, use the `remote_store.ext.write` helpers (e.g. `write_with_hash`). When blob versioning is enabled on a non-HNS container, `version_id` is also populated from the upload response.

Pass `metadata=` to store custom string key-value pairs as Azure blob metadata.

## Capabilities

Supports all capabilities except `SEEKABLE_READ` and `ATOMIC_MOVE`. See the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for full details.

## Streaming and seekable reads

`read()` returns a forward-only streaming handle (not seekable). Data is fetched on demand, not loaded into memory upfront.

For random access (`seek()` / `tell()`) — for example, reading the footer of a large Parquet object — use **`Store.read_seekable()`** instead of materialising the whole blob. The Azure backend does not declare the `SEEKABLE_READ` capability (its `read()` is forward-only), but `read_seekable()` is backed by a native HTTP-Range reader that issues one ranged `download_blob` per `read()`: it fetches only the bytes the consumer seeks to, with no spill to a temp file and no in-RAM copy of the object.

```
import io

with Registry(config) as registry:
    store = registry.get_store("data")
    with store.read_seekable("large-file.parquet") as stream:
        stream.seek(-8, io.SEEK_END)   # only this 8-byte range is fetched
        magic = stream.read(8)
```

The `ext.arrow` / `ext.parquet` extensions read through `read_seekable()`, so analytical reads over Azure range-seek the footer and prune columns rather than download the whole object. Reaching for `read_bytes()` + `io.BytesIO` instead forces the **entire** blob into memory, which defeats the optimisation on multi-GB objects:

```
# Anti-pattern for large objects: materialises the whole blob in RAM.
data = store.read_bytes("large-file.parquet")
seekable_stream = io.BytesIO(data)
```

`io.BytesIO` is still fine for small blobs, where a single download is cheaper than issuing ranged requests.

### Async caveat: no native seekable read

The async API has no `read_seekable()` (see [Async API limitations](https://docs.remotestore.dev/stable/guides/async/#limitations)), and `remote_store.aio.ext` ships only `write` — there is no async `ext.arrow` / `ext.parquet`. To drive those analytical readers against an `AsyncAzureBackend` you must bridge to sync with [`AsyncBackendSyncAdapter`](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md), whose `read()` is forward-only (`seekable()` is `False`). That masks Azure's range reader, so `read_seekable()` falls back to spooling the whole object to a temporary file (sized by `TMPDIR`) before the reader can seek. For large analytical reads, prefer the **sync** Azure store, which keeps the native range path.

## Upload tuning

The library sets conservative upload defaults on the Azure service clients to keep memory usage bounded during streaming transfers:

| Setting                            | Library default | SDK default |
| ---------------------------------- | --------------- | ----------- |
| `max_single_put_size`              | 1 MiB           | 64 MiB      |
| `max_block_size`                   | 1 MiB           | 4 MiB       |
| `min_large_block_upload_threshold` | 1               | 4 MiB + 1   |

These defaults cause uploads to use staged-block requests with small blocks. For large files where upload throughput matters more than memory, override via `client_options`:

```
AzureBackend(
    container="my-container",
    hns=False,  # or True for an ADLS Gen2 (HNS) account
    connection_string="...",
    client_options={
        "max_single_put_size": 8 * 1024 * 1024,   # 8 MiB
        "max_block_size": 4 * 1024 * 1024,          # 4 MiB
    },
)
```

## Concurrency and connection pooling

The async Azure SDK rides aiohttp (`AioHttpTransport`). A single `AsyncStore` (or `AsyncAzureBackend`) shared across many coroutines funnels every request through one transport and its connection pool, so under high fan-out — a large `asyncio.gather`, or one shared store behind a FastAPI app — the pool can become the bottleneck before the storage account's own limits do. (Share one store per event loop; see the [concurrency posture](https://docs.remotestore.dev/stable/explanation/concurrency/#concurrent-use-posture).)

Two independent levers:

- **`max_concurrency`** (constructor option, default `1`) sets the parallel connections used *within* a single upload/download. Raise it for large-file throughput; it does not change how many operations run concurrently.
- **Connector pool size.** `client_options` is forwarded verbatim to the Azure service clients, so for very high concurrent fan-out you can supply a custom `transport=` (an [`AioHttpTransport`](https://learn.microsoft.com/en-us/python/api/azure-core/azure.core.pipeline.transport.aiohttptransport) over an `aiohttp.ClientSession` whose `TCPConnector` has a higher `limit`) to raise the shared-pool ceiling.

Size the pool to your fan-out, not arbitrarily high: each connection is a socket against the storage account, which itself throttles (`429`). The right ceiling is best found by measuring against your workload.

## Escape Hatch

Access the underlying `FileSystemClient` when you need Azure-specific features:

```
from azure.storage.filedatalake import FileSystemClient

fs = backend.unwrap(FileSystemClient)
fs.get_paths(path="my-prefix")
```

## Local Development with Azurite

[Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite) is the official Azure Storage emulator. Start it with Docker:

```
docker run -p 10000:10000 mcr.microsoft.com/azure-storage/azurite
```

Then connect using the well-known Azurite connection string:

```
backend = AzureBackend(
    container="test",
    hns=False,  # Azurite is flat-namespace only
    connection_string=(
        "DefaultEndpointsProtocol=http;"
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
        "/K1SZFPTOtr/KBHBeksoGMGw==;"
        "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    ),
)
```

Note: Azurite does not support Hierarchical Namespace. HNS-specific features (atomic rename, real directories) are tested with mocked SDK objects. To validate against a live ADLS Gen2 account, see [Azure HNS account setup](https://docs.remotestore.dev/stable/guides/backends/azure-hns-setup/index.md).

## See also

- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md)
- [Example script](https://docs.remotestore.dev/stable/tutorial/examples/azure-backend/index.md)

## API Reference

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

Bases: `Backend`

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
