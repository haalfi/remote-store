"""``memory`` fixture: pure in-process MemoryBackend.

Stage 1, real-local. Always available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store.backends._memory import MemoryBackend
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("memory")


def _factory() -> MemoryBackend:
    return MemoryBackend()


def _cleanup(backend: Backend) -> None:
    # On the contract kernel close() is the kernel's, which closes the driver;
    # Memory's releases nothing, but the class overrides Backend.close.
    backend.close()


register(
    BackendFixture(
        factory=_factory,
        capabilities=frozenset(MemoryBackend.CAPABILITIES),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
