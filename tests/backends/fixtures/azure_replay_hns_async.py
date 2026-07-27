"""``azure_replay_hns_async`` fixture: AsyncAzureBackend replaying the live HNS cassettes.

Stage 1, kind=replay, async. The async sibling of ``azure_replay_hns`` (BK-303).
Like ``azure_replay_async`` it injects ``AsyncioRequestsTransport`` because
vcrpy's aiohttp stub cannot stream a response body on replay (still measured on
vcrpy 8.3.0 under BK-326; see ``azure_replay_async``); every
``AsyncAzureBackend`` code path and ``azure.core`` async pipeline policy still
runs, only the bottom transport leaf differs (``azure_live_hns_async`` with the
real ``AioHttpTransport`` remains the source of truth for transport-leaf defects).

Builds against ``FAKE_FILESYSTEM`` / ``FAKE_CONN_STR``; cassette naming and the
missing-cassette skip are identical to ``azure_replay_hns``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._cassettes_azure import AZURE_PROFILE, FAKE_CONN_STR, FAKE_FILESYSTEM
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta = load_fixture("azure_replay_hns_async")


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
