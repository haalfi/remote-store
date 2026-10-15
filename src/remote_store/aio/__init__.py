"""Async Store and Backend API for remote_store."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio._async_store import AsyncStore
from remote_store.aio._sync_adapter import SyncBackendAdapter
from remote_store.aio._types import AsyncWritableContent

if TYPE_CHECKING:
    from remote_store.aio.backends._memory import AsyncMemoryBackend, AsyncMemoryDriver

__all__ = [
    "AsyncBackend",
    "AsyncMemoryBackend",
    "AsyncMemoryDriver",
    "AsyncStore",
    "AsyncWritableContent",
    "SyncBackendAdapter",
]

try:
    from remote_store.aio.backends import AsyncAzureBackend

    __all__ = [*__all__, "AsyncAzureBackend"]
except ImportError:  # pragma: no cover
    pass

try:
    from remote_store.aio.backends import GraphAuth, GraphBackend, GraphUtils

    __all__ = [*__all__, "GraphAuth", "GraphBackend", "GraphUtils"]
except ImportError:  # pragma: no cover
    pass


def __getattr__(name: str) -> Any:
    # Lazy for the reason ``remote_store.aio.backends`` gives: the Memory classes
    # are on the async kernel, whose module imports this package.
    if name in ("AsyncMemoryBackend", "AsyncMemoryDriver"):
        from remote_store.aio.backends import _memory

        return getattr(_memory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    # The lazy names are listed too, so dir(), inspect and pydoc see them.
    return sorted({*globals(), "AsyncMemoryBackend", "AsyncMemoryDriver"})
