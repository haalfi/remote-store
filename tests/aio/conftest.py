"""Fixtures for async API tests."""

from __future__ import annotations

import pytest

from remote_store.aio import AsyncMemoryBackend, AsyncStore, SyncBackendAdapter
from remote_store.backends._memory import MemoryBackend


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
