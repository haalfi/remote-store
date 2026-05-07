"""``dafny_oracle`` fixture: Dafny-derived MemoryBackend conformance oracle.

Stage 1, real-local. The oracle implementation lives at
``tests/backends/dafny/_helpers.py``. It runs entirely in-process; the
conformance suite uses it as a second in-memory implementation to
cross-check semantic divergence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.backends.dafny._helpers import DafnyOracleBackend
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend


def _factory() -> Backend:
    return DafnyOracleBackend()


register(
    BackendFixture(
        name="dafny_oracle",
        backend="dafny",
        factory=_factory,
        stage=1,
        kind="real-local",
        capabilities=frozenset(DafnyOracleBackend.CAPABILITIES),
        is_async=False,
        cleanup=None,
    )
)
