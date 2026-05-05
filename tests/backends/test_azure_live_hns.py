"""Live ADLS Gen2 (HNS) integration tests for ``AzureBackend`` directory-path guards.

The mock-only suite in :mod:`tests.backends.test_azure` (``TestAzureWriteOnHnsDirectory``)
asserts that ``write`` / ``write_atomic`` / ``open_atomic`` raise
:class:`~remote_store._errors.InvalidPath` when the target path is an HNS
directory blob. Those tests fabricate ``hdi_isfolder=true`` metadata on a
mocked :class:`~azure.storage.blob.BlobProperties` and rely on the same
probe the production code uses, so they verify code logic but not the
real-account behaviour. This module fills that gap by running against a
real Azure Data Lake Storage Gen2 account: the fixture creates a real HNS
directory via :class:`~azure.storage.filedatalake.DataLakeServiceClient`,
and each test asserts the public sync API raises ``InvalidPath`` when
targeting that directory path.

Spec: BE-021 (directory-path guard) for BE-008 (``write``),
BE-010 (``write_atomic``), SAW-001 (``open_atomic``).

Gating
------

Three layers, all required:

1. ``pytest.mark.live`` at module level. Default ``addopts`` is
   ``-m 'not live'``, so plain ``hatch run test`` skips the file entirely.
2. ``RS_TEST_LIVE_HNS=1`` env var (matches the existing async live HNS gate
   at :class:`tests.aio.test_async_azure_live.TestAsyncAzureLiveHNS`).
3. ``AZURE_STORAGE_CONNECTION_STRING`` and ``RS_TEST_LIVE_HNS_CONTAINER``
   pointing at a *real* ADLS Gen2 account. If layer 2 is enabled but
   either of these is missing or points at Azurite, the fixture raises
   rather than skipping silently — a silent skip here would mean
   "I thought I tested it" but didn't.

Cost discipline
---------------

The whole point of this file is "is the precondition observed against a
real account?" Three deterministic test cases, 1 KiB payloads, one HNS
directory per session shared across the three tests. Fixture teardown
deletes the per-session prefix on a best-effort basis so a teardown race
does not turn a green test red.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.storage.filedatalake import DataLakeServiceClient  # noqa: E402

from remote_store._errors import InvalidPath  # noqa: E402
from remote_store.backends._azure import AzureBackend  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


_LOG = logging.getLogger(__name__)

# Connection-string fragment that unambiguously indicates Azurite (the
# local emulator). Azurite does not emulate Hierarchical Namespace, so a
# connection string pointing at it cannot validate the HNS directory-path
# guards. See docs-src/guides/backends/azure-hns-setup.md.
#
# Heuristic intentionally narrow: a real Azure account routed through a
# localhost tunnel or service-mesh sidecar may legitimately contain
# ``127.0.0.1`` or ``localhost`` in the BlobEndpoint, so those tokens are
# not used as Azurite signatures. Connection strings that target Azurite
# via explicit endpoint URLs without this shortcut will fail downstream
# at ``create_directory`` (no DFS endpoint), which is informative enough.
_AZURITE_FRAGMENTS = ("UseDevelopmentStorage=true",)


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RS_TEST_LIVE_HNS") != "1",
        reason="live HNS suite is opt-in via RS_TEST_LIVE_HNS=1",
    ),
]


def _require_live_env() -> tuple[str, str]:
    """Return (connection_string, filesystem) or fail loud.

    The module-level skipif handles the opt-out path. Once the user opts
    in, missing or Azurite-pointing credentials are a configuration bug,
    not a reason to skip — silent skips defeat the whole point of running
    a live test.
    """
    # Backstop ``.env`` load. The primary path is ``pytest_configure`` in
    # ``tests/conftest.py``, which loads ``.env`` before collection when
    # the mark expression includes ``live`` — that is the path the doc
    # contract relies on. This call covers the niche case where someone
    # runs the file with ``RS_TEST_LIVE_HNS=1`` exported in the shell but
    # without ``-m live`` (so ``pytest_configure``'s heuristic skips the
    # load), letting ``.env`` still supply the connection string and
    # container. override=False keeps shell/CI values authoritative.
    from dotenv import load_dotenv  # noqa: PLC0415 -- intentional lazy import

    load_dotenv(override=False)

    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    fs = os.environ.get("RS_TEST_LIVE_HNS_CONTAINER")
    if not conn:
        pytest.fail("RS_TEST_LIVE_HNS=1 set but AZURE_STORAGE_CONNECTION_STRING is empty")
    if not fs:
        pytest.fail("RS_TEST_LIVE_HNS=1 set but RS_TEST_LIVE_HNS_CONTAINER is empty")
    if any(frag in conn for frag in _AZURITE_FRAGMENTS):
        pytest.fail(
            "RS_TEST_LIVE_HNS=1 set but AZURE_STORAGE_CONNECTION_STRING points at Azurite; "
            "the live HNS suite needs a real ADLS Gen2 account"
        )
    return conn, fs


@pytest.fixture(scope="module")
def live_hns_backend() -> Iterator[tuple[AzureBackend, str]]:
    """Provision an ``AzureBackend`` against a real ADLS Gen2 account with one HNS directory.

    Yields ``(backend, dirpath)`` where ``dirpath`` is the in-filesystem
    path of an HNS directory created via
    :meth:`~azure.storage.filedatalake.FileSystemClient.create_directory`.
    The directory and its contents are best-effort deleted on teardown.

    Module-scoped because creating an HNS directory is a real round trip
    against Azure; the three tests that share it cannot interfere with
    each other (they only read directory metadata via ``get_blob_properties``
    and never mutate the directory blob).
    """
    conn, fs_name = _require_live_env()

    prefix = f"bug191/{uuid.uuid4().hex[:8]}"
    dirpath = f"{prefix}/dirblob"

    # Each acquired resource is paired with its teardown via a nested
    # try/finally so that failures during setup (after one resource
    # succeeded but before the next) still trigger cleanup of what was
    # already provisioned.
    service = DataLakeServiceClient.from_connection_string(conn)
    try:
        fs_client = service.get_file_system_client(fs_name)
        fs_client.get_directory_client(dirpath).create_directory()
        try:
            backend = AzureBackend(container=fs_name, connection_string=conn)
            try:
                yield backend, dirpath
            finally:
                backend.close()
        finally:
            try:
                fs_client.get_directory_client(prefix).delete_directory()
            except Exception:  # noqa: BLE001 -- teardown is best-effort
                _LOG.warning("failed to delete live HNS test prefix %s", prefix, exc_info=True)
    finally:
        service.close()


# ---------------------------------------------------------------------------
# BE-021 — directory-path guards on a real HNS account
# ---------------------------------------------------------------------------


# 1 KiB cap (BUG-191 cost discipline). The guards fire on path shape, not
# content; a single KiB is sufficient to demonstrate the exception path.
_PAYLOAD = b"x" * 1024


def _do_write(backend: AzureBackend, path: str) -> None:
    backend.write(path, _PAYLOAD)


def _do_write_atomic(backend: AzureBackend, path: str) -> None:
    backend.write_atomic(path, _PAYLOAD)


def _do_open_atomic(backend: AzureBackend, path: str) -> None:
    with backend.open_atomic(path):
        pass


class TestAzureLiveHnsDirectoryGuard:
    """``write`` / ``write_atomic`` / ``open_atomic`` must raise ``InvalidPath`` on a real HNS directory.

    Companion to ``TestAzureWriteOnHnsDirectory`` in ``test_azure.py``,
    which mocks ``hdi_isfolder=true`` on a fabricated ``BlobProperties``.
    These tests confirm the same precondition fires when the marker is
    set by the real ADLS Gen2 service.
    """

    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(_do_write, id="write", marks=pytest.mark.spec("BE-008")),
            pytest.param(_do_write_atomic, id="write_atomic", marks=pytest.mark.spec("BE-010")),
            pytest.param(_do_open_atomic, id="open_atomic", marks=pytest.mark.spec("SAW-001")),
        ],
    )
    def test_directory_path_raises_invalid_path(
        self,
        live_hns_backend: tuple[AzureBackend, str],
        operation: Callable[[AzureBackend, str], None],
    ) -> None:
        backend, dirpath = live_hns_backend
        with pytest.raises(InvalidPath, match="exists as a directory"):
            operation(backend, dirpath)
