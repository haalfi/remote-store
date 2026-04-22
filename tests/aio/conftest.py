"""Fixtures for async API tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store.aio import AsyncMemoryBackend, AsyncStore, SyncBackendAdapter
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend


@pytest.fixture(params=["native", "adapted"], ids=["native", "adapted"])
def async_backend(request: pytest.FixtureRequest) -> AsyncMemoryBackend | SyncBackendAdapter:
    """Async backend -- both native AsyncMemoryBackend and adapted sync MemoryBackend."""
    if request.param == "native":
        return AsyncMemoryBackend()
    return SyncBackendAdapter(MemoryBackend())


@pytest.fixture
def async_store(async_backend: AsyncMemoryBackend | SyncBackendAdapter) -> AsyncStore:
    """AsyncStore backed by dual-parameterized backend."""
    return AsyncStore(async_backend, root_path="data")


@pytest.fixture
def native_memory() -> AsyncMemoryBackend:
    """Native AsyncMemoryBackend (for memory-specific tests)."""
    return AsyncMemoryBackend()


@pytest.fixture
def native_store(native_memory: AsyncMemoryBackend) -> AsyncStore:
    """AsyncStore with native AsyncMemoryBackend."""
    return AsyncStore(native_memory, root_path="data")


class RestrictedAsyncBackend:
    """Async backend wrapper that excludes specific capabilities for testing.

    Delegates all methods to the inner ``AsyncBackend`` but overrides the
    ``capabilities`` property to return a restricted ``CapabilitySet``.
    """

    def __init__(self, backend: AsyncBackend, exclude: set[Capability]) -> None:
        self._inner = backend
        self._caps = CapabilitySet(set(backend.capabilities) - exclude)

    @property
    def capabilities(self) -> CapabilitySet:
        return self._caps

    @property
    def name(self) -> str:
        return self._inner.name

    def __getattr__(self, item: str) -> object:
        return getattr(self._inner, item)
