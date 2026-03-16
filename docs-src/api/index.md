# API Reference

Complete reference for all public exports of `remote-store`.

## Core

| Class | Description |
|-------|-------------|
| [Store](store.md) | Main entry point for all file operations |
| [Registry](registry.md) | Creates and manages backend instances and stores |
| [Backend](backend.md) | Abstract base class for storage backends |

## Backends

| Class | Description |
|-------|-------------|
| [LocalBackend](backends/local.md) | Local filesystem storage |
| [MemoryBackend](backends/memory.md) | In-process storage for testing |
| [ReadOnlyHttpBackend](backends/http.md) | Read-only access to HTTP/HTTPS URLs |
| [S3Backend](backends/s3.md) | Amazon S3 and S3-compatible services |
| [S3PyArrowBackend](backends/s3-pyarrow.md) | S3 via PyArrow C++ for higher throughput |
| [SFTPBackend](backends/sftp.md) | SSH/SFTP server storage via paramiko |
| [AzureBackend](backends/azure.md) | Azure Blob Storage and ADLS Gen2 |

## Utilities

| Class | Description |
|-------|-------------|
| [SFTPUtils](sftp-utils.md) | Key loading and host-key verification helpers for SFTP |

## Configuration

| Class | Description |
|-------|-------------|
| [RegistryConfig](config.md#remote_store.RegistryConfig) | Top-level configuration holding backends and stores |
| [BackendConfig](config.md#remote_store.BackendConfig) | Configuration for a single backend |
| [StoreProfile](config.md#remote_store.StoreProfile) | Configuration for a single store |
| [RetryPolicy](config.md#remote_store.RetryPolicy) | Retry policy for backend operations |
| [Secret](config.md#remote_store.Secret) | Sensitive string wrapper with masked repr |
| [SecretRedactionFilter](config.md#remote_store.SecretRedactionFilter) | Logging filter that redacts secrets |

## Path & Models

| Class | Description |
|-------|-------------|
| [RemotePath](path.md) | Validated, immutable path value object |
| [FileInfo](models.md#remote_store.FileInfo) | Metadata for a file (name, size, modified time) |
| [FolderEntry](models.md#remote_store.FolderEntry) | Folder identity returned by listing operations |
| [FolderInfo](models.md#remote_store.FolderInfo) | Aggregated folder metadata (file count, total size); satisfies `PathEntry` |
| [PathEntry](models.md#remote_store.PathEntry) | Protocol for uniform listing (name + path) |

## Capabilities

| Class | Description |
|-------|-------------|
| [Capability](capabilities.md#remote_store.Capability) | Enum of backend capabilities |
| [CapabilitySet](capabilities.md#remote_store.CapabilitySet) | Set of capabilities a backend supports |

## Errors

| Class | Description |
|-------|-------------|
| [RemoteStoreError](errors.md#remote_store.RemoteStoreError) | Base exception |
| [NotFound](errors.md#remote_store.NotFound) | File or folder not found |
| [AlreadyExists](errors.md#remote_store.AlreadyExists) | File already exists (no overwrite) |
| [PermissionDenied](errors.md#remote_store.PermissionDenied) | Insufficient permissions |
| [InvalidPath](errors.md#remote_store.InvalidPath) | Path validation failed |
| [CapabilityNotSupported](errors.md#remote_store.CapabilityNotSupported) | Backend lacks required capability |
| [BackendUnavailable](errors.md#remote_store.BackendUnavailable) | Backend could not be reached |
| [DirectoryNotEmpty](errors.md#remote_store.DirectoryNotEmpty) | Non-recursive delete on non-empty folder |

## Functions

| Function | Description |
|----------|-------------|
| [register_backend](registry.md#remote_store.register_backend) | Register a custom backend type |

## Extensions

| Module | Description |
|--------|-------------|
| [ext.arrow](ext-arrow.md) | PyArrow `FileSystemHandler` adapter for Store |
| [ext.batch](ext-batch.md) | Batch delete, copy, and exists operations |
| [ext.cache](ext-cache.md) | Store-level caching middleware with TTL |
| [ext.dagster](ext-dagster.md) | Dagster IO Manager adapter for Store |
| [ext.glob](ext-glob.md) | Portable glob pattern matching fallback |
| [ext.observe](ext-observe.md) | Callback hooks for store operations |
| [ext.otel](ext-otel.md) | OpenTelemetry bridge for ext.observe |
| [ext.partition](ext-partition.md) | Hive-style partition path helpers |
| [ext.pydantic](ext-pydantic.md) | Pydantic model to RegistryConfig adapter |
| [ext.transfer](ext-transfer.md) | Upload, download, and cross-store transfer |
| [ext.yaml](ext-yaml.md) | YAML config loader (PyYAML / ruamel.yaml) |
