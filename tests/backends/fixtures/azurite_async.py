"""Async Azurite fixtures: ``azurite_async`` + ``azurite_async_strict``.

Stage 2, real-local, async. The async siblings of the sync ``azurite`` /
``azurite_strict`` pair, registered together via a parametrised factory.

- ``azurite_async`` (BUG-217): the non-strict baseline. Gives the async Azurite
  staged-write path offline conformance coverage — notably the large
  WriteResult↔FileInfo consistency test, which before this ran on no offline
  async fixture (only the live ``azure_live_async``, skipped without
  ``RS_TEST_LIVE_HNS=1``).
- ``azurite_async_strict`` (ID-211): ``strict_only`` variant driving the
  file-ancestor gate through ``AsyncAzureBackend._maybe_check_no_file_ancestor``
  / ``_acheck_no_file_ancestor`` / the SDK ``get_blob_properties`` closure
  end-to-end against a real (emulated) Azure target — otherwise covered only by
  the stub-callable unit tests in ``tests/backends/test_flat_ns.py``.
  ``strict_only=true`` keeps it out of the default enumeration; the
  file-ancestor tests opt in via ``include_strict_only=True``.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from typing import TYPE_CHECKING

import pytest

from infra._settings import AZURITE_HOST, AZURITE_PORT
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures._state import INFRA
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_LOG = logging.getLogger(__name__)
_CONTAINERS: dict[int, tuple[str, object]] = {}


def _make_factory(reject_write_under_file_ancestor: bool):
    def _factory() -> AsyncBackend:
        if INFRA.azurite_conn_str is None:
            pytest.skip(f"Azure SDK not installed or Azurite not reachable on {AZURITE_HOST}:{AZURITE_PORT}")
        from azure.storage.blob import BlobServiceClient

        from remote_store.aio.backends._azure import AsyncAzureBackend

        container = f"conformance-{uuid.uuid4().hex[:8]}"
        # Container provisioning uses the sync SDK because it's a one-shot
        # setup/teardown step; the backend under test exercises the async SDK.
        service = BlobServiceClient.from_connection_string(INFRA.azurite_conn_str)
        try:
            service.create_container(container)
        except Exception:
            service.close()
            raise
        # Construct the backend inside a guard so a failure during
        # AsyncAzureBackend __init__ (validation error, import-path drift)
        # doesn't leak the just-created container — _CONTAINERS registration
        # only happens on success, so without the guard the teardown path
        # never reaches it.
        try:
            backend = AsyncAzureBackend(
                container=container,
                connection_string=INFRA.azurite_conn_str,
                reject_write_under_file_ancestor=reject_write_under_file_ancestor,
            )
        except Exception:
            with contextlib.suppress(Exception):
                service.delete_container(container)
            service.close()
            raise
        _CONTAINERS[id(backend)] = (container, service)
        return backend

    return _factory


async def _aclose(backend: AsyncBackend) -> None:
    """Drain the AsyncAzureBackend pool before the next test."""
    try:
        await backend.aclose()
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("backend.aclose() failed during cleanup", exc_info=True)


def _cleanup(backend: AsyncBackend) -> None:
    """Delete the per-test container after ``aclose`` has drained the pool."""
    entry = _CONTAINERS.pop(id(backend), None)
    if entry is not None:
        container, service = entry
        try:
            service.delete_container(container)  # type: ignore[attr-defined]
        finally:
            service.close()  # type: ignore[attr-defined]


def _capabilities() -> frozenset:
    try:
        from remote_store.aio.backends._azure import AsyncAzureBackend
    except ImportError:
        return frozenset()
    return frozenset(AsyncAzureBackend.CAPABILITIES)


for _name in ("azurite_async", "azurite_async_strict"):
    _meta = load_fixture(_name)
    register(
        BackendFixture(
            factory=_make_factory(_meta.rejects_write_under_file_ancestor),
            capabilities=_capabilities(),
            aclose=_aclose,
            cleanup=_cleanup,
            marks=(pytest.mark.requires_docker,),
            **_meta.to_kwargs(),
        )
    )
