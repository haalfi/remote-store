# API Reference

Complete reference for all public exports of `remote-store`.

## Core

| Class | Description |
|-------|-------------|
| [Store](store.md) | Main entry point for all file operations |
| [Registry](registry.md) | Creates and manages backend instances and stores |
| [Backend](backend.md) | Abstract base class for storage backends |

## Configuration

| Class | Description |
|-------|-------------|
| [RegistryConfig](config.md#remote_store.RegistryConfig) | Top-level configuration holding backends and stores |
| [BackendConfig](config.md#remote_store.BackendConfig) | Configuration for a single backend |
| [StoreProfile](config.md#remote_store.StoreProfile) | Configuration for a single store |

## Path & Models

| Class | Description |
|-------|-------------|
| [RemotePath](path.md) | Validated, immutable path value object |
| [FileInfo](models.md#remote_store.FileInfo) | Metadata for a file (name, size, modified time) |
| [FolderInfo](models.md#remote_store.FolderInfo) | Metadata for a folder |

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
| [ext.glob](ext-glob.md) | Portable glob pattern matching fallback |
| [ext.observe](ext-observe.md) | Callback hooks for store operations |
| [ext.otel](ext-otel.md) | OpenTelemetry bridge for ext.observe |
| [ext.partition](ext-partition.md) | Hive-style partition path helpers |
| [ext.pydantic](ext-pydantic.md) | Pydantic model to RegistryConfig adapter |
| [ext.transfer](ext-transfer.md) | Upload, download, and cross-store transfer |
| [ext.yaml](ext-yaml.md) | YAML config loader (PyYAML / ruamel.yaml) |
