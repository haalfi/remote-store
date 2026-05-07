"""``azurite`` fixture: AzureBackend against the Azurite emulator.

Stage 2, real-local. Azurite is the Microsoft-published Docker emulator
for Azure Blob Storage. Each factory call creates a fresh container with
a random suffix and tears it down on cleanup.

Real ADLS Gen2 behaviour (HNS, hierarchical namespace) is not reachable
through Azurite — that path needs the Stage 3 ``azure_live`` fixture
introduced by BK-180.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_CONTAINERS: dict[int, tuple[str, object]] = {}


def _factory() -> Backend:
    if INFRA.azurite_conn_str is None:
        pytest.skip("Azure SDK not installed or Azurite not reachable on 127.0.0.1:10000")
    from azure.storage.blob import BlobServiceClient

    from remote_store.backends._azure import AzureBackend

    container = f"conformance-{uuid.uuid4().hex[:8]}"
    service = BlobServiceClient.from_connection_string(INFRA.azurite_conn_str)
    try:
        service.create_container(container)
    except Exception:
        service.close()
        raise
    backend = AzureBackend(container=container, connection_string=INFRA.azurite_conn_str)
    _CONTAINERS[id(backend)] = (container, service)
    return backend


def _cleanup(backend: Backend) -> None:
    backend.close()
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


register(
    BackendFixture(
        name="azurite",
        backend="azure",
        factory=_factory,
        stage=2,
        kind="real-local",
        capabilities=_capabilities(),
        is_async=False,
        cleanup=_cleanup,
        marks=(pytest.mark.requires_docker,),
    )
)
