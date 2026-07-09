# Errors

## RemoteStoreError

```
RemoteStoreError(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `Exception`

Base class for all remote_store errors.

Parameters:

- **`message`** (`str`, default: `''` ) – Human-readable error description.
- **`path`** (`str | None`, default: `None` ) – The path involved in the error, if any.
- **`backend`** (`str | None`, default: `None` ) – The backend name involved, if any.

## NotFound

```
NotFound(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised when a file or folder does not exist.

Raised by read, delete, metadata, move, and copy operations when the target path does not exist.

## AlreadyExists

```
AlreadyExists(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised when a target already exists and overwrite is not allowed.

Raised by write and copy operations when `overwrite=False` (the default) and the destination already exists.

## PermissionDenied

```
PermissionDenied(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised when access is denied by the storage backend.

Raised by any Store or Backend method when the underlying storage system denies access (e.g., missing credentials, insufficient permissions on the bucket or container).

## InvalidPath

```
InvalidPath(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised for malformed, unsafe, out-of-scope, or wrong-type paths.

Raised by any method that validates paths: empty strings in file-targeted operations, paths containing `..` or null bytes, paths that fall outside the store's root scope, and paths that name the wrong type (e.g. a file operation on a directory path, or a folder operation on a file path).

## CapabilityNotSupported

```
CapabilityNotSupported(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
    capability: str = "",
)
```

Bases: `RemoteStoreError`

Raised when an operation requires an unsupported capability.

Raised by capability-gated Store methods and by `CapabilitySet.require()` when a backend does not declare the needed capability. Check `Store.supports()` before calling capability-gated methods.

Parameters:

- **`capability`** (`str`, default: `''` ) – The name of the unsupported capability.

## DirectoryNotEmpty

```
DirectoryNotEmpty(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised when a non-recursive delete targets a non-empty folder.

Raised by `Store.delete_folder()` when `recursive=False` (the default) and the folder contains files or subfolders.

## BackendUnavailable

```
BackendUnavailable(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised when the backend cannot be reached or initialized.

Raised during backend construction or first operation when the storage service is unreachable (e.g., network error, invalid endpoint, missing container).

## ResourceLocked

```
ResourceLocked(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised when a target resource is locked by another session.

The resource exists and the caller is authorised, but another session or process holds it (e.g. an open Office co-authoring session), so the operation cannot proceed now. Not retried by the default policy: the lock has no `Retry-After` and may last indefinitely. Maps from Microsoft Graph `423 Locked`.

## See also

- [Troubleshooting](https://docs.remotestore.dev/stable/guides/troubleshooting/index.md) — diagnosing and resolving common errors
- [Error Handling example](https://docs.remotestore.dev/stable/tutorial/examples/error-handling/index.md) — catching and handling store errors
