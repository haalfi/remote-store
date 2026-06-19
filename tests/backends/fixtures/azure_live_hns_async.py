"""``azure_live_hns_async`` fixture: AsyncAzureBackend against a real ADLS Gen2 account (HNS deviation tier).

Stage 3, real-live, async. The async sibling of ``azure_live_hns`` (BK-303),
the recordable form of ``tests/backends/azure/aio/test_live_hns.py``. Targets
the persistent ``RS_TEST_LIVE_HNS_CONTAINER`` filesystem; the azure-subtree
``aio`` conftest provisions the per-test HNS directory.

Under ``_RS_CASSETTE_RECORDING=1`` the async backend injects
``AsyncioRequestsTransport`` so vcrpy captures real streaming bodies — the same
shim ``azure_live_async`` uses (vcrpy 8.1.1's aiohttp stub drops streaming
bodies on record).

Gating, the dynamic ``pytest.mark.vcr`` under ``--record``, and ``strict_only``
match ``azure_live_hns``.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._cassettes_azure import AZURE_PROFILE
from tests.backends.fixtures._live_env import (
    require_azure_live_connection_string,
    require_azure_live_hns_container,
)
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta = load_fixture("azure_live_hns_async")


_LOG = logging.getLogger(__name__)


def _factory() -> AsyncBackend:
    if os.environ.get("RS_TEST_LIVE_HNS") != "1":
        pytest.skip("azure_live_hns_async opt-in via RS_TEST_LIVE_HNS=1")
    try:
        import azure.storage.filedatalake  # noqa: F401, PLC0415
    except ImportError:
        pytest.skip("azure-storage-file-datalake not installed")

    from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: PLC0415

    conn = require_azure_live_connection_string()
    fs_name = require_azure_live_hns_container()
    client_options: dict[str, object] = {}
    if os.environ.get("_RS_CASSETTE_RECORDING") == "1":
        # vcrpy 8.1.1's aiohttp stub drops streaming response bodies on record.
        # Inject AsyncioRequestsTransport so the cassette captures real bodies.
        try:
            from azure.core.pipeline.transport import AsyncioRequestsTransport  # noqa: PLC0415

            client_options = {"transport": AsyncioRequestsTransport()}
        except ImportError:
            pass
    return AsyncAzureBackend(container=fs_name, hns=True, connection_string=conn, client_options=client_options or None)


async def _aclose(backend: AsyncBackend) -> None:
    """Await the async backend's network-pool teardown."""
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
        marks=(pytest.mark.live,),
        cassette_profile=AZURE_PROFILE,
        **_meta.to_kwargs(),
    )
)
