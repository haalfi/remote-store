"""``azure_replay_hns`` fixture: AzureBackend replaying the live HNS cassettes.

Stage 1, kind=replay. The creds-free replay tier for the live HNS deviation
suite (BK-303), the HNS analogue of ``azure_replay``. Builds the backend
against ``FAKE_FILESYSTEM`` / ``FAKE_CONN_STR`` — no network, no live account.

The HNS suite's per-session ``live-hns/<uuid8>`` prefix and the real
``RS_TEST_LIVE_HNS_CONTAINER`` filesystem name are normalised by the
``azure.uri.hns-prefix`` / ``azure.hns-container`` scrub rules to the fixed
``live-hns/REPLAY`` prefix and ``FAKE_FILESYSTEM`` respectively, so the backend
this fixture builds replays cassette URLs that match.

``record_mode="none"`` forces replay even under ``--record`` so the fixture can
never overwrite cassettes with fake-connection-string traffic. The azure-subtree
conftest's ``default_cassette_name`` aliases ``[azure_replay_hns]`` →
``[azure_hns]`` so this fixture and ``azure_live_hns`` share one cassette file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._cassettes_azure import AZURE_PROFILE, FAKE_CONN_STR, FAKE_FILESYSTEM
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("azure_replay_hns")


def _factory() -> Backend:
    try:
        from remote_store.backends._azure import AzureBackend  # noqa: PLC0415
    except ImportError:
        pytest.skip("azure-storage-file-datalake not installed")

    return AzureBackend(container=FAKE_FILESYSTEM, hns=True, connection_string=FAKE_CONN_STR)


def _cleanup(backend: Backend) -> None:
    backend.close()


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
        # record_mode="none" forces replay even when --record is active.
        marks=(pytest.mark.vcr(record_mode="none"),),
        cassette_profile=AZURE_PROFILE,
        **_meta.to_kwargs(),
    )
)
