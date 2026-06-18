"""``azure_replay_async`` fixture: AsyncAzureBackend replaying from a committed cassette.

Stage 1, kind=replay, async.  Mirrors ``azure_replay`` for the async backend
surface.  Uses the full ``AsyncAzureBackend`` code path and ``azure.core``
async pipeline against recorded cassette files.

Transport shim
--------------
vcrpy 8.1.1's aiohttp stub cannot stream a response body — it deadlocks
``AioHttpTransport.__anext__`` on replay and drops the body silently on record
(PoC finding, see ``sdd/research/research-bk-181-cassette-replay-poc.md``).

The fix is ``AsyncioRequestsTransport``, an ``azure.core`` async transport that
runs ``requests``/urllib3 in a thread pool.  It is injected via the existing
``client_options`` kwarg so no production code is changed.  Every async Azure
backend code path (``AsyncAzureBackend``) and every ``azure.core`` pipeline
policy still runs; only the bottom transport leaf differs.

*Fidelity caveat*: defects that live purely in ``AioHttpTransport`` itself would
not be caught by replay.  ``azure_live_async`` (real ``AioHttpTransport``,
Stage 3) remains the source of truth for such defects.

Cassette naming and missing-cassette skip are identical to ``azure_replay``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._cassettes_azure import AZURE_PROFILE, FAKE_CONN_STR, FAKE_FILESYSTEM
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta = load_fixture("azure_replay_async")


def _factory() -> AsyncBackend:
    try:
        from azure.core.pipeline.transport import AsyncioRequestsTransport  # noqa: PLC0415

        from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: PLC0415
    except ImportError:
        pytest.skip("azure-storage-file-datalake not installed")

    return AsyncAzureBackend(
        container=FAKE_FILESYSTEM,
        hns=True,
        connection_string=FAKE_CONN_STR,
        client_options={"transport": AsyncioRequestsTransport()},
    )


async def _aclose(backend: AsyncBackend) -> None:
    """Drain the AsyncioRequestsTransport thread-pool before the next test."""
    await backend.aclose()


def _capabilities() -> frozenset:
    try:
        from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: PLC0415
    except ImportError:
        return frozenset()
    return frozenset(AsyncAzureBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        aclose=_aclose,
        # record_mode="none" forces replay even when --record is active.
        marks=(pytest.mark.vcr(record_mode="none"),),
        cassette_profile=AZURE_PROFILE,
        **_meta.to_kwargs(),
    )
)
