"""Backend-agnostic remote storage abstraction."""

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import BackendConfig, RegistryConfig, StoreProfile
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo
from remote_store._path import RemotePath
from remote_store._registry import Registry, register_backend
from remote_store._store import Store
from remote_store.ext.batch import BatchResult, batch_copy, batch_delete, batch_exists
from remote_store.ext.glob import glob_files
from remote_store.ext.transfer import download, transfer, upload

__version__ = "0.10.0"

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
    "DirectoryNotEmpty",
    "BackendUnavailable",
    # Batch operations
    "BatchResult",
    "batch_delete",
    "batch_copy",
    "batch_exists",
    # Glob operations
    "glob_files",
    # Transfer operations
    "upload",
    "download",
    "transfer",
    # Version
    "__version__",
]

# Optional PyArrow extension (available when pyarrow is installed)
try:
    from remote_store.ext.arrow import StoreFileSystemHandler, pyarrow_fs

    __all__ += ["StoreFileSystemHandler", "pyarrow_fs"]
except ImportError:
    # PyArrow not installed or broken — don't crash the core package.
    pass
