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
| `max_concurrency` | `int` | `1` | Parallel connections for uploads/downloads (>1 benefits large files) |

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

If the HNS detection call fails (e.g. insufficient permissions), the backend falls back to non-HNS behavior.

Note that non-HNS `move()` (copy + delete) is not atomic and `overwrite=False` has a TOCTOU race on all account types. See the [Concurrency and Atomicity Guarantees](../concurrency.md) guide for details.

## File Metadata

`get_file_info()` and `list_files()` return `FileInfo` objects with the following fields populated by the Azure backend:

| Field | Source | Notes |
|-------|--------|-------|
| `etag` | `BlobProperties.etag` | Double-quotes stripped; lowercased. |
| `digest` | `BlobProperties.content_settings.content_md5` | Populated as `ContentDigest("md5", <hex>)` when the blob has a stored Content-MD5; `None` otherwise. |

## Write Results

The Azure backend declares `WRITE_RESULT_NATIVE` and `USER_METADATA`. Write operations return
a [`WriteResult`](../api/models.md) with `etag` and `last_modified` populated from the upload
response. HNS-enabled accounts additionally populate `version_id` on `write_atomic()`.

Pass `metadata=` to store custom string key-value pairs as Azure blob metadata:

```python
# requires Azure credentials
result = store.write("file.csv", data, metadata={"env": "prod"})
print(result.etag)          # e.g. "0x8da..."
print(result.last_modified) # datetime(...)
```

## Capabilities

Supports all capabilities except `SEEKABLE_READ` and `ATOMIC_MOVE`.
See the [capabilities matrix](../capabilities-matrix.md) for full details.

## Streaming

`read()` returns a forward-only streaming handle (not seekable). Data is fetched on demand, not loaded into memory upfront. If you need seekability, use `read_bytes()` and wrap in `BytesIO`:

```python
import io

data = backend.read_bytes("large-file.bin")
seekable_stream = io.BytesIO(data)
```

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

Note: Azurite does not support Hierarchical Namespace. HNS-specific features (atomic rename, real directories) are tested with mocked SDK objects.

## See also

- [Capabilities matrix](../capabilities-matrix.md)
- [API reference](../api/store.md)
- [Example script](../examples/azure-backend.md)
