"""Normalized error hierarchy for remote_store."""

from __future__ import annotations


class RemoteStoreError(Exception):
    """Base class for all remote_store errors.

    Args:
        message: Human-readable error description.
        path: The path involved in the error, if any.
        backend: The backend name involved, if any.
    """

    def __init__(self, message: str = "", *, path: str | None = None, backend: str | None = None) -> None:
        self.path = path
        self.backend = backend
        super().__init__(message)

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.path is not None:
            parts.append(f"path={self.path!r}")
        if self.backend is not None:
            parts.append(f"backend={self.backend!r}")
        return " | ".join(parts) if len(parts) > 1 else parts[0]

    def __repr__(self) -> str:
        cls = type(self).__name__
        args = [repr(super().__str__())]
        if self.path is not None:
            args.append(f"path={self.path!r}")
        if self.backend is not None:
            args.append(f"backend={self.backend!r}")
        return f"{cls}({', '.join(args)})"


class NotFound(RemoteStoreError):
    """Raised when a file or folder does not exist.

    Raised by ``Store.read()``, ``Store.read_bytes()``, ``Store.delete()``,
    ``Store.delete_folder()``, ``Store.get_file_info()``,
    ``Store.get_folder_info()``, ``Store.move()``, and ``Store.copy()``
    when the target path does not exist.
    """


class AlreadyExists(RemoteStoreError):
    """Raised when a target already exists and overwrite is not allowed.

    Raised by ``Store.write()``, ``Store.write_atomic()``,
    ``Store.open_atomic()``, ``Store.move()``, and ``Store.copy()``
    when ``overwrite=False`` (the default) and the destination exists.
    """


class PermissionDenied(RemoteStoreError):
    """Raised when access is denied by the storage backend.

    Raised by any Store or Backend method when the underlying storage
    system denies access (e.g., missing credentials, insufficient
    permissions on the bucket or container).
    """


class InvalidPath(RemoteStoreError):
    """Raised for malformed, unsafe, or out-of-scope paths.

    Raised by any method that validates paths: empty strings in file-targeted
    operations, paths containing ``..`` or null bytes, and paths that fall
    outside the store's root scope.
    """


class CapabilityNotSupported(RemoteStoreError):
    """Raised when an operation requires an unsupported capability.

    Raised by capability-gated methods (``Store.glob()``,
    ``Store.write_atomic()``, ``Store.open_atomic()``, ``Store.unwrap()``)
    and by ``CapabilitySet.require()`` when a backend does not declare
    the needed capability.

    Args:
        capability: The name of the unsupported capability.
    """

    def __init__(
        self,
        message: str = "",
        *,
        path: str | None = None,
        backend: str | None = None,
        capability: str = "",
    ) -> None:
        self.capability = capability
        super().__init__(message, path=path, backend=backend)

    def __str__(self) -> str:
        base = super().__str__()
        if self.capability:
            if " | " in base or base:
                return f"{base} | capability={self.capability!r}"
            return f"capability={self.capability!r}"
        return base

    def __repr__(self) -> str:
        cls = type(self).__name__
        args = [repr(self.args[0] if self.args else "")]
        if self.path is not None:
            args.append(f"path={self.path!r}")
        if self.backend is not None:
            args.append(f"backend={self.backend!r}")
        if self.capability:
            args.append(f"capability={self.capability!r}")
        return f"{cls}({', '.join(args)})"


class DirectoryNotEmpty(RemoteStoreError):
    """Raised when a non-recursive delete targets a non-empty folder.

    Raised by ``Store.delete_folder()`` when ``recursive=False`` (the
    default) and the folder contains files or subfolders.
    """


class BackendUnavailable(RemoteStoreError):
    """Raised when the backend cannot be reached or initialized.

    Raised during backend construction or first operation when the
    storage service is unreachable (e.g., network error, invalid
    endpoint, missing container).
    """


# ---------------------------------------------------------------------------
# Error factory helpers
# ---------------------------------------------------------------------------
# Short-hand constructors that eliminate the repeated
# ``ErrorType(f"...: {path}", path=path, backend=backend)`` boilerplate
# across backends.


def _not_found(path: str, backend: str) -> NotFound:
    """Create a ``NotFound`` with canonical message formatting."""
    return NotFound(f"Not found: {path}", path=path, backend=backend)


def _permission_denied(path: str, backend: str) -> PermissionDenied:
    """Create a ``PermissionDenied`` with canonical message formatting."""
    return PermissionDenied(f"Permission denied: {path}", path=path, backend=backend)


def _classify_by_message(exc: Exception, path: str, backend: str) -> RemoteStoreError:
    """Heuristic fallback classifier based on exception message text.

    Backends with structured SDK errors (e.g. botocore
    ``ClientError.response['Error']['Code']``) should classify those
    first and call this only for unrecognised exceptions.
    """
    msg = str(exc).lower()
    if "404" in msg or "nosuchkey" in msg or "nosuchbucket" in msg or "not found" in msg:
        return _not_found(path, backend)
    if "403" in msg or "accessdenied" in msg or "access denied" in msg:
        return _permission_denied(path, backend)
    if any(kw in msg for kw in ("endpoint", "connect", "timeout", "dns", "name or service")):
        return BackendUnavailable(str(exc), path=path, backend=backend)
    return RemoteStoreError(str(exc), path=path, backend=backend)
