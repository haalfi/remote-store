"""``memory`` fixture: pure in-process MemoryBackend.

Stage 1, real-local. Always available.
"""

from __future__ import annotations

from remote_store.backends._memory import MemoryBackend
from tests.backends.fixtures.registry import BackendFixture, register


def _factory() -> MemoryBackend:
    return MemoryBackend()


register(
    BackendFixture(
        name="memory",
        backend="memory",
        factory=_factory,
        stage=1,
        kind="real-local",
        capabilities=frozenset(MemoryBackend.CAPABILITIES),
        is_async=False,
        cleanup=None,
    )
)
