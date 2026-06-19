"""Live ADLS Gen2 (HNS) integration tests for ``AzureBackend``.

Covers HNS semantics that the conformance suite against ``azure_live``
cannot reach. Happy-path coverage (write/read/move/copy/delete/list,
NotFound, exists on regular paths, write_atomic content round-trip, etc.)
lives in ``tests/backends/conformance/`` and runs against the same real
ADLS Gen2 account via the ``azure_live`` fixture; duplicating those cases
here is what BK-182 removed.

What stays here are cases the conformance suite cannot express:

* **Directory-blob ``hdi_isfolder`` probes.** Conformance fabricates a
  "directory" by writing ``backend.write("dir/file.txt", ...)`` which only
  creates a virtual prefix, not an HNS directory blob with the
  ``hdi_isfolder`` marker. Tests here provision the directory via
  ``DataLakeServiceClient.create_directory()`` and verify the production
  marker-probe fires:

  - ``write`` / ``write_atomic`` / ``open_atomic`` on an HNS directory
    raise ``InvalidPath`` (``TestAzureLiveHnsDirectoryGuard``).
  - ``get_file_info`` on an HNS directory raises ``InvalidPath``
    (``TestAzureLiveHnsGetFileInfoOnDirectory``).
  - ``is_folder`` returns ``True`` and ``is_file`` returns ``False`` on
    an HNS directory (``TestAzureLiveHnsIsFolderIsFile``, BUG-203).
  - ``read_bytes`` / ``delete`` on an HNS directory raise ``InvalidPath``
    without mutating account state (``TestAzureLiveHnsFileApiOnDirectory``,
    BUG-197 data-loss guard).

* **WriteResult etag normalisation cross-check.** WriteResult etag from
  post-rename ``get_file_properties`` and FileInfo etag from
  ``get_blob_properties`` must agree — a normalisation drift between the
  two SDK paths only surfaces against a real account
  (``TestAzureLiveHnsWriteResult``, AZ-034).

* **``write_atomic`` streaming guard against BUG-202.** The DFS append
  protocol (``create_file`` → ``append_data`` → ``flush_data``) is the
  fix for the ``MissingRequiredQueryParameter`` regression on HNS.
  Production dispatches on ``isinstance(content, bytes)``, so both the
  conformance streaming test and this kept test route a ``BytesIO``
  payload through the same DFS append branch; what this test adds is
  post-rename read-back byte-equality, which catches the failure mode
  where a miscomputed ``position`` lets ``WriteResult.size`` look right
  while the uploaded bytes are wrong. The multi-chunk offset arithmetic
  lives in monkeypatched mock tests under ``test_config.py``
  (``TestAzureLiveHnsWriteAtomicStreaming``).

* **``get_folder_info("")`` HNS root carve-out.** Real ADLS Gen2 rejects
  ``get_directory_client("")``; the production code skips the per-path
  probe for the root and relies on ``get_paths(path="/")`` instead
  (``TestAzureLiveHnsGetFolderInfoRoot``, BUG-213, AZ-024).

* **HNS ``exists`` fallback on real HNS directories.** Only a
  real account exercises the blob-client miss → DataLake directory probe
  fallback chain (``TestAzureLiveHnsExists``).

Spec: TEST-003 (per-backend deviation tier); BE-005, BE-008, BE-010,
BE-013, BE-014, BE-015, BE-016, BE-017, BE-021, SAW-001, WR-001a,
AZ-024, AZ-034.

Tiers (BK-303)
--------------

Each test runs against two records, parametrised by the azure-subtree
conftest (``tests/backends/azure/conftest.py``):

* ``azure_live_hns`` — the real ADLS Gen2 account. Carries
  ``pytest.mark.live`` (default ``addopts`` is ``-m 'not live'``, so a plain
  ``hatch run test`` skips it) and its factory ``pytest.skip``s unless
  ``RS_TEST_LIVE_HNS=1``. ``AZURE_STORAGE_CONNECTION_STRING`` and
  ``RS_TEST_LIVE_HNS_CONTAINER`` must point at a *real* account — the fixture
  fails loud rather than silent-skipping if they are missing or point at
  Azurite. Pass ``--record`` (Stage 3) to capture cassettes.
* ``azure_replay_hns`` — replays the committed cassette creds-free at Stage 1.
  Skipped (not errored) when its cassette is absent.

Cost discipline
---------------

The whole point of this file is "is the precondition observed against a
real account?" Test bodies stay deterministic (fixed basenames; the
per-session ``live-hns/<uuid8>`` prefix gives cross-run isolation) and
payloads stay small. The conftest provisions one HNS directory per test and
best-effort deletes the prefix on teardown so a teardown race does not turn a
green test red.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.storage.filedatalake import DataLakeServiceClient  # noqa: E402

from remote_store._errors import InvalidPath  # noqa: E402
from remote_store._path import RemotePath  # noqa: E402
from remote_store.backends import AzureUtils  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

    from remote_store.backends._azure import AzureBackend


# The ``live_hns_backend`` / ``live_hns_env`` fixtures and the live/replay
# parametrize live in ``tests/backends/azure/conftest.py`` (BK-303): each test
# body runs against both the live ``azure_live_hns`` record (recordable) and
# the creds-free ``azure_replay_hns`` cassette tier.


# ---------------------------------------------------------------------------
# AZ-006 — AzureUtils.detect_hns against a real ADLS Gen2 account
# ---------------------------------------------------------------------------


@pytest.mark.spec("AZ-006")
class TestAzureLiveDetectHns:
    """The discovery helper reports HNS=True against a real ADLS Gen2 account.

    Mocks can only encode the assumed ``get_account_information()`` shape; this
    confirms the real account returns the ``is_hns_enabled`` key as ``True`` so
    a user calling ``detect_hns`` to populate ``AzureBackend(hns=...)`` gets the
    correct value live.
    """

    def test_detect_hns_true_on_real_hns(self, live_hns_env: tuple[str, str]) -> None:
        conn, _fs = live_hns_env
        assert AzureUtils.detect_hns(connection_string=conn) is True


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

    Companion to ``TestAzureWriteOnHnsDirectory`` in ``test_config.py``,
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
        # Deterministic basename (no uuid): the per-session ``live-hns/<uuid8>``
        # prefix gives cross-run isolation, and each test uses a distinct
        # basename, so the cassette path is stable for replay (BK-303).
        path = f"{prefix}/wr-native.txt"

        result = backend.write_atomic(path, _PAYLOAD)

        # WR-004 / WR-001a: HNS backend declares WRITE_RESULT_NATIVE; source must be "native".
        assert result.source == "native"
        # WR-001a: size must equal the committed byte count.
        assert result.size == len(_PAYLOAD)
        # WR-001a / AZ-034: on the success path, etag from post-rename
        # get_file_properties must be non-empty, quote-stripped, and lowercased.
        # On a transient post-rename read failure the BUG-173 fallback returns
        # etag=None (rename already committed; WR-001a lists etag as Optional).
        if result.etag is not None:
            assert result.etag != ""
            assert '"' not in result.etag, f"etag must be quote-stripped; got {result.etag!r}"
            assert result.etag == result.etag.lower(), f"etag must be lowercased; got {result.etag!r}"
            # WR-001a: last_modified from the post-rename read must be timezone-aware.
            assert result.last_modified is not None, "HNS write_atomic must populate WriteResult.last_modified"
            assert result.last_modified.tzinfo is not None, "last_modified must be timezone-aware"
            # AZ-034 consistency: WriteResult.etag and FileInfo.etag must agree.
            fi = backend.get_file_info(path)
            assert fi.etag is not None
            assert fi.etag == result.etag, (
                f"WriteResult.etag {result.etag!r} != FileInfo.etag {fi.etag!r}: "
                "normalisation inconsistent between post-rename get_file_properties and get_file_info"
            )
        else:
            # Fallback path — rename committed, post-rename read failed
            # transiently. WR-001a allows etag=None; retrying would raise
            # AlreadyExists. The fallback contract is verified by mock
            # tests in tests/backends/azure/test_config.py. Skip rather
            # than silently pass so a fallback run is audible — the
            # method name asserts "fully native" and the rest of that
            # contract is not exercised on this path.
            pytest.skip("transient post-rename read failure; fully-native contract not exercised on fallback path")


# ---------------------------------------------------------------------------
# BE-016 — get_file_info on an HNS directory blob
# ---------------------------------------------------------------------------


class TestAzureLiveHnsGetFileInfoOnDirectory:
    """``get_file_info`` on an HNS directory blob must raise ``InvalidPath``.

    ADLS Gen2 marks directory blobs with ``hdi_isfolder=true`` metadata. The
    production code detects this marker and raises ``InvalidPath`` so callers cannot
    treat a directory as a file. Mock-only suites fabricate ``hdi_isfolder`` on a
    ``BlobProperties`` stub; only a real account confirms the marker is present on
    a directory created via ``DataLakeServiceClient``.

    Spec: BE-016 (get_file_info), BE-021 (directory-path guard).
    """

    @pytest.mark.spec("BE-016", "BE-021")
    def test_get_file_info_on_hns_directory_raises_invalid_path(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        with pytest.raises(InvalidPath, match="exists as a directory"):
            backend.get_file_info(dirpath)


class TestAzureLiveHnsIsFolderIsFile:
    """``is_folder`` / ``is_file`` semantics on a real HNS directory + file.

    BUG-203 changed ``is_folder`` from "return True whenever
    ``get_directory_properties()`` succeeds" to "return True only when
    ``hdi_isfolder`` is set in metadata". The mock-level test fabricates the
    metadata; this class proves the marker is actually present on a directory
    created via ``DataLakeServiceClient.create_directory()`` (the way
    ``live_hns_backend`` provisions ``dirpath``) and absent on a regular file
    written via ``write_atomic`` — different SDK code paths than the conformance
    cassette's blob HEAD captures.

    Spec: BE-005 (is_folder / is_file).
    """

    @pytest.mark.spec("BE-005")
    def test_is_folder_true_on_hns_directory(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        assert backend.is_folder(dirpath) is True

    @pytest.mark.spec("BE-005")
    def test_is_file_false_on_hns_directory(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        assert backend.is_file(dirpath) is False


# ---------------------------------------------------------------------------
# BE-015 — exists() on a real HNS directory
# ---------------------------------------------------------------------------


class TestAzureLiveHnsExists:
    """``exists`` on a real HNS directory.

    Conformance covers ``exists`` on regular present / missing files. On HNS, a
    directory created via ``DataLakeServiceClient`` is visible on the *blob*
    endpoint too: ``get_blob_properties`` returns ``200`` carrying
    ``hdi_isfolder=true`` (verify against the committed cassette), so ``exists``
    resolves ``True`` at the blob check (``_azure.py`` ``exists``) without
    reaching the ``ResourceNotFoundError`` → DataLake directory-probe fallback —
    that fallback is defensive ``# pragma: no cover`` for directories with no
    blob marker, which ``create_directory`` does not produce.

    The point this guards is that a real HNS directory reads as an existing
    *directory*, not a file: ``exists`` True, ``is_folder`` True (the
    ``hdi_isfolder`` marker), ``is_file`` False. A plain blob would also satisfy
    ``exists``, so the ``is_folder`` / ``is_file`` assertions are what pin the
    HNS-directory case.

    Spec: BE-015 (exists).
    """

    @pytest.mark.spec("BE-015")
    def test_exists_returns_true_for_hns_directory(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        backend, dirpath = live_hns_backend
        assert backend.exists(dirpath) is True
        # Pin the HNS-directory resolution (a flat blob would also yield exists
        # True): the path reads as a directory, not a file.
        assert backend.is_folder(dirpath) is True
        assert backend.is_file(dirpath) is False


# ---------------------------------------------------------------------------
# BE-021 — file-API operations on an HNS directory must raise InvalidPath
# ---------------------------------------------------------------------------


class TestAzureLiveHnsFileApiOnDirectory:
    """``read_bytes`` and ``delete`` on HNS directory blobs must raise ``InvalidPath``.

    BE-021 mandates that file-API operations on a directory path raise
    ``InvalidPath``. ``write``/``write_atomic``/``open_atomic`` enforce this via
    the ``hdi_isfolder`` probe (BUG-190/BUG-192); ``read_bytes`` and ``delete``
    are fixed by BUG-197. These tests are the live regression guards for the
    spec contract.

    Spec: BE-021 (directory-path guard), BE-013 (read), BE-014 (delete).
    """

    @pytest.mark.spec("BE-021", "BE-013")
    def test_read_bytes_on_hns_directory_raises_invalid_path(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        """BUG-197 fix: read_bytes on an HNS directory must raise ``InvalidPath``."""
        backend, dirpath = live_hns_backend
        with pytest.raises(InvalidPath, match="is a directory"):
            backend.read_bytes(dirpath)

    @pytest.mark.spec("BE-021", "BE-014")
    def test_delete_on_hns_directory_raises_invalid_path(
        self,
        live_hns_backend: tuple[AzureBackend, str],
        live_hns_env: tuple[str, str],
    ) -> None:
        """BUG-197 fix: delete on an HNS directory must raise ``InvalidPath``.

        Uses an isolated, per-test directory (not the module-shared one) so that
        when the fix is working the directory is NOT deleted and subsequent tests
        are unaffected. A failing test (InvalidPath not raised, directory deleted)
        would still be isolated because the scratch directory is fresh each run.
        """
        backend, dirpath = live_hns_backend
        conn, fs_name = live_hns_env
        prefix = dirpath.rsplit("/", 1)[0]
        scratch_dir = f"{prefix}/scratch-dir"
        service = DataLakeServiceClient.from_connection_string(conn)
        try:
            fs_client = service.get_file_system_client(fs_name)
            fs_client.get_directory_client(scratch_dir).create_directory()

            assert backend.exists(scratch_dir) is True
            with pytest.raises(InvalidPath, match="is a directory"):
                backend.delete(scratch_dir)
            # Directory must still exist — InvalidPath must have fired before
            # any SDK mutation (BUG-197 data-loss guard).
            assert backend.exists(scratch_dir) is True
        finally:
            # Best-effort cleanup: delete the scratch directory via the DataLake
            # client (bypasses the file-API guard that prevents backend.delete).
            with contextlib.suppress(Exception):
                fs_client.get_directory_client(scratch_dir).delete_directory()
            service.close()


# ---------------------------------------------------------------------------
# BE-017 — get_folder_info("") on a real HNS account (root-path coverage)
# ---------------------------------------------------------------------------


class TestAzureLiveHnsGetFolderInfoRoot:
    """``get_folder_info("")`` on a real HNS account exercises the root-path call shape.

    BUG-213 contract (post-fix): the HNS branch skips the per-path
    ``get_directory_client(azure_path)`` probe when ``azure_path == ""`` —
    real ADLS Gen2 rejects ``get_directory_client("")`` with "Please specify
    a file system name and file path", and the root is always a folder so
    no marker probe is needed.  The branch relies on
    ``_fs.get_paths(path="/", recursive=True)`` (the deliberate ``or "/"``
    fallback) to enumerate the root.

    The test runs against a dedicated *empty* filesystem (``LIVE_HNS_ROOT_FS``,
    via ``live_hns_root_backend``) rather than the shared container: enumerating
    the shared root recursively would bake its mutable top-level inventory into
    the cassette — non-reproducible on re-record and an unbounded residue
    surface. An empty root enumerates to ``{"paths":[]}``, so the aggregates are
    an exact, asserted contract instead of unverified payload.

    Spec: BE-017 (get_folder_info postcondition); AZ-024 (HNS root-path carve-out).
    """

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_root_returns_valid_folder_info(
        self,
        live_hns_root_backend: AzureBackend,
    ) -> None:
        """Root get_folder_info must succeed and return an empty FolderInfo for path=''.

        Contract under test: ``get_folder_info("")`` against an HNS account
        completes without an SDK exception, takes the root-path carve-out
        (skips the ``get_directory_client("")`` probe, uses the ``or "/"``
        ``get_paths`` fallback), and returns a ``FolderInfo`` rooted at
        ``RemotePath.ROOT``. Against the dedicated empty filesystem the
        aggregates are exact and reproducible: zero files, zero bytes.
        """
        from remote_store._models import FolderInfo  # noqa: PLC0415 -- intentional late import

        info = live_hns_root_backend.get_folder_info("")
        assert isinstance(info, FolderInfo)
        # FolderInfo.path is a RemotePath; the root normalises to RemotePath.ROOT
        # (str form "."), and RemotePath.__eq__ returns NotImplemented for str
        # operands — comparing against "" would always be False.
        assert info.path == RemotePath.ROOT
        # Empty dedicated filesystem → exact, reproducible aggregates.
        assert info.file_count == 0
        assert info.total_size == 0


class TestAzureLiveHnsWriteAtomicStreaming:
    """``write_atomic`` with a streaming ``BinaryIO`` input on a real HNS account.

    BUG-202: streaming ``write_atomic`` previously called ``upload_data`` with the
    unseekable ``_ByteCountingIO`` wrapper, which left ``position=None`` on the
    DataLake SDK's ``flush_data`` call.  Real HNS rejected this with
    ``MissingRequiredQueryParameter``; Azurite forgave it.  The fix drives the
    DFS append protocol directly (``create_file`` → per-chunk
    ``append_data(offset, length)`` → ``flush_data(position)``), mirroring the
    async sibling introduced by BUG-194.

    Stage 3 coverage: this class exercises the streaming path end-to-end against
    a real ADLS Gen2 account, parallel to ``TestAzureLiveHnsGetFolderInfoRoot``
    for BUG-213.  Verifies both that the write succeeds (no
    ``MissingRequiredQueryParameter``) and that the bytes round-trip intact.

    Spec: BE-010 (write_atomic atomic temp+rename), WR-001a (WriteResult.size).
    Cassette: new Stage 3 cassette required — record with
    ``RS_TEST_LIVE_HNS=1 hatch run record-azure``.
    """

    @pytest.mark.spec("BE-010", "WR-001a")
    def test_write_atomic_streaming_input_succeeds_on_real_hns(
        self,
        live_hns_backend: tuple[AzureBackend, str],
    ) -> None:
        """Streaming write_atomic must succeed on real HNS and preserve the payload.

        Contract under test: a ``BinaryIO`` payload routed to the DFS append
        branch (``create_file`` → ``append_data`` → ``flush_data``) uploads
        successfully, ``flush_data(position)`` carries the correct byte count,
        and the post-rename read-back matches the original payload. Pre-fix
        this raised ``MissingRequiredQueryParameter``. Differentiator vs the
        conformance streaming test: that test asserts only
        ``WriteResult.size``; this one asserts post-rename body equality on
        a real account, which catches the failure mode where a miscomputed
        ``position`` lets ``result.size`` look right while the uploaded
        bytes are wrong.
        """
        import io  # noqa: PLC0415 -- intentional late import

        backend, dirpath = live_hns_backend
        target = f"{dirpath}/streaming.bin"
        # 1152 bytes: single chunk at the default 1 MiB ``_AZURE_BLOCK_SIZE``.
        # The multi-chunk offset arithmetic is covered by the mock test
        # ``test_write_atomic_hns_streaming_uses_dfs_append_protocol`` in
        # ``test_config.py`` (which monkeypatches the block size to 50);
        # this live test asserts post-rename body equality against real
        # ADLS Gen2 to guard against a miscomputed-position regression
        # that would let ``result.size`` look right with wrong bytes on
        # the wire.
        payload = b"streaming-payload-" * 64
        try:
            result = backend.write_atomic(target, io.BytesIO(payload), overwrite=True)
            assert result.size == len(payload), f"WriteResult.size {result.size} != payload size {len(payload)}"
            assert backend.read_bytes(target) == payload, "round-trip body must match"
        finally:
            with contextlib.suppress(Exception):
                backend.delete(target, missing_ok=True)
