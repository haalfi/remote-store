"""Shared test fixtures and marker registration."""

from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, settings

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

# -- Hypothesis profiles (dev=50, ci=100, nightly=1000) --
# Activate via HYPOTHESIS_PROFILE env var (e.g. HYPOTHESIS_PROFILE=ci).
settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("nightly", max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_configure(config: object) -> None:
    """Register custom markers."""
    if isinstance(config, pytest.Config):
        config.addinivalue_line("markers", "spec(id): links test to a spec section ID")
        config.addinivalue_line("markers", "integration: requires external services")
        config.addinivalue_line("markers", "requires_docker: test needs Docker services (e.g. Azurite)")
        config.addinivalue_line(
            "markers",
            "os_sensitive: exercises OS-specific behaviour (paths, atomic writes, local filesystem); "
            "run on macOS and Windows CI",
        )
        config.addinivalue_line("markers", "pbt: property-based test using Hypothesis")


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
