"""``dafny_oracle`` fixture: Dafny-derived MemoryBackend conformance oracle.

Stage 1, real-local. The oracle implementation lives at
``tests/backends/dafny/_helpers.py``. It runs entirely in-process; the
conformance suite uses it as a second in-memory implementation to
cross-check semantic divergence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.backends.dafny._helpers import DafnyOracleBackend
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("dafny_oracle")


def _factory() -> Backend:
    return DafnyOracleBackend()


def _cleanup(backend: Backend) -> None:
    """Call ``backend.close()`` for parity with the other fixtures.

    ``DafnyOracleBackend.close()`` drives the model's ``Close()``, which
    sets ``closed`` on the non-terminal ``MemoryBackend``. Wiring
    ``cleanup`` here runs it on every conformance iteration, and keeps
    ``TestFixtureCleanupContract`` satisfied for the override.
    """
    backend.close()


register(
    BackendFixture(
        factory=_factory,
        capabilities=frozenset(DafnyOracleBackend.CAPABILITIES),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
