"""``azurite`` fixture: AzureBackend against the Azurite emulator.

Stage 2, real-local. Azurite is the Microsoft-published Docker emulator
for Azure Blob Storage. Each factory call creates a fresh container with
a random suffix and tears it down on cleanup.

Real ADLS Gen2 behaviour (HNS, hierarchical namespace) is not reachable
through Azurite — that path needs the Stage 3 ``azure_live`` fixture
introduced by BK-180.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import pytest

from infra._settings import AZURITE_HOST, AZURITE_PORT
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_LOG = logging.getLogger(__name__)
_CONTAINERS: dict[int, tuple[str, object]] = {}


def _make_factory(reject_write_under_file_ancestor: bool):
    def _factory() -> Backend:
        if INFRA.azurite_conn_str is None:
            pytest.skip(f"Azure SDK not installed or Azurite not reachable on {AZURITE_HOST}:{AZURITE_PORT}")
        from azure.storage.blob import BlobServiceClient

        from remote_store.backends._azure import AzureBackend

        container = f"conformance-{uuid.uuid4().hex[:8]}"
        service = BlobServiceClient.from_connection_string(INFRA.azurite_conn_str)
        try:
            service.create_container(container)
        except Exception:
            service.close()
            raise
        backend = AzureBackend(
            container=container,
            connection_string=INFRA.azurite_conn_str,
            reject_write_under_file_ancestor=reject_write_under_file_ancestor,
        )
        _CONTAINERS[id(backend)] = (container, service)
        return backend

    return _factory


def _cleanup(backend: Backend) -> None:
    # Guard ``backend.close()`` so a transient close failure does not
    # short-circuit the container-deletion path. Mirrors the same pattern
    # in ``azure_live._cleanup``; a leaked Azurite container is free, so
    # this is consistency with the live counterpart rather than a cost
    # concern.
    try:
        backend.close()
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("backend.close() failed during cleanup", exc_info=True)
    entry = _CONTAINERS.pop(id(backend), None)
    if entry is not None:
        container, service = entry
        try:
            service.delete_container(container)  # type: ignore[attr-defined]
        finally:
            service.close()  # type: ignore[attr-defined]


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._azure import AzureBackend
    except ImportError:
        return frozenset()
    return frozenset(AzureBackend.CAPABILITIES)


for _name in ("azurite", "azurite_strict"):
    _meta = load_fixture(_name)
    register(
        BackendFixture(
            factory=_make_factory(_meta.rejects_write_under_file_ancestor),
            capabilities=_capabilities(),
            cleanup=_cleanup,
            marks=(pytest.mark.requires_docker,),
            **_meta.to_kwargs(),
        )
    )
