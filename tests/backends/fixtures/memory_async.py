"""Async ``memory`` fixtures: native AsyncMemoryBackend + adapted MemoryBackend.

Stage 1, real-local, ``is_async=True``. Two registry entries with the
same backend family (``memory``) so async conformance exercises both
the native async implementation and the SyncBackendAdapter wrapping
the sync MemoryBackend.

The two entries deliberately share a backend family because, from the
test perspective, both represent "memory backend, async surface". The
distinction is in the implementation path, captured by the fixture
``name``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store.aio import AsyncMemoryBackend, SyncBackendAdapter
from remote_store.backends._memory import MemoryBackend
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend


def _native_factory() -> AsyncBackend:
    return AsyncMemoryBackend()


def _adapted_factory() -> AsyncBackend:
    return SyncBackendAdapter(MemoryBackend())


register(
    BackendFixture(
        name="memory_async_native",
        backend="memory",
        factory=_native_factory,
        stage=1,
        kind="real-local",
        capabilities=frozenset(AsyncMemoryBackend.CAPABILITIES),
        is_async=True,
        cleanup=None,
    )
)


register(
    BackendFixture(
        name="memory_async_adapted",
        backend="memory",
        factory=_adapted_factory,
        stage=1,
        kind="real-local",
        capabilities=frozenset(MemoryBackend.CAPABILITIES),
        is_async=True,
        cleanup=None,
    )
)
