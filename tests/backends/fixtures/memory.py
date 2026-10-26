"""``memory`` fixture: pure in-process MemoryBackend.

Stage 1, real-local. Always available.
"""

from __future__ import annotations

from remote_store.backends._memory import MemoryBackend
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

_meta = load_fixture("memory")


def _factory() -> MemoryBackend:
    return MemoryBackend()


register(
    BackendFixture(
        factory=_factory,
        capabilities=frozenset(MemoryBackend.CAPABILITIES),
        cleanup=None,
        **_meta.to_kwargs(),
    )
)
