"""Live ADLS Gen2 (HNS) integration tests for ``AzureBackend``.

Covers HNS semantics that mock-only suites cannot reproduce.

**Directory-path guards.** ``TestAzureWriteOnHnsDirectory`` in
:mod:`tests.backends.test_azure` fabricates ``hdi_isfolder=true``
metadata on a mocked :class:`~azure.storage.blob.BlobProperties` and
relies on the same probe the production code uses, so it verifies
code logic but not real-account behaviour.
``TestAzureLiveHnsDirectoryGuard`` here asserts the sync API raises
:class:`~remote_store._errors.InvalidPath` when the target is an HNS
directory blob created via the real
:class:`~azure.storage.filedatalake.DataLakeServiceClient`.

**`write_atomic` metadata-survives-rename.**
``test_write_atomic_hns_metadata_preserved`` in
:mod:`tests.aio.test_async_azure` only verifies that ``metadata=`` is
forwarded to ``upload_data`` on the temp file and that
``WriteResult.metadata`` echoes the caller's mapping by construction
(WR-012). It cannot verify that ADLS Gen2's ``rename_file`` preserves
user-defined metadata on the renamed final file, a filesystem-level
semantics concern only the real service can answer.
``TestAzureLiveHnsMetadataSurvivesRename`` writes a small payload through
``write_atomic`` with metadata and asserts the round-trip via
``get_file_info`` after the temp-then-rename has committed.

Spec: BE-021 (directory-path guard) for BE-008 (``write``),
BE-010 (``write_atomic``), SAW-001 (``open_atomic``);
WR-013 (user-metadata round-trip).

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
real account?" Test bodies stay deterministic, payloads stay small, and
one HNS directory is provisioned per session and shared across the
parametrized cases. Fixture teardown deletes the per-session prefix on
a best-effort basis so a teardown race does not turn a green test red.
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
from remote_store._models import WriteResult  # noqa: E402
from remote_store.backends._azure import AzureBackend  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


_LOG = logging.getLogger(__name__)

# Connection-string fragments that unambiguously indicate Azurite (the
# local emulator). Azurite does not emulate Hierarchical Namespace, so a
# connection string pointing at it cannot validate the HNS directory-path
# guards. See docs-src/guides/backends/azure-hns-setup.md.
#
# Both forms are caught:
#  - The shorthand ``UseDevelopmentStorage=true`` token.
#  - The explicit-endpoint form (used by the repo's own
#    ``_AZURITE_CONN_STR`` in ``tests/conftest.py``), which omits the
#    shorthand but always carries ``AccountName=devstoreaccount1`` —
#    Azurite's well-known emulator account, globally reserved and
#    unclaimable on real Azure.
#
# A real Azure account routed through a localhost tunnel or service-mesh
# sidecar may legitimately contain ``127.0.0.1`` or ``localhost`` in the
# BlobEndpoint, so those tokens are NOT used as Azurite signatures.
_AZURITE_FRAGMENTS = ("UseDevelopmentStorage=true", "AccountName=devstoreaccount1")


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

    Module-scoped because creating an HNS directory is a real round
    trip against Azure. Tests share the fixture by either targeting
    ``dirpath`` directly (directory-path guards) or writing a fresh
    sibling file under the session prefix (rename / metadata semantics);
    each rename-path test uses a unique uuid-suffixed name so concurrent
    or repeated runs cannot collide. Teardown deletes the entire prefix
    recursively, so any data that lands during a regression is also
    cleaned up.
    """
    conn, fs_name = _require_live_env()

    prefix = f"live-hns/{uuid.uuid4().hex[:8]}"
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


# 1 KiB cap keeps the live-cost footprint small. Tests in this module
# exercise path-shape and metadata semantics; payload content is
# irrelevant to either contract.
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


# ---------------------------------------------------------------------------
# WR-013 — user metadata survives the HNS atomic-rename commit
# ---------------------------------------------------------------------------


