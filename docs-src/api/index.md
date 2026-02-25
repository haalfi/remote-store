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
| [RemoteFile](models.md#remote_store.RemoteFile) | Context manager wrapping a readable binary stream |
| [RemoteFolder](models.md#remote_store.RemoteFolder) | Iterable of files and subfolders |

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
