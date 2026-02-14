"""Normalized error hierarchy for remote_store."""

from __future__ import annotations

from typing import Optional


class RemoteStoreError(Exception):
    """Base class for all remote_store errors.

    :param message: Human-readable error description.
    :param path: The path involved in the error, if any.
    :param backend: The backend name involved, if any.
    """

    def __init__(self, message: str = "", *, path: Optional[str] = None, backend: Optional[str] = None) -> None:
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
    """Raised when a file or folder does not exist."""


class AlreadyExists(RemoteStoreError):
    """Raised when a target already exists and overwrite is not allowed."""


class PermissionDenied(RemoteStoreError):
    """Raised when access is denied by the storage backend."""


class InvalidPath(RemoteStoreError):
    """Raised for malformed, unsafe, or out-of-scope paths."""


class CapabilityNotSupported(RemoteStoreError):
    """Raised when an operation requires an unsupported capability.

    :param capability: The name of the unsupported capability.
    """

    def __init__(
        self,
        message: str = "",
        *,
        path: Optional[str] = None,
        backend: Optional[str] = None,
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


class BackendUnavailable(RemoteStoreError):
    """Raised when the backend cannot be reached or initialized."""
