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

    ``DafnyOracleBackend`` does not override ``close()``; it inherits the
    ``Backend`` ABC default (a no-op). Wiring ``cleanup`` here exercises
    BE-020's idempotency contract on every conformance iteration and
    makes future overrides safe by construction.
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
