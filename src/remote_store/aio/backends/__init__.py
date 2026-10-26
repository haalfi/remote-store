"""Async backend implementations."""

from remote_store.aio.backends._memory import AsyncMemoryBackend

__all__ = ["AsyncMemoryBackend"]

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
