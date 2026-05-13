"""AzureBackend check_health() probe-identity and error-mapping tests -- PING-007.

The healthy-path assertion (``check_health() is None``) is the universal
ABC contract covered by tests/backends/conformance/test_check_health.py.
This file pins what is Azure-specific:

- The non-HNS probe is ``container_client.get_container_properties()``;
  the HNS branch uses ``file_system_client.get_file_system_properties()``.
- ``azure.core.exceptions.ResourceNotFoundError`` maps to the standard
  ``NotFound`` (PING-009).

Migrated from tests/test_ping.py (BK-217 / BK-191 slice 2/6).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("azure.storage.blob", reason="azure-storage-blob not installed")

from remote_store._errors import NotFound  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# Tracker so an autouse fixture can close() backends made by the helper below —
# without close, AzureBackend.__del__ emits ResourceWarning at GC.
_BACKENDS: list[Backend] = []


@pytest.fixture(autouse=True)
def _close_tracked_backends() -> Iterator[None]:
    yield
    while _BACKENDS:
        backend = _BACKENDS.pop()
        with contextlib.suppress(Exception):
            backend.close()


def _azure_backend(side_effect: Any = None) -> Any:
    from azure.storage.blob import ContainerClient

    from remote_store.backends._azure import AzureBackend

    cc_mock = MagicMock(spec=ContainerClient)
    if side_effect is not None:
        cc_mock.get_container_properties.side_effect = side_effect
    else:
        cc_mock.get_container_properties.return_value = {}
    backend = AzureBackend(
        container="test",
        connection_string="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net",
    )
    backend._cc_instance = cc_mock
    backend._hns_enabled = False
    _BACKENDS.append(backend)
    return backend, cc_mock


@pytest.mark.spec("PING-007")
def test_azure_probe_is_get_container_properties() -> None:
    backend, cc_mock = _azure_backend()
    backend.check_health()
    assert cc_mock.get_container_properties.call_count == 1


@pytest.mark.spec("PING-007")
def test_azure_not_found() -> None:
    from azure.core.exceptions import ResourceNotFoundError

    backend, _ = _azure_backend(side_effect=ResourceNotFoundError("not found"))
    with pytest.raises(NotFound):
        backend.check_health()
