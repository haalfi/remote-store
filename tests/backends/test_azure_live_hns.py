"""Live ADLS Gen2 (HNS) integration tests for ``AzureBackend``.

Covers HNS semantics that mock-only suites cannot reproduce.

**Directory-path guards.** ``TestAzureWriteOnHnsDirectory`` in
``tests.backends.test_azure`` fabricates ``hdi_isfolder=true``
metadata on a mocked ``BlobProperties`` and
relies on the same probe the production code uses, so it verifies
code logic but not real-account behaviour.
``TestAzureLiveHnsDirectoryGuard`` here asserts the sync API raises
``InvalidPath`` when the target is an HNS
directory blob created via the real
``DataLakeServiceClient``.

**`write_atomic` metadata-survives-rename.**
``test_write_atomic_hns_metadata_preserved`` in
``tests.aio.test_async_azure`` only verifies that ``metadata=`` is
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
2. ``RS_TEST_LIVE_HNS=1`` env var (matches the async live HNS gate in
   ``tests.aio.test_async_azure_live_hns``).
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

from remote_store._errors import AlreadyExists, InvalidPath, NotFound  # noqa: E402
from remote_store._models import FileInfo  # noqa: E402
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


# Gating — three layers, all required:
#   1. ``pytest.mark.live`` below. Default addopts is ``-m 'not live'``,
#      so plain ``hatch run test`` skips the file entirely.
#   2. ``RS_TEST_LIVE_HNS=1`` env var.
#   3. ``AZURE_STORAGE_CONNECTION_STRING`` + ``RS_TEST_LIVE_HNS_CONTAINER``
#      pointing at a real ADLS Gen2 account. Azurite-shaped values raise
#      rather than skip — a silent skip defeats the point of a live test.
#
# Cost discipline: test bodies stay deterministic, payloads stay small,
# and one HNS directory is provisioned per session and shared across
# parametrized cases. Teardown deletes the prefix on a best-effort basis
# so a teardown race does not turn a green test red.
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
def live_hns_env() -> tuple[str, str]:
    """Module-scoped accessor for the validated ``(connection_string, filesystem)``.

    Centralises the env-var lookup so individual tests do not re-read
    ``os.environ`` directly — direct access bypasses ``_require_live_env``'s
    fail-loud handling and would raise ``KeyError`` on misconfiguration
    instead of the descriptive ``pytest.fail`` message.
    """
    return _require_live_env()


@pytest.fixture(scope="module")
def live_hns_backend() -> Iterator[tuple[AzureBackend, str]]:
    """Provision an ``AzureBackend`` against a real ADLS Gen2 account with one HNS directory.

    Yields ``(backend, dirpath)`` where ``dirpath`` is the in-filesystem
    path of an HNS directory created via
    ``create_directory()``.
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
    ``tests.aio.test_async_azure``, which mocks ``upload_data`` and
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

        # WR-004 / WR-001a: HNS backend declares WRITE_RESULT_NATIVE; source must be "native".
        assert result.source == "native"
        # WR-001a: size must equal the committed byte count.
        assert result.size == len(_PAYLOAD)
        # WR-001a / AZ-034: etag must be non-empty, quote-stripped, and lowercased.
        # On HNS this comes from post-rename get_file_properties — only a real account
        # confirms that call succeeds and the ETag is in a usable form.
        # BUG-173 allows etag=None when get_file_properties() fails post-rename (the
        # rename committed; the read is best-effort). That path is a transient fallback;
        # this test targets the normal path where the read succeeds.
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


# ---------------------------------------------------------------------------
# BE-010 — content round-trip and overwrite on the HNS write_atomic path
# ---------------------------------------------------------------------------


