"""Backend-agnostic remote storage abstraction."""

import logging

from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter
from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import (
    BackendConfig,
    RegistryConfig,
    RetryPolicy,
    Secret,
    SecretRedactionFilter,
    StoreProfile,
    resolve_env,
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
from remote_store._info import BackendInfo, ExtensionInfo, InfoResult, info
from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo, PathEntry, WriteResult
from remote_store._path import RemotePath
from remote_store._proxy import ProxyStore
from remote_store._registry import Registry, register_backend
from remote_store._resolution import ResolutionPlan
from remote_store._store import Store
from remote_store.ext.batch import BatchResult, batch_copy, batch_delete, batch_exists
from remote_store.ext.cache import CacheBackend, CachedStore, CacheStats, MemoryCache, cache
from remote_store.ext.glob import glob_files
from remote_store.ext.integrity import checksum, content_digest, verify, verify_hex
from remote_store.ext.observe import (
    BufferedObserver,
    ObservedStore,
    StoreEvent,
    observe,
    set_correlation_id,
)
from remote_store.ext.partition import ParsedPartition, parse_partition, partition_path
from remote_store.ext.streams import ChecksumReader, ChecksumWriter, ProgressReader, ProgressWriter, read_with_progress
from remote_store.ext.transfer import download, transfer, upload

__version__ = "0.23.0"

logging.getLogger("remote_store").addHandler(logging.NullHandler())

__all__ = [
    # Core
    "Store",
    "ProxyStore",
    "Registry",
    "Backend",
    "AsyncBackendSyncAdapter",
    "register_backend",
    # Path & Models
    "RemotePath",
    "ResolutionPlan",
    "ContentDigest",
    "FileInfo",
    "FolderEntry",
    "FolderInfo",
    "PathEntry",
    "WriteResult",
    # Capabilities
    "Capability",
    "CapabilitySet",
    # Config
    "BackendConfig",
    "StoreProfile",
    "RegistryConfig",
    "RetryPolicy",
    "Secret",
    "SecretRedactionFilter",
    "resolve_env",
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
    "cache",
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
    # Integrity helpers
    "checksum",
    "content_digest",
    "verify",
    "verify_hex",
    # Stream wrappers
    "ProgressReader",
    "ProgressWriter",
    "ChecksumReader",
    "ChecksumWriter",
    "read_with_progress",
    # Transfer operations
    "upload",
    "download",
    "transfer",
    # Introspection
    "BackendInfo",
    "ExtensionInfo",
    "InfoResult",
    "info",
    # Version
    "__version__",
]

# Optional-dependency extensions (arrow, otel, pydantic, yaml, dagster) are
# NOT re-exported here.  Import them from their module directly, e.g.
# ``from remote_store.ext.arrow import pyarrow_fs``.  See ADR-0013.
