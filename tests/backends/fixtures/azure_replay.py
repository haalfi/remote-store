"""``azure_replay`` fixture: AzureBackend replaying from a committed cassette.

Stage 1, kind=replay.  Exercises the full ``AzureBackend`` code path and
the ``azure.core`` pipeline against recorded cassette files stored under
``tests/backends/cassettes/azure/``.  No network access; no live credentials.

The fixture is registered with ``pytest.mark.vcr(record_mode="none")``, which
forces replay mode even when the session is running with ``--record-mode=rewrite``
(i.e., when the developer uses ``pytest --stage=3 --record`` to refresh the
``azure_live`` cassettes).  This prevents the replay fixture from accidentally
overwriting cassettes with traffic from a fake connection string.

Cassette naming
---------------
The conformance conftest's ``default_cassette_name`` fixture normalises the
parametrize suffix ``[azure_replay]`` → ``[azure]`` so that the cassette
recorded from ``azure_live`` (``…[azure]``) and the one read by ``azure_replay``
share a single file.

Missing cassettes
-----------------
If the cassette for a given test is absent, the conformance conftest's
``pytest_collection_modifyitems`` hook marks that parametrize id as skip
rather than letting vcrpy raise — per TEST-007.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._cassettes_azure import AZURE_PROFILE, FAKE_CONN_STR, FAKE_FILESYSTEM
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("azure_replay")


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
        # record_mode="none" forces replay even when --record is active;
        # prevents overwriting cassettes with fake-connection-string traffic.
        marks=(pytest.mark.vcr(record_mode="none"),),
        cassette_profile=AZURE_PROFILE,
        **_meta.to_kwargs(),
    )
)
