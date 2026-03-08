"""Backend-agnostic remote storage abstraction."""

import logging

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import (
    BackendConfig,
    RegistryConfig,
    Secret,
    SecretRedactionFilter,
    StoreProfile,
)
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
from remote_store.ext.cache import CacheBackend, CachedStore, CacheStats, MemoryCache, cached_store
from remote_store.ext.glob import glob_files
from remote_store.ext.observe import (
    BufferedObserver,
    ObservedStore,
    StoreEvent,
    observe,
    set_correlation_id,
)
from remote_store.ext.partition import ParsedPartition, parse_partition, partition_path
from remote_store.ext.transfer import download, transfer, upload

__version__ = "0.14.0"

logging.getLogger("remote_store").addHandler(logging.NullHandler())

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
    "Secret",
    "SecretRedactionFilter",
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
    # Cache operations
    "CacheBackend",
    "CachedStore",
    "CacheStats",
    "MemoryCache",
    "cached_store",
    # Glob operations
    "glob_files",
    # Partition helpers
    "ParsedPartition",
    "parse_partition",
    "partition_path",
    # Observe operations
    "BufferedObserver",
    "ObservedStore",
    "StoreEvent",
    "observe",
    "set_correlation_id",
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

# Optional OpenTelemetry extension (available when opentelemetry-api is installed)
try:
    from remote_store.ext.otel import otel_hooks, otel_observe

    __all__ += ["otel_hooks", "otel_observe"]
except ImportError:
    # opentelemetry-api not installed — don't crash the core package.
    pass

# Optional Pydantic extension (available when pydantic is installed)
try:
    from remote_store.ext.pydantic import pydantic_to_registry_config

    __all__ += ["pydantic_to_registry_config"]
except ImportError:
    # pydantic not installed — don't crash the core package.
    pass