class TestAzureLiveHnsContentRoundTrip:
    """Bytes written via write_atomic must survive the HNS temp-upload + rename_file commit.

    The content round-trip (write then read_bytes) confirms the rename committed the
    full payload, not a truncated or empty blob. The overwrite path exercises the
    existing-file case through the same DFS rename. The overwrite=False guard confirms
    AlreadyExists is raised before the temp upload starts.

    Spec: BE-010 (write_atomic).
    """

    @pytest.mark.spec("BE-010", "WR-001a")
    def test_write_atomic_content_survives_hns_rename(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/roundtrip-{uuid.uuid4().hex[:8]}.txt"
        payload = b"roundtrip-" + uuid.uuid4().bytes

        result = backend.write_atomic(path, payload)

        assert result.size == len(payload)
        assert backend.read_bytes(path) == payload

    @pytest.mark.spec("BE-010")
    def test_write_atomic_overwrite_replaces_content(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/overwrite-{uuid.uuid4().hex[:8]}.txt"
        original = b"original-content"
        replacement = b"replaced-content"

        backend.write_atomic(path, original)
        backend.write_atomic(path, replacement, overwrite=True)

        assert backend.read_bytes(path) == replacement

    @pytest.mark.spec("BE-010")
    def test_write_atomic_overwrite_false_raises_already_exists(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/noover-{uuid.uuid4().hex[:8]}.txt"

        backend.write_atomic(path, _PAYLOAD)
        with pytest.raises(AlreadyExists, match="already exists"):
            backend.write_atomic(path, _PAYLOAD, overwrite=False)


# ---------------------------------------------------------------------------
# BE-018 — move uses rename_file on HNS accounts
# ---------------------------------------------------------------------------


class TestAzureLiveHnsMove:
    """``move`` must use ``rename_file`` on an HNS account for atomic relocation.

    The non-HNS path uses server-side copy + delete, which is not atomic. On HNS
    accounts the backend calls ``rename_file`` instead. Mock-only suites stub the
    DFS client; only a real account confirms the rename path executes correctly
    end-to-end.

    Spec: BE-018 (move).
    """

    @pytest.mark.spec("BE-018")
    def test_move_hns_src_content_reaches_dst(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/move-src-{uid}.txt"
        dst = f"{prefix}/move-dst-{uid}.txt"
        payload = b"move-content-" + uuid.uuid4().bytes

        backend.write_atomic(src, payload)
        backend.move(src, dst)

        assert backend.read_bytes(dst) == payload
        with pytest.raises(NotFound, match="(?i)not found"):
            backend.read_bytes(src)

    @pytest.mark.spec("BE-018")
    def test_move_existing_dst_overwrite_false_raises_already_exists(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        """``move`` must guard against silent overwrite when ``overwrite=False``.

        On HNS the underlying ``rename_file`` could silently clobber the destination;
        the production code interposes a ``get_blob_properties`` probe to raise
        ``AlreadyExists`` first. Only a real account confirms the probe + raise
        sequence on actual HNS resources.
        """
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/move-src-exists-{uid}.txt"
        dst = f"{prefix}/move-dst-exists-{uid}.txt"

        backend.write_atomic(src, b"src")
        backend.write_atomic(dst, b"dst-original")

        with pytest.raises(AlreadyExists, match="already exists"):
            backend.move(src, dst)
        # Both blobs must remain unchanged after the failed move.
        assert backend.read_bytes(dst) == b"dst-original"
        assert backend.read_bytes(src) == b"src"


# ---------------------------------------------------------------------------
# BE-016 — get_file_info on an HNS directory blob
# ---------------------------------------------------------------------------


class TestAzureLiveHnsGetFileInfoOnDirectory:
    """``get_file_info`` on an HNS directory blob must raise ``NotFound``.

    ADLS Gen2 marks directory blobs with ``hdi_isfolder=true`` metadata. The
    production code detects this marker and raises ``NotFound`` so callers cannot
    treat a directory as a file. Mock-only suites fabricate ``hdi_isfolder`` on a
    ``BlobProperties`` stub; only a real account confirms the marker is present on
    a directory created via ``DataLakeServiceClient``.

    Note: BE-016 specifies ``InvalidPath`` for directory paths, but the current
    implementation raises ``NotFound``. This test documents the actual live
    behaviour; the deviation is tracked as **BUG-195** in ``sdd/BACKLOG.md`` and
    must be flipped to ``InvalidPath`` when that fix lands.

    Spec: BE-016 (get_file_info).
    """

    # BUG-195: marks the spec target, not the current behaviour. BE-016 specifies
    # InvalidPath but the runtime raises NotFound; this test documents the deviation
    # and must be flipped to pytest.raises(InvalidPath) when BUG-195 is fixed.
    @pytest.mark.spec("BE-016")
    def test_get_file_info_on_hns_directory_raises_not_found(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        with pytest.raises(NotFound, match="(?i)not found"):
            backend.get_file_info(dirpath)


# ---------------------------------------------------------------------------
# SAW-001 — open_atomic success path on a real HNS account
# ---------------------------------------------------------------------------


class TestAzureLiveHnsOpenAtomicSuccess:
    """``open_atomic`` must commit written content atomically on an HNS account.

    The HNS path uploads to a temp blob and renames atomically to the final path.
    ``TestAzureLiveHnsDirectoryGuard`` covers the error path (directory target).
    This class covers the success path: content written to the context manager
    must be readable at the final path after the context exits.

    Spec: SAW-001 (open_atomic).
    """

    @pytest.mark.spec("SAW-001")
    def test_open_atomic_content_committed_on_hns(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/open-atomic-{uuid.uuid4().hex[:8]}.txt"
        payload = b"open-atomic-content-" + uuid.uuid4().bytes

        with backend.open_atomic(path) as fh:
            fh.write(payload)

        assert backend.read_bytes(path) == payload


# ---------------------------------------------------------------------------
# BE-013 / BE-014 / BE-018 — NotFound on real HNS account (read / delete / move)
# ---------------------------------------------------------------------------


def _read_bytes_missing(backend: AzureBackend, prefix: str) -> None:
    backend.read_bytes(f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt")


def _get_file_info_missing(backend: AzureBackend, prefix: str) -> None:
    backend.get_file_info(f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt")


def _delete_missing(backend: AzureBackend, prefix: str) -> None:
    backend.delete(f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt")


def _move_missing_src(backend: AzureBackend, prefix: str) -> None:
    uid = uuid.uuid4().hex[:8]
    backend.move(f"{prefix}/missing-src-{uid}.txt", f"{prefix}/missing-dst-{uid}.txt")


class TestAzureLiveHnsNotFound:
    """Operations on missing HNS paths must raise ``NotFound`` on a real account.

    The most common error path in real usage. Mock suites stub
    ``ResourceNotFoundError`` directly; only a real account confirms the SDK
    actually raises it for the shapes the production code probes (blob client
    vs file client paths can differ between flat-blob and HNS).

    Spec: BE-013 (read), BE-014 (delete), BE-016 (get_file_info), BE-018 (move).
    """

    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(_read_bytes_missing, id="read_bytes", marks=pytest.mark.spec("BE-013")),
            pytest.param(_get_file_info_missing, id="get_file_info", marks=pytest.mark.spec("BE-016")),
            pytest.param(_delete_missing, id="delete", marks=pytest.mark.spec("BE-014")),
            pytest.param(_move_missing_src, id="move", marks=pytest.mark.spec("BE-018")),
        ],
    )
    def test_operation_on_missing_path_raises_not_found(
        self,
        live_hns_backend: tuple[AzureBackend, str],
        operation: Callable[[AzureBackend, str], None],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        with pytest.raises(NotFound, match="(?i)not found"):
            operation(backend, prefix)

    @pytest.mark.spec("BE-014")
    def test_delete_missing_with_missing_ok_is_silent(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        """``missing_ok=True`` is the contract for idempotent delete; live confirms."""
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        missing = f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt"
        # Returning normally is the assertion: missing_ok=True must not raise.
        result = backend.delete(missing, missing_ok=True)
        assert result is None


# ---------------------------------------------------------------------------
# BE-015 — exists() on a real HNS account
# ---------------------------------------------------------------------------


class TestAzureLiveHnsExists:
    """``exists`` must return True for present files and HNS directories, False for missing.

    Most-hit predicate in real usage. The HNS path probes the blob client first;
    on miss it falls back to a DataLake directory probe (`_ensure_hns()` branch).
    Mock suites stub each branch in isolation; only a real account confirms the
    fallback chain works end-to-end on actual HNS resources.

    Spec: BE-015 (exists).
    """

    @pytest.mark.spec("BE-015")
    def test_exists_returns_true_for_present_file(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/exists-{uuid.uuid4().hex[:8]}.txt"
        backend.write_atomic(path, _PAYLOAD)
        assert backend.exists(path) is True

    @pytest.mark.spec("BE-015")
    def test_exists_returns_false_for_missing_path(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        missing = f"{prefix}/does-not-exist-{uuid.uuid4().hex[:8]}.txt"
        assert backend.exists(missing) is False

    @pytest.mark.spec("BE-015")
    def test_exists_returns_true_for_hns_directory(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        """The DataLake directory-probe fallback fires only on a real HNS account."""
        backend, dirpath = live_hns_backend
        assert backend.exists(dirpath) is True


# ---------------------------------------------------------------------------
# BE-022 — list_files on an HNS prefix (recursive vs non-recursive)
# ---------------------------------------------------------------------------


class TestAzureLiveHnsListFiles:
    """``list_files`` traverses HNS prefixes via ``DataLakeFileSystemClient.get_paths``.

    Non-recursive must yield only immediate files (filtering out the ``is_directory``
    entries); recursive must yield files in nested subdirectories. The HNS path
    differs structurally from the flat-blob ``walk_blobs`` / ``list_blobs`` path —
    only a real ADLS Gen2 account exercises ``get_paths`` with real ``is_directory``
    markers.

    Spec: BE-022 (list_files).
    """

    @pytest.mark.spec("BE-022")
    def test_list_files_non_recursive_yields_immediate_files_only(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        sub = f"{prefix}/listroot-{uuid.uuid4().hex[:8]}"
        backend.write_atomic(f"{sub}/a.txt", b"a")
        backend.write_atomic(f"{sub}/b.txt", b"b")
        backend.write_atomic(f"{sub}/nested/c.txt", b"c")

        files = sorted(str(fi.path) for fi in backend.list_files(sub))
        assert files == [f"{sub}/a.txt", f"{sub}/b.txt"]

    @pytest.mark.spec("BE-022")
    def test_list_files_recursive_yields_nested_files(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        sub = f"{prefix}/listrec-{uuid.uuid4().hex[:8]}"
        backend.write_atomic(f"{sub}/a.txt", b"a")
        backend.write_atomic(f"{sub}/b.txt", b"b")
        backend.write_atomic(f"{sub}/nested/c.txt", b"c")

        files = sorted(str(fi.path) for fi in backend.list_files(sub, recursive=True))
        assert files == [f"{sub}/a.txt", f"{sub}/b.txt", f"{sub}/nested/c.txt"]


# ---------------------------------------------------------------------------
# BE-024 — iter_children on an HNS prefix yields both files and folders
# ---------------------------------------------------------------------------


class TestAzureLiveHnsIterChildren:
    """``iter_children`` must yield ``FileInfo`` for files and ``FolderEntry`` for subdirs.

    On HNS, ``get_paths(recursive=False)`` returns both regular files and directory
    blobs (marked ``is_directory=True``); the production code routes them to the
    correct dataclass. Mock suites can fabricate the marker; only a real account
    confirms the marker shape on a directory created via ``DataLakeServiceClient``.

    Spec: BE-024 (iter_children).
    """

    @pytest.mark.spec("BE-024")
    def test_iter_children_yields_files_and_folders(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        sub = f"{prefix}/iterchild-{uuid.uuid4().hex[:8]}"
        backend.write_atomic(f"{sub}/a.txt", b"a")
        backend.write_atomic(f"{sub}/b.txt", b"b")
        backend.write_atomic(f"{sub}/nested/c.txt", b"c")

        files: list[str] = []
        folders: list[str] = []
        for entry in backend.iter_children(sub):
            if isinstance(entry, FileInfo):
                files.append(str(entry.path))
            else:
                folders.append(str(entry.path))

        assert sorted(files) == [f"{sub}/a.txt", f"{sub}/b.txt"]
        assert sorted(folders) == [f"{sub}/nested"]


# ---------------------------------------------------------------------------
# BE-014 — delete happy path on a real HNS account
# ---------------------------------------------------------------------------


class TestAzureLiveHnsDelete:
    """``delete`` must remove the file from the account.

    The production code calls ``delete_blob`` on the blob client; on HNS the
    SDK routes this through the DataLake layer. Mocks confirm the SDK call;
    only a real account confirms the file actually vanishes (``exists`` flips
    to ``False``, subsequent reads raise ``NotFound``).

    Spec: BE-014 (delete).
    """

    @pytest.mark.spec("BE-014")
    def test_delete_removes_file_from_account(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        path = f"{prefix}/delete-{uuid.uuid4().hex[:8]}.txt"
        backend.write_atomic(path, _PAYLOAD)
        assert backend.exists(path) is True

        backend.delete(path)

        assert backend.exists(path) is False
        with pytest.raises(NotFound, match="(?i)not found"):
            backend.read_bytes(path)


# ---------------------------------------------------------------------------
# BE-019 — copy on a real HNS account
# ---------------------------------------------------------------------------


class TestAzureLiveHnsCopy:
    """``copy`` must create an independent blob; respect overwrite semantics.

    Production code uses ``start_copy_from_url`` (no HNS-specific branch), but
    running it against an HNS account confirms the blob layer remains usable
    on HNS resources and that the ``get_blob_properties`` overwrite probe
    correctly detects existing destinations.

    Spec: BE-019 (copy).
    """

    @pytest.mark.spec("BE-019")
    def test_copy_creates_independent_blob(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/copy-src-{uid}.txt"
        dst = f"{prefix}/copy-dst-{uid}.txt"
        payload = b"copy-content-" + uuid.uuid4().bytes

        backend.write_atomic(src, payload)
        backend.copy(src, dst)

        # Both must be readable after copy — src is preserved, dst is independent.
        assert backend.read_bytes(src) == payload
        assert backend.read_bytes(dst) == payload

    @pytest.mark.spec("BE-019")
    def test_copy_overwrite_false_existing_dst_raises_already_exists(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/copy-src-exists-{uid}.txt"
        dst = f"{prefix}/copy-dst-exists-{uid}.txt"

        backend.write_atomic(src, b"src")
        backend.write_atomic(dst, b"dst-original")

        with pytest.raises(AlreadyExists, match="already exists"):
            backend.copy(src, dst)
        # The failed copy must not have touched the destination.
        assert backend.read_bytes(dst) == b"dst-original"

    @pytest.mark.spec("BE-019")
    def test_copy_overwrite_true_replaces_dst(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        prefix = dirpath.rsplit("/", 1)[0]
        uid = uuid.uuid4().hex[:8]
        src = f"{prefix}/copy-src-over-{uid}.txt"
        dst = f"{prefix}/copy-dst-over-{uid}.txt"

        backend.write_atomic(src, b"new-content")
        backend.write_atomic(dst, b"old-content")

        backend.copy(src, dst, overwrite=True)
        assert backend.read_bytes(dst) == b"new-content"


# ---------------------------------------------------------------------------
# BE-021 — file-API operations on an HNS directory must raise InvalidPath
# ---------------------------------------------------------------------------


class TestAzureLiveHnsFileApiOnDirectory:
    """``read_bytes`` and ``delete`` on HNS directory blobs — actual live behaviour.

    BE-021 mandates that file-API operations on a directory path raise
    ``InvalidPath``. ``write``/``write_atomic``/``open_atomic`` enforce this via
    the ``hdi_isfolder`` probe (BUG-190/BUG-192); ``read_bytes`` and ``delete``
    do not. These tests document the actual live behaviour:

    - ``read_bytes(hns_dir)`` silently returns ``b""`` (0 bytes).
    - ``delete(hns_dir)`` silently deletes the directory marker — a data-loss
      defect, since the caller invoked the *file*-API ``delete()``.

    Both deviations are tracked as **BUG-197** in ``sdd/BACKLOG.md``. The tests
    must be flipped back to ``with pytest.raises(InvalidPath):`` when that fix
    lands — they then become regression guards for the spec contract.

    Spec: BE-021 (directory-path guard), BE-013 (read), BE-014 (delete).
    """

    @pytest.mark.spec("BE-021", "BE-013")
    def test_read_bytes_on_hns_directory_returns_empty_bytes(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        """BUG-197: should raise ``InvalidPath`` per BE-021; currently returns ``b""``."""
        backend, dirpath = live_hns_backend
        result = backend.read_bytes(dirpath)
        assert result == b""

    @pytest.mark.spec("BE-021", "BE-014")
    def test_delete_on_hns_directory_silently_removes_directory(
        self,
        live_hns_backend: tuple[AzureBackend, str],
        live_hns_env: tuple[str, str],
    ) -> None:
        """BUG-197: should raise ``InvalidPath`` per BE-021; currently destroys the directory.

        Uses an isolated, per-test directory (not the module-shared one) because
        a successful delete actually mutates the account: a shared directory
        would be gone for all subsequent tests in the module.
        """
        backend, dirpath = live_hns_backend
        # Reuse the env values already validated by _require_live_env() in the
        # fixture chain; direct os.environ access here would raise KeyError instead
        # of the descriptive pytest.fail message on misconfiguration.
        conn, fs_name = live_hns_env
        prefix = dirpath.rsplit("/", 1)[0]
        # Provision a fresh directory just for this destructive test. The backend
        # API has no create_directory method, so use the underlying DataLake client.
        scratch_dir = f"{prefix}/scratch-dir-{uuid.uuid4().hex[:8]}"
        service = DataLakeServiceClient.from_connection_string(conn)
        try:
            fs_client = service.get_file_system_client(fs_name)
            fs_client.get_directory_client(scratch_dir).create_directory()

            assert backend.exists(scratch_dir) is True
            backend.delete(scratch_dir)
            # The directory marker is gone — this is the data-loss surface.
            assert backend.exists(scratch_dir) is False
        finally:
            service.close()
