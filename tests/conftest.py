"""Shared test fixtures and marker registration."""

from __future__ import annotations

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend


def pytest_configure(config: object) -> None:
    """Register custom markers."""
    if isinstance(config, pytest.Config):
        config.addinivalue_line("markers", "spec(id): links test to a spec section ID")
        config.addinivalue_line("markers", "integration: requires external services")


# region: shared fixtures


@pytest.fixture
def mem_backend() -> MemoryBackend:
    """Fresh MemoryBackend instance."""
    return MemoryBackend()


@pytest.fixture
def mem_store() -> Store:
    """Store backed by a fresh MemoryBackend with no root_path."""
    return Store(backend=MemoryBackend())


# endregion


# region: shared test helpers


class RestrictedBackend:
    """Backend wrapper that removes specific capabilities for testing.

    Delegates all methods to the inner MemoryBackend but overrides the
    ``capabilities`` property to return a restricted ``CapabilitySet``.
    """

    def __init__(self, backend: MemoryBackend, exclude: set[Capability]) -> None:
        self._inner = backend
        self._caps = CapabilitySet(set(Capability) - exclude)

    @property
    def capabilities(self) -> CapabilitySet:
        return self._caps

    @property
    def name(self) -> str:
        return self._inner.name

    def __getattr__(self, item: str) -> object:
        return getattr(self._inner, item)


def make_restricted_store(exclude: set[Capability]) -> Store:
    """Create a Store whose backend lacks the given capabilities."""
    backend = MemoryBackend()
    backend.write("test.txt", b"hello")
    backend.write("folder/a.txt", b"data")
    restricted = RestrictedBackend(backend, exclude)
    return Store(backend=restricted, root_path="")  # type: ignore[arg-type]


# endregion
