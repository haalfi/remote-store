"""``dafny_oracle_async`` fixture: async surface over the verified MemoryBackend.

Stage 1, real-local, ``is_async=True``. Composes
``SyncBackendAdapter(DafnyOracleBackend())`` so the async conformance suite
runs against the correct-by-construction Dafny oracle — closing the (T) gap
ID-210 names: the async-shaped contract was previously cross-checked between
two Python implementations (``AsyncMemoryBackend`` and
``SyncBackendAdapter(MemoryBackend())``) rather than against a
verified-by-construction oracle.

The adapter (``SyncBackendAdapter``) is itself certified by
``test_sync_adapter_conformance.py`` (ASYNC-030..ASYNC-035); composing it
with the verified sync oracle keeps both legs honest end-to-end. Native
async semantics that a ``to_thread``-bridged sync backend cannot express
(concurrency ordering, mid-await cancellation) are out of scope — see the
ID-210 backlog "Open question" for the bridged-first rationale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store.aio import SyncBackendAdapter
from tests.backends.dafny._helpers import DafnyOracleBackend
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta = load_fixture("dafny_oracle_async")


def _factory() -> AsyncBackend:
    return SyncBackendAdapter(DafnyOracleBackend())


def _cleanup(backend: AsyncBackend) -> None:
    """Mirror the sync ``dafny_oracle`` cleanup.

    ``SyncBackendAdapter.aclose`` would call ``DafnyOracleBackend.close()``,
    but conformance teardown for sync-wrapped async fixtures runs through
    ``cleanup`` (the adapter exposes no per-sync-close hook). Calling
    ``close()`` on the wrapped oracle directly exercises BE-020 idempotency
    on every parametrize iteration, matching the sync ``dafny_oracle``
    fixture.
    """
    backend._sync.close()  # type: ignore[attr-defined]


register(
    BackendFixture(
        factory=_factory,
        capabilities=frozenset(DafnyOracleBackend.CAPABILITIES),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
