# Azure Backend

The Azure backend stores files in Azure Blob Storage and Azure Data Lake Storage (ADLS) Gen2 using [`azure-storage-file-datalake`](https://learn.microsoft.com/en-us/python/api/azure-storage-file-datalake/) directly. It adapts at runtime to Hierarchical Namespace (HNS) accounts, providing atomic rename and real directories on ADLS Gen2 while remaining fully functional on plain Blob Storage.

## Installation

```bash
pip install "remote-store[azure]"
```

This pulls in `azure-storage-file-datalake` and `azure-identity` (for `DefaultAzureCredential`).

## Usage

```python
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={
        "my-azure": BackendConfig(
            type="azure",
            options={
                "container": "my-container",
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

```python
from remote_store.backends import AzureBackend

# Account key
backend = AzureBackend(
    container="my-container",
    account_name="mystorageaccount",
    account_key="...",
)

# SAS token
backend = AzureBackend(
    container="my-container",
    account_name="mystorageaccount",
    sas_token="sv=2023-11-03&...",
)

# Connection string
backend = AzureBackend(
    container="my-container",
    connection_string="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;",
)

# DefaultAzureCredential (auto-resolves env vars, managed identity, CLI login, etc.)
backend = AzureBackend(
    container="my-container",
    account_name="mystorageaccount",
)
```

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `container` | `str` | *(required)* | Azure Storage container name |
| `account_name` | `str` | `None` | Storage account name (builds URL automatically) |
| `account_url` | `str` | `None` | Full account URL (e.g. `https://myaccount.dfs.core.windows.net`) |
| `account_key` | `str` | `None` | Storage account key |
| `sas_token` | `str` | `None` | Shared Access Signature token |
| `connection_string` | `str` | `None` | Azure Storage connection string |
| `credential` | `Any` | `None` | Any credential object (e.g. `DefaultAzureCredential()`) |
| `client_options` | `dict` | `None` | Extra kwargs passed to service clients (see [Upload tuning](#upload-tuning)) |
| `retry` | `RetryPolicy` | `None` | Retry policy for transient failures |
| `max_concurrency` | `int` | `1` | Parallel connections for uploads/downloads (>1 benefits large files) |
| `reject_write_under_file_ancestor` | `bool` | `False` | If `True`, reject writes whose path nests under an existing regular file (non-HNS HEADs each ancestor; HNS rejects natively). Adds one HEAD per ancestor per nested-path write |

At least one of `account_name`, `account_url`, or `connection_string` must be provided.

## Authentication

The backend resolves credentials in this order:

1. **`account_key`** — if provided, used directly
2. **`sas_token`** — if provided, used directly
3. **`credential`** — any credential object (e.g. `DefaultAzureCredential()`)
4. **`DefaultAzureCredential`** — auto-detected from environment (requires `azure-identity`)

`DefaultAzureCredential` automatically tries environment variables, managed identity, Azure CLI, and other sources. See the [Azure Identity docs](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential) for details.

## HNS vs Non-HNS

The backend detects Hierarchical Namespace (HNS) status on first use and adapts its behavior:

| Feature | HNS Enabled (ADLS Gen2) | No HNS (Blob Storage) |
|---------|------------------------|-----------------------|
| Directories | Real entities | Virtual (prefix-based) |
| `write_atomic` | Temp file + atomic rename | Direct upload (PUT is atomic) |
| `move` | Atomic `rename_file` | Copy + delete |
| `delete_folder(recursive=True)` | Single recursive delete | Iterate + delete each blob |

If the HNS detection call fails, the backend falls back to non-HNS behavior for that operation and retries detection on the next one, so a transient failure does not permanently degrade an HNS account. A persistently failing probe (e.g. a credential denied account-level `GetAccountInfo`) re-probes once per operation and logs a warning once.

!!! note "HNS auto-detection is being replaced"
    This implicit `GetAccountInfo` probe is interim. A future release will require you to **declare** whether the account is HNS (an explicit `hns=` option) and provide an `AzureUtils.detect_hns()` helper to discover it once, rather than probing on every backend. This removes the auto-detection failure modes entirely.

Note that non-HNS `move()` (copy + delete) is not atomic and `overwrite=False` has a TOCTOU race on all account types. See the [Concurrency and Atomicity Guarantees](../../explanation/concurrency.md) guide for details.

## File Metadata

`get_file_info()` and `list_files()` return `FileInfo` objects with the following fields populated by the Azure backend:

| Field | Source | Notes |
|-------|--------|-------|
| `etag` | `BlobProperties.etag` | Double-quotes stripped; lowercased. |
| `digest` | `BlobProperties.content_settings.content_md5` | Populated as `ContentDigest("md5", <hex>)` when the blob has a stored Content-MD5; `None` otherwise. |

## Write Results

The Azure backend declares `WRITE_RESULT_NATIVE` and `USER_METADATA`. Write operations return
a [`WriteResult`](../../reference/api/models.md) with `etag` and `last_modified` populated from the upload
response. `digest` is populated as `ContentDigest("md5", <hex>)` when Azure echoes back
`Content-MD5` in the upload response, and `None` otherwise. When blob versioning is enabled
on a non-HNS container, `version_id` is also populated from the upload response.

Pass `metadata=` to store custom string key-value pairs as Azure blob metadata.

## Capabilities

Supports all capabilities except `SEEKABLE_READ` and `ATOMIC_MOVE`.
See the [capabilities matrix](../../reference/capabilities-matrix.md) for full details.

## Streaming and seekable reads

`read()` returns a forward-only streaming handle (not seekable). Data is fetched on demand, not loaded into memory upfront.

For random access (`seek()` / `tell()`) — for example, reading the footer of a large Parquet object — use **`Store.read_seekable()`** instead of materialising the whole blob. The Azure backend does not declare the `SEEKABLE_READ` capability (its `read()` is forward-only), but `read_seekable()` is backed by a native HTTP-Range reader that issues one ranged `download_blob` per `read()`: it fetches only the bytes the consumer seeks to, with no spill to a temp file and no in-RAM copy of the object.

```python
import io

with Registry(config) as registry:
    store = registry.get_store("data")
    with store.read_seekable("large-file.parquet") as stream:
        stream.seek(-8, io.SEEK_END)   # only this 8-byte range is fetched
        magic = stream.read(8)
```

The `ext.arrow` / `ext.parquet` extensions read through `read_seekable()`, so analytical reads over Azure range-seek the footer and prune columns rather than download the whole object. Reaching for `read_bytes()` + `io.BytesIO` instead forces the **entire** blob into memory, which defeats the optimisation on multi-GB objects:

```python
# Anti-pattern for large objects: materialises the whole blob in RAM.
data = store.read_bytes("large-file.parquet")
seekable_stream = io.BytesIO(data)
```

`io.BytesIO` is still fine for small blobs, where a single download is cheaper than issuing ranged requests.

### Async caveat: no native seekable read

The async API has no `read_seekable()` (see [Async API limitations](../async.md#limitations)), and `remote_store.aio.ext` ships only `write` — there is no async `ext.arrow` / `ext.parquet`. To drive those analytical readers against an `AsyncAzureBackend` you must bridge to sync with [`AsyncBackendSyncAdapter`](../async-sync-bridges.md), whose `read()` is forward-only (`seekable()` is `False`). That masks Azure's range reader, so `read_seekable()` falls back to spooling the whole object to a temporary file (sized by `TMPDIR`) before the reader can seek. For large analytical reads, prefer the **sync** Azure store, which keeps the native range path.

## Upload tuning

The library sets conservative upload defaults on the Azure service clients
to keep memory usage bounded during streaming transfers:

| Setting | Library default | SDK default |
|---------|----------------|-------------|
| `max_single_put_size` | 1 MiB | 64 MiB |
| `max_block_size` | 1 MiB | 4 MiB |
| `min_large_block_upload_threshold` | 1 | 4 MiB + 1 |

These defaults cause uploads to use staged-block requests with small blocks.
For large files where upload throughput matters more than memory, override
via `client_options`:

```python
AzureBackend(
    container="my-container",
    connection_string="...",
    client_options={
        "max_single_put_size": 8 * 1024 * 1024,   # 8 MiB
        "max_block_size": 4 * 1024 * 1024,          # 4 MiB
    },
)
```

## Concurrency and connection pooling

The async Azure SDK rides aiohttp (`AioHttpTransport`). A single `AsyncStore` (or `AsyncAzureBackend`) shared across many coroutines funnels every request through one transport and its connection pool, so under high fan-out — a large `asyncio.gather`, or one shared store behind a FastAPI app — the pool can become the bottleneck before the storage account's own limits do. (Share one store per event loop; see the [concurrency posture](../../explanation/concurrency.md#concurrent-use-posture).)

Two independent levers:

- **`max_concurrency`** (constructor option, default `1`) sets the parallel connections used *within* a single upload/download. Raise it for large-file throughput; it does not change how many operations run concurrently.
- **Connector pool size.** `client_options` is forwarded verbatim to the Azure service clients, so for very high concurrent fan-out you can supply a custom `transport=` (an [`AioHttpTransport`](https://learn.microsoft.com/en-us/python/api/azure-core/azure.core.pipeline.transport.aiohttptransport) over an `aiohttp.ClientSession` whose `TCPConnector` has a higher `limit`) to raise the shared-pool ceiling.

Size the pool to your fan-out, not arbitrarily high: each connection is a socket against the storage account, which itself throttles (`429`). The right ceiling is best found by measuring against your workload.

## Escape Hatch

Access the underlying `FileSystemClient` when you need Azure-specific features:

```python
from azure.storage.filedatalake import FileSystemClient

fs = backend.unwrap(FileSystemClient)
fs.get_paths(path="my-prefix")
```

## Local Development with Azurite

[Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite) is the official Azure Storage emulator. Start it with Docker:

```bash
docker run -p 10000:10000 mcr.microsoft.com/azure-storage/azurite
```

Then connect using the well-known Azurite connection string:

```python
backend = AzureBackend(
    container="test",
    connection_string=(
        "DefaultEndpointsProtocol=http;"
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
        "/K1SZFPTOtr/KBHBeksoGMGw==;"
        "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    ),
)
```

Note: Azurite does not support Hierarchical Namespace. HNS-specific features (atomic rename, real directories) are tested with mocked SDK objects. To validate against a live ADLS Gen2 account, see [Azure HNS account setup](azure-hns-setup.md).

## See also

- [Capabilities matrix](../../reference/capabilities-matrix.md)
- [API reference](../../reference/api/store.md)
- [Example script](../../../examples/backends/azure_backend.py)

## API Reference

::: remote_store.backends.AzureBackend
