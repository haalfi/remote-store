"""``azure_live`` fixture: AzureBackend against a real ADLS Gen2 account.

Stage 3, real-live. Each factory call provisions a fresh HNS filesystem
(container) named ``conformance-<uuid>`` on the configured storage
account; cleanup deletes it. Per-call isolation keeps conformance tests
from leaking state into each other on a shared real account.

Gating
------

Two layers, both required:

1. ``--stage=3`` (or ``RS_TEST_STAGE=3``). Lower stages exclude this
   fixture from the registry walk and no parametrize id is generated.
2. ``RS_TEST_LIVE_HNS=1`` env var. When unset, the factory calls
   ``pytest.skip(...)`` per TEST-006 — collection still succeeds and
   tests parametrised over other backends still run.

Once both are set, ``AZURE_STORAGE_CONNECTION_STRING`` becomes a
fail-loud precondition: empty or pointing-at-Azurite is a configuration
bug, not a reason to silent-skip a test the user explicitly opted into
(see ``_live_env.require_azure_live_connection_string``).

The ``pytest.mark.live`` mark rides along with the parametrize entry so
the default ``addopts = -m 'not live'`` deselects every test
parametrised over this fixture unless the user opts in with ``-m live``.

Cost discipline
---------------

Each factory call performs one create-filesystem and one delete-filesystem
SDK round trip; data-plane traffic per test stays small because
conformance payloads are deliberately tiny. A run with N parametrised
tests therefore costs ``N × (create + delete + per-test ops)`` against a
real account — affordable for Stage 3 cadence (manual or scheduled CI),
not for default CI.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._live_env import require_azure_live_connection_string
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend


_LOG = logging.getLogger(__name__)

# id(backend) -> (filesystem name, DataLakeServiceClient) so cleanup can
# tear down what factory created without threading state through the
# Backend instance.
_FILESYSTEMS: dict[int, tuple[str, object]] = {}


def _factory() -> Backend:
    if os.environ.get("RS_TEST_LIVE_HNS") != "1":
        pytest.skip("azure_live opt-in via RS_TEST_LIVE_HNS=1")
    try:
        from azure.storage.filedatalake import DataLakeServiceClient
    except ImportError:
        pytest.skip("azure-storage-file-datalake not installed")

    from remote_store.backends._azure import AzureBackend

    conn = require_azure_live_connection_string()
    fs_name = f"conformance-{uuid.uuid4().hex[:8]}"
    service = DataLakeServiceClient.from_connection_string(conn)
    try:
        service.create_file_system(fs_name)
    except Exception:
        service.close()
        raise
    backend = AzureBackend(container=fs_name, connection_string=conn)
    _FILESYSTEMS[id(backend)] = (fs_name, service)
    return backend


def _cleanup(backend: Backend) -> None:
    backend.close()
    entry = _FILESYSTEMS.pop(id(backend), None)
    if entry is None:
        return
    fs_name, service = entry
    try:
        service.delete_file_system(fs_name)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("failed to delete live HNS filesystem %s", fs_name, exc_info=True)
    finally:
        service.close()  # type: ignore[attr-defined]


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._azure import AzureBackend
    except ImportError:
        return frozenset()
    return frozenset(AzureBackend.CAPABILITIES)


register(
    BackendFixture(
        name="azure_live",
        backend="azure",
        factory=_factory,
        stage=3,
        kind="real-live",
        capabilities=_capabilities(),
        is_async=False,
        cleanup=_cleanup,
        marks=(pytest.mark.live,),
    )
)
