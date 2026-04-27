"""Async Store and Backend API for remote_store."""

from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio._async_store import AsyncStore
from remote_store.aio._sync_adapter import SyncBackendAdapter
from remote_store.aio._types import AsyncWritableContent
from remote_store.aio.backends._memory import AsyncMemoryBackend

__all__ = [
    "AsyncBackend",
    "AsyncMemoryBackend",
    "AsyncStore",
    "AsyncWritableContent",
    "SyncBackendAdapter",
]

try:
    from remote_store.aio.backends._azure import AsyncAzureBackend

    __all__ = [*__all__, "AsyncAzureBackend"]
except ImportError:  # pragma: no cover
    pass
