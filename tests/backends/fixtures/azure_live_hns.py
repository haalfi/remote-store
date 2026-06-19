"""``azure_live_hns`` fixture: AzureBackend against a real ADLS Gen2 account (HNS deviation tier).

Stage 3, real-live. The recordable form of the live HNS deviation suite
(``tests/backends/azure/test_live_hns.py``) — BK-303. Unlike ``azure_live``,
which mints a fresh ``conformance-<uuid>`` filesystem per call, this fixture
targets the **persistent** ``RS_TEST_LIVE_HNS_CONTAINER`` filesystem that the
HNS suite has always used: HNS directory-marker behaviour is exercised against
a long-lived account-specific filesystem, and per-test isolation comes from the
``live-hns/<uuid8>`` prefix the azure-subtree conftest provisions, not from a
per-call container.

The backend instance is all this factory owns; the azure-subtree conftest's
``_hns_dir`` fixture creates and tears down the HNS directory state. ``cleanup``
therefore only closes the backend — there is no filesystem to delete.

Gating mirrors ``azure_live``: ``--stage=3`` plus ``RS_TEST_LIVE_HNS=1``, with
``AZURE_STORAGE_CONNECTION_STRING`` a fail-loud precondition. ``pytest.mark.vcr``
is added dynamically by the root conftest only under ``--record``.
``conformance_excluded`` keeps the fixture off the conformance auto-walk in every
mode (a stronger guarantee than ``strict_only``, which the ``include_strict_only``
file-ancestor tests opt back in); it is consumed only by the azure-subtree conftest.
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
    from remote_store._backend import Backend

_meta = load_fixture("azure_live_hns")


_LOG = logging.getLogger(__name__)


def _factory() -> Backend:
    if os.environ.get("RS_TEST_LIVE_HNS") != "1":
        pytest.skip("azure_live_hns opt-in via RS_TEST_LIVE_HNS=1")
    try:
        import azure.storage.filedatalake  # noqa: F401, PLC0415
    except ImportError:
        pytest.skip("azure-storage-file-datalake not installed")

    from remote_store.backends._azure import AzureBackend  # noqa: PLC0415

    conn = require_azure_live_connection_string()
    fs_name = require_azure_live_hns_container()
    return AzureBackend(container=fs_name, hns=True, connection_string=conn)


def _cleanup(backend: Backend) -> None:
    try:
        backend.close()
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("backend.close() failed during cleanup", exc_info=True)


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._azure import AzureBackend  # noqa: PLC0415
    except ImportError:
        return frozenset()
    return frozenset(AzureBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        marks=(pytest.mark.live,),
        cassette_profile=AZURE_PROFILE,
        **_meta.to_kwargs(),
    )
)
