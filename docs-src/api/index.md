# API Reference

Complete reference for all public exports of `remote-store`.

## Core

| Class | Description |
|-------|-------------|
| [Store](store.md) | Main entry point for all file operations |
| [ProxyStore](proxy.md) | Base class for building Store middleware |
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
| [SQLBlobBackend](backends/sql-blob.md) | SQL database blob storage via SQLAlchemy |
| [SQLQueryBackend](backends/sql-query.md) | Read-only SQL query materialization via SQLAlchemy + PyArrow |

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
| [ResolutionPlan](models.md#remote_store.ResolutionPlan) | Frozen introspection result from `resolve()` |
| [ContentDigest](models.md#remote_store.ContentDigest) | Verified content digest with known algorithm |
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

## Introspection

| Symbol | Description |
|--------|-------------|
| [info](info.md#remote_store.info) | Runtime introspection of available backends and extensions |
| [InfoResult](info.md#remote_store.InfoResult) | TypedDict for the `info()` return value |
| [BackendInfo](info.md#remote_store.BackendInfo) | TypedDict for a single backend entry in `InfoResult` |
| [ExtensionInfo](info.md#remote_store.ExtensionInfo) | TypedDict for a single extension entry in `InfoResult` |

## Functions

| Function | Description |
|----------|-------------|
| [register_backend](registry.md#remote_store.register_backend) | Register a custom backend type |

## Extensions

| Module | Description |
|--------|-------------|
| [ext.arrow](extensions/arrow.md) | PyArrow `FileSystemHandler` adapter for Store |
| [ext.batch](extensions/batch.md) | Batch delete, copy, and exists operations |
| [ext.cache](extensions/cache.md) | Store-level caching middleware with TTL |
| [ext.dagster](extensions/dagster.md) | Dagster IO Manager adapter for Store |
| [ext.glob](extensions/glob.md) | Portable glob pattern matching fallback |
| [ext.integrity](extensions/integrity.md) | Checksum computation and verification helpers |
| [ext.observe](extensions/observe.md) | Callback hooks for store operations |
| [ext.otel](extensions/otel.md) | OpenTelemetry bridge for ext.observe |
| [ext.partition](extensions/partition.md) | Hive-style partition path helpers |
| [ext.pydantic](extensions/pydantic.md) | Pydantic model to RegistryConfig adapter |
| [ext.streams](extensions/streams.md) | Composable BinaryIO wrappers for progress and checksums |
| [ext.transfer](extensions/transfer.md) | Upload, download, and cross-store transfer |
| [ext.yaml](extensions/yaml.md) | YAML config loader (PyYAML / ruamel.yaml) |
