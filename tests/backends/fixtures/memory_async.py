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
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta_native = load_fixture("memory_async_native")
_meta_adapted = load_fixture("memory_async_adapted")


def _native_factory() -> AsyncBackend:
    return AsyncMemoryBackend()


def _adapted_factory() -> AsyncBackend:
    return SyncBackendAdapter(MemoryBackend())


register(
    BackendFixture(
        factory=_native_factory,
        capabilities=frozenset(AsyncMemoryBackend.CAPABILITIES),
        cleanup=None,
        **_meta_native.to_kwargs(),
    )
)


register(
    BackendFixture(
        factory=_adapted_factory,
        capabilities=frozenset(MemoryBackend.CAPABILITIES),
        cleanup=None,
        **_meta_adapted.to_kwargs(),
    )
)
