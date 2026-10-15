"""Async backend implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remote_store.aio.backends._memory import AsyncMemoryBackend, AsyncMemoryDriver

__all__ = ["AsyncMemoryBackend", "AsyncMemoryDriver"]

try:
    from remote_store.aio.backends._azure import AsyncAzureBackend

    __all__ = [*__all__, "AsyncAzureBackend"]
except ImportError:  # pragma: no cover
    pass

try:
    from remote_store.aio.backends._graph import GraphAuth, GraphBackend, GraphUtils

    __all__ = [*__all__, "GraphAuth", "GraphBackend", "GraphUtils"]
except ImportError:  # pragma: no cover
    pass


def __getattr__(name: str) -> Any:
    # The Memory classes are on the async contract kernel, whose module imports
    # this package's AsyncBackend; importing them here eagerly would cycle when
    # the kernel module is the first one imported.
    if name in ("AsyncMemoryBackend", "AsyncMemoryDriver"):
        from remote_store.aio.backends import _memory

        return getattr(_memory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
