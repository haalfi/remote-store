"""Backend-agnostic remote storage abstraction."""

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import BackendConfig, RegistryConfig, StoreProfile
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo, RemoteFile, RemoteFolder
from remote_store._path import RemotePath
from remote_store._registry import Registry, register_backend
from remote_store._store import Store

__version__ = "0.4.1"

__all__ = [
    # Core
    "Store",
    "Registry",
    "Backend",
    "register_backend",
    # Path & Models
    "RemotePath",
    "FileInfo",
    "FolderInfo",
    "RemoteFile",
    "RemoteFolder",
    # Capabilities
    "Capability",
    "CapabilitySet",
    # Config
    "BackendConfig",
    "StoreProfile",
    "RegistryConfig",
    # Errors
    "RemoteStoreError",
    "NotFound",
    "AlreadyExists",
    "PermissionDenied",
    "InvalidPath",
    "CapabilityNotSupported",
    "BackendUnavailable",
    # Version
    "__version__",
]
