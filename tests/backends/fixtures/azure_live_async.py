"""``azure_live_async`` fixture: AsyncAzureBackend against a real ADLS Gen2 account.

Stage 3, real-live, async. Mirrors ``azure_live`` for the async backend
surface. Each factory call provisions a fresh HNS filesystem
(``conformance-async-<uuid>``) and tears it down on cleanup.

The HNS filesystem is created via the *sync* DataLake SDK at fixture
setup. The async SDK's filesystem-management API is identical for
correctness but adds an event-loop dependency to setup paths that
would otherwise run synchronously; the resource being managed (a real
ADLS Gen2 filesystem) is identical regardless of which SDK created it.
The async backend instance under test exercises the async SDK code path
during the test body, which is the actual behaviour conformance is
verifying.

Async cleanup channel
---------------------

This is the first registry fixture that owns a real network pool needing
``await backend.aclose()``. It uses the ``aclose`` field on
``BackendFixture`` (TEST-004 extension) so the conformance
``async_backend`` indirect fixture awaits the close before the next
test starts. The ``cleanup`` field handles the sync filesystem deletion
that does not need the event loop.

Gating, isolation, and cost
---------------------------

Identical to ``azure_live`` (sync): two-layer gate (``--stage=3`` plus
``RS_TEST_LIVE_HNS=1``), per-call fresh HNS filesystem, ``pytest.mark.live``
default-deselect. ``pytest.mark.vcr`` is added dynamically by the root
``conftest.pytest_collection_modifyitems`` hook when ``--record`` is
active — not as a static mark — for the same reason described in
``azure_live``.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._live_env import require_azure_live_connection_string
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store.aio import AsyncBackend

_meta = load_fixture("azure_live_async")


_LOG = logging.getLogger(__name__)

# id(backend) -> (filesystem name, sync DataLakeServiceClient).
# The service client created at setup is reused at cleanup to delete
# the filesystem; storing it here avoids reconstructing it from the
# connection string and keeps teardown quick.
_FILESYSTEMS: dict[int, tuple[str, object]] = {}


def _factory() -> AsyncBackend:
    if os.environ.get("RS_TEST_LIVE_HNS") != "1":
        pytest.skip("azure_live_async opt-in via RS_TEST_LIVE_HNS=1")
    try:
        from azure.storage.filedatalake import DataLakeServiceClient
    except ImportError:
        pytest.skip("azure-storage-file-datalake not installed")

    from remote_store.aio.backends._azure import AsyncAzureBackend

    conn = require_azure_live_connection_string()
    fs_name = f"conformance-async-{uuid.uuid4().hex[:8]}"
    service = DataLakeServiceClient.from_connection_string(conn)
    try:
        service.create_file_system(fs_name)
    except Exception:
        service.close()
        raise
    client_options: dict[str, object] = {}
    if os.environ.get("_RS_CASSETTE_RECORDING") == "1":
        # vcrpy 8.1.1's aiohttp stub drops streaming response bodies on record.
        # Inject AsyncioRequestsTransport so the cassette captures real bodies.
        try:
            from azure.core.pipeline.transport import AsyncioRequestsTransport  # noqa: PLC0415

            client_options = {"transport": AsyncioRequestsTransport()}
        except ImportError:
            pass
    backend = AsyncAzureBackend(container=fs_name, connection_string=conn, client_options=client_options or None)
    _FILESYSTEMS[id(backend)] = (fs_name, service)
    return backend


async def _aclose(backend: AsyncBackend) -> None:
    """Await the async backend's network-pool teardown.

    Runs before ``_cleanup`` so the connection pool drains while the
    fixture metadata is still in scope; the filesystem itself is then
    deleted via the sync SDK in ``_cleanup``.
    """
    await backend.aclose()


def _cleanup(backend: AsyncBackend) -> None:
    """Delete the filesystem created at setup. Best-effort.

    Runs after ``_aclose``. Uses the cached sync ``DataLakeServiceClient``
    rather than spinning up a new one because the filesystem name and
    service handle were both captured at setup.
    """
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
        from remote_store.aio.backends._azure import AsyncAzureBackend
    except ImportError:
        return frozenset()
    return frozenset(AsyncAzureBackend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        aclose=_aclose,
        marks=(pytest.mark.live,),
        **_meta.to_kwargs(),
    )
)