class TestAzureLiveHnsMetadataSurvivesRename:
    """``write_atomic`` user metadata must survive ADLS Gen2's atomic rename.

    Companion to ``test_write_atomic_hns_metadata_preserved`` in
    :mod:`tests.aio.test_async_azure`, which mocks ``upload_data`` and
    asserts the ``metadata=`` kwarg reaches it on the temp file. The
    mocks cannot answer the harder question: *does the subsequent
    ``rename_file`` preserve that metadata on the renamed final file?*
    That is a service-side semantics property of ADLS Gen2 and only a
    real account can confirm it.
    """

    @pytest.mark.spec("WR-012", "WR-013", "BE-010")
    def test_write_atomic_metadata_survives_rename(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        # Write a sibling file under the session prefix (alongside the
        # directory blob the guard tests target). A unique suffix keeps
        # repeated runs from colliding even though the prefix is shared.
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/meta-{uuid.uuid4().hex[:8]}.txt"
        metadata = {"env": "prod", "owner": "team-a"}

        result = backend.write_atomic(path, _PAYLOAD, metadata=metadata)

        # WR-012: WriteResult.metadata must echo the caller's mapping exactly —
        # the backend must not wait for a round-trip to populate this field.
        assert result.metadata == metadata
        # WR-001a: size and source are always populated on the HNS write_atomic path.
        assert result.size == len(_PAYLOAD)
        assert result.source == "native"

        info = backend.get_file_info(path)
        assert info.metadata is not None, "expected metadata round-trip via get_file_info"
        # Compare key-by-key rather than equality: ADLS Gen2 may surface
        # internal markers (e.g. hdi_isfolder) alongside user metadata,
        # and the production code is allowed to strip them. The contract
        # is that user-supplied keys round-trip with their values.
        assert info.metadata.get("env") == "prod"
        assert info.metadata.get("owner") == "team-a"


# ---------------------------------------------------------------------------
# WR-001a / WR-004 — WriteResult native fields on real HNS account
# ---------------------------------------------------------------------------


class TestAzureLiveHnsWriteResult:
    """WriteResult from write_atomic on a real HNS account must be fully native-sourced.

    The HNS write_atomic path (temp upload + rename_file) populates etag and
    last_modified from a post-rename ``get_file_properties()`` call, not from the
    upload response. Mock-only suites cannot confirm that this secondary read succeeds
    and returns a usable, normalised ETag.

    The etag cross-check (``WriteResult.etag`` vs ``FileInfo.etag``) is the uniquely
    live assertion: the backend reads etag via two distinct SDK paths (post-rename
    ``get_file_properties`` vs ``get_blob_properties`` inside ``get_file_info``), and
    normalisation inconsistency between them only surfaces against a real account.

    Spec: WR-001a (WriteResult native fields), WR-004 (source matches capability),
    BE-010 (write_atomic), AZ-034 (ETag normalisation).
    """

    @pytest.mark.spec("WR-001a", "WR-004", "BE-010", "AZ-034")
    def test_write_atomic_hns_write_result_fully_native(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/wr-native-{uuid.uuid4().hex[:8]}.txt"

        result = backend.write_atomic(path, _PAYLOAD)

        assert isinstance(result, WriteResult)
        # WR-004 / WR-001a: HNS backend declares WRITE_RESULT_NATIVE; source must be "native".
        assert result.source == "native"
        # WR-001a: size must equal the committed byte count.
        assert result.size == len(_PAYLOAD)
        # WR-001a / AZ-034: etag must be non-empty, quote-stripped, and lowercased.
        # On HNS this comes from post-rename get_file_properties — only a real account
        # confirms that call succeeds and the ETag is in a usable form.
        assert result.etag is not None, (
            "HNS write_atomic must populate WriteResult.etag from post-rename get_file_properties"
        )
        assert result.etag != ""
        assert '"' not in result.etag, f"etag must be quote-stripped; got {result.etag!r}"
        assert result.etag == result.etag.lower(), f"etag must be lowercased; got {result.etag!r}"
        # WR-001a: last_modified from the same post-rename read must be timezone-aware.
        assert result.last_modified is not None, (
            "HNS write_atomic must populate WriteResult.last_modified from post-rename get_file_properties"
        )
        assert result.last_modified.tzinfo is not None, "last_modified must be timezone-aware"
        # AZ-034 consistency: WriteResult.etag and FileInfo.etag must agree.
        # A normalisation bug that affects one SDK read path but not the other only
        # surfaces here.
        fi = backend.get_file_info(path)
        assert fi.etag is not None
        assert fi.etag == result.etag, (
            f"WriteResult.etag {result.etag!r} != FileInfo.etag {fi.etag!r}: "
            "normalisation inconsistent between post-rename get_file_properties and get_file_info"
        )
