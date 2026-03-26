"""SFTP backend tests -- covers SFTP-xxx spec items.

Requires: paramiko, tenacity (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import contextlib
import errno
import io
import os
import shutil
import tempfile
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

# Guard: skip entire module if dependencies are missing
paramiko = pytest.importorskip("paramiko", reason="paramiko not installed")
pytest.importorskip("tenacity", reason="tenacity not installed")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo  # noqa: E402
from remote_store.backends._sftp import (  # noqa: E402
    HostKeyPolicy,
    SFTPBackend,
    _sanitize_pem,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


@pytest.fixture()
def sftp_backend(sftp_server: tuple[int, str]) -> Iterator[Backend]:
    """Create an SFTPBackend against the in-process SFTP server."""
    port, host_key_entry = sftp_server
    base_path = f"/test_{uuid.uuid4().hex[:8]}"
    backend = SFTPBackend(
        host="127.0.0.1",
        port=port,
        username="testuser",
        password="testpass",
        base_path=base_path,
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    yield backend
    backend.close()


# region: Construction (SFTP-001 through SFTP-005)
class TestSFTPConstruction:
    """SFTP-001 through SFTP-005: construction and identity."""

    @pytest.mark.spec("SFTP-001")
    def test_constructor_minimal(self, sftp_backend: Backend) -> None:
        """Backend can be constructed with host and credentials."""
        assert sftp_backend is not None

    @pytest.mark.spec("SFTP-002")
    def test_name_is_sftp(self, sftp_backend: Backend) -> None:
        assert sftp_backend.name == "sftp"

    @pytest.mark.spec("SFTP-003")
    def test_declares_all_capabilities(self, sftp_backend: Backend) -> None:
        caps = sftp_backend.capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            if cap is Capability.GLOB:
                assert not caps.supports(cap), "SFTP should not declare GLOB"
            else:
                assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("SFTP-004")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        backend = SFTPBackend(
            host="nonexistent.invalid",
            port=99999,
            username="x",
            password="x",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
        )
        # Should succeed -- no connection attempted yet
        assert backend.name == "sftp"

    @pytest.mark.spec("SFTP-005")
    @pytest.mark.parametrize("host", [pytest.param("", id="empty"), pytest.param("   ", id="whitespace")])
    def test_invalid_host_raises(self, host: str) -> None:
        with pytest.raises(ValueError, match="host"):
            SFTPBackend(host=host)


# endregion


# region: Connection (SFTP-006 through SFTP-010)
class TestSFTPConnection:
    """SFTP-006 through SFTP-010: connection and host key handling."""

    @pytest.mark.spec("SFTP-006")
    def test_host_key_policy_enum(self) -> None:
        """HostKeyPolicy enum has expected values."""
        assert HostKeyPolicy.STRICT.value == "strict"
        assert HostKeyPolicy.TRUST_ON_FIRST_USE.value == "tofu"
        assert HostKeyPolicy.AUTO_ADD.value == "auto"

    @pytest.mark.spec("SFTP-009")
    def test_connection_established_on_first_use(self, sftp_backend: Backend) -> None:
        """First operation triggers connection."""
        assert sftp_backend.exists("nonexistent.txt") is False

    @pytest.mark.spec("SFTP-010")
    def test_staleness_reconnect(self, sftp_backend: Backend) -> None:
        """Backend reconnects when connection goes stale."""
        assert isinstance(sftp_backend, SFTPBackend)
        # Force a first connection
        sftp_backend.exists("test.txt")
        # Close the connection manually to simulate staleness
        sftp_backend._close_clients()
        # Next operation should reconnect automatically
        assert sftp_backend.exists("test.txt") is False


# endregion


# region: Filesystem Model (SFTP-011 through SFTP-013)
class TestSFTPFilesystemModel:
    """SFTP-011 through SFTP-013: real directory semantics."""

    @pytest.mark.spec("SFTP-011")
    def test_real_directories(self, sftp_backend: Backend) -> None:
        """SFTP uses real directories, not virtual prefixes."""
        sftp_backend.write("realdir/file.txt", b"content")
        assert sftp_backend.is_folder("realdir") is True

    @pytest.mark.spec("SFTP-012")
    def test_write_creates_intermediate_dirs(self, sftp_backend: Backend) -> None:
        """Writing to nested path creates parent directories."""
        sftp_backend.write("a/b/c/deep.txt", b"deep")
        assert sftp_backend.read_bytes("a/b/c/deep.txt") == b"deep"
        assert sftp_backend.is_folder("a") is True
        assert sftp_backend.is_folder("a/b") is True
        assert sftp_backend.is_folder("a/b/c") is True

    @pytest.mark.spec("SFTP-013")
    def test_empty_folders_persist(self, sftp_backend: Backend) -> None:
        """Empty directories persist after their contents are deleted."""
        sftp_backend.write("persist/only.txt", b"x")
        assert sftp_backend.is_folder("persist") is True
        sftp_backend.delete("persist/only.txt")
        # Unlike S3, the folder should still exist
        assert sftp_backend.is_folder("persist") is True


# endregion


# region: Atomic Write (SFTP-014, SFTP-015)
class TestSFTPAtomicWrite:
    """SFTP-014, SFTP-015: simulated atomic write."""

    @pytest.mark.spec("SFTP-014")
    def test_write_atomic_creates_file(self, sftp_backend: Backend) -> None:
        sftp_backend.write_atomic("atomic.txt", b"atomic content")
        assert sftp_backend.read_bytes("atomic.txt") == b"atomic content"

    @pytest.mark.spec("SFTP-014")
    def test_write_atomic_no_temp_file_left(self, sftp_backend: Backend) -> None:
        """After successful atomic write, no temp files should remain."""
        sftp_backend.write_atomic("clean.txt", b"content")
        # List files -- should only see the target, no .~tmp.* files
        files = list(sftp_backend.list_files(""))
        temp_files = [f for f in files if f.name.startswith(".~tmp.")]
        assert temp_files == []

    @pytest.mark.spec("SFTP-015")
    def test_write_atomic_overwrite(self, sftp_backend: Backend) -> None:
        sftp_backend.write_atomic("at.txt", b"first")
        sftp_backend.write_atomic("at.txt", b"second", overwrite=True)
        assert sftp_backend.read_bytes("at.txt") == b"second"

    @pytest.mark.spec("SFTP-015")
    def test_write_atomic_already_exists(self, sftp_backend: Backend) -> None:
        sftp_backend.write_atomic("at2.txt", b"first")
        with pytest.raises(AlreadyExists):
            sftp_backend.write_atomic("at2.txt", b"second", overwrite=False)


# endregion


# region: delete_folder (SFTP-016, SFTP-017)
class TestSFTPDeleteFolder:
    """SFTP-016, SFTP-017: delete_folder semantics."""

    @pytest.mark.spec("SFTP-016")
    def test_delete_folder_recursive(self, sftp_backend: Backend) -> None:
        sftp_backend.write("rf/a.txt", b"a")
        sftp_backend.write("rf/sub/b.txt", b"b")
        sftp_backend.delete_folder("rf", recursive=True)
        assert sftp_backend.exists("rf/a.txt") is False
        assert sftp_backend.exists("rf/sub/b.txt") is False
        assert sftp_backend.is_folder("rf") is False

    @pytest.mark.spec("SFTP-016")
    def test_delete_folder_recursive_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.delete_folder("ghost", recursive=True)

    @pytest.mark.spec("SFTP-016")
    def test_delete_folder_recursive_missing_ok(self, sftp_backend: Backend) -> None:
        sftp_backend.delete_folder("ghost", recursive=True, missing_ok=True)

    @pytest.mark.spec("SFTP-017")
    def test_delete_folder_non_recursive_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.delete_folder("empty", recursive=False)

    @pytest.mark.spec("SFTP-017")
    def test_delete_folder_non_recursive_non_empty(self, sftp_backend: Backend) -> None:
        sftp_backend.write("nonempty/file.txt", b"x")
        with pytest.raises(DirectoryNotEmpty):
            sftp_backend.delete_folder("nonempty", recursive=False)


# endregion


# region: Move and Copy (SFTP-018, SFTP-019)
class TestSFTPMoveCopy:
    """SFTP-018, SFTP-019: move and copy operations."""

    @pytest.mark.spec("SFTP-018")
    def test_move(self, sftp_backend: Backend) -> None:
        sftp_backend.write("src.txt", b"data")
        sftp_backend.move("src.txt", "dst.txt")
        assert sftp_backend.exists("src.txt") is False
        assert sftp_backend.read_bytes("dst.txt") == b"data"

    @pytest.mark.parametrize(
        ("op", "src_setup", "dst_setup", "kwargs", "expected_error"),
        [
            pytest.param("move", False, False, {}, NotFound, id="move-not-found"),
            pytest.param("move", True, True, {"overwrite": False}, AlreadyExists, id="move-already-exists"),
            pytest.param("copy", False, False, {}, NotFound, id="copy-not-found"),
            pytest.param("copy", True, True, {"overwrite": False}, AlreadyExists, id="copy-already-exists"),
        ],
    )
    @pytest.mark.spec("SFTP-018")
    def test_move_copy_errors(
        self,
        sftp_backend: Backend,
        op: str,
        src_setup: bool,
        dst_setup: bool,
        kwargs: dict[str, object],
        expected_error: type,
    ) -> None:
        src, dst = f"{op}_e_src.txt", f"{op}_e_dst.txt"
        if src_setup:
            sftp_backend.write(src, b"a")
        if dst_setup:
            sftp_backend.write(dst, b"b")
        with pytest.raises(expected_error):
            getattr(sftp_backend, op)(src, dst, **kwargs)

    @pytest.mark.spec("SFTP-018")
    def test_move_overwrite(self, sftp_backend: Backend) -> None:
        sftp_backend.write("mo1.txt", b"a")
        sftp_backend.write("mo2.txt", b"b")
        sftp_backend.move("mo1.txt", "mo2.txt", overwrite=True)
        assert sftp_backend.read_bytes("mo2.txt") == b"a"
        assert sftp_backend.exists("mo1.txt") is False

    @pytest.mark.spec("SFTP-019")
    def test_copy(self, sftp_backend: Backend) -> None:
        sftp_backend.write("orig.txt", b"data")
        sftp_backend.copy("orig.txt", "clone.txt")
        assert sftp_backend.read_bytes("orig.txt") == b"data"
        assert sftp_backend.read_bytes("clone.txt") == b"data"

    @pytest.mark.spec("SFTP-019")
    def test_copy_overwrite(self, sftp_backend: Backend) -> None:
        sftp_backend.write("co1.txt", b"a")
        sftp_backend.write("co2.txt", b"b")
        sftp_backend.copy("co1.txt", "co2.txt", overwrite=True)
        assert sftp_backend.read_bytes("co2.txt") == b"a"
        assert sftp_backend.read_bytes("co1.txt") == b"a"


# endregion


# region: Error Mapping (SFTP-020 through SFTP-024)
class TestSFTPErrorMapping:
    """SFTP-020 through SFTP-024: error mapping."""

    @pytest.mark.spec("SFTP-020")
    def test_read_missing_maps_to_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound) as exc_info:
            sftp_backend.read_bytes("does-not-exist.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-020")
    def test_get_file_info_missing(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.get_file_info("nope.txt")

    @pytest.mark.spec("SFTP-020")
    def test_delete_missing(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.delete("nope.txt")

    @pytest.mark.spec("SFTP-021")
    def test_eacces_maps_to_permission_denied(self, sftp_backend: Backend) -> None:
        """OSError with errno.EACCES maps to PermissionDenied."""
        import errno
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        # Force connection so _sftp_client is populated
        sftp_backend.exists("warmup.txt")

        eacces = OSError(errno.EACCES, "Permission denied")
        with (
            patch.object(sftp_backend._sftp_client, "file", side_effect=eacces),
            pytest.raises(PermissionDenied) as exc_info,
        ):
            sftp_backend.read_bytes("secret.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-021")
    def test_eacces_on_remove_maps_to_permission_denied(self, sftp_backend: Backend) -> None:
        """OSError with errno.EACCES on remove maps to PermissionDenied."""
        import errno
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("locked.txt", b"data")

        eacces = OSError(errno.EACCES, "Permission denied")
        with (
            patch.object(sftp_backend._sftp_client, "remove", side_effect=eacces),
            pytest.raises(PermissionDenied) as exc_info,
        ):
            sftp_backend.delete("locked.txt")
        assert exc_info.value.backend == "sftp"
        assert exc_info.value.path == "locked.txt"

    @pytest.mark.spec("SFTP-022")
    def test_eexist_maps_to_already_exists(self, sftp_backend: Backend) -> None:
        """OSError with errno.EEXIST maps to AlreadyExists."""
        import errno
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        eexist = OSError(errno.EEXIST, "File exists")
        with (
            patch.object(sftp_backend._sftp_client, "file", side_effect=eexist),
            pytest.raises(AlreadyExists) as exc_info,
        ):
            sftp_backend.read_bytes("existing.txt")
        assert exc_info.value.backend == "sftp"
        assert exc_info.value.path == "existing.txt"

    @pytest.mark.spec("SFTP-023")
    def test_ssh_exception_maps_to_backend_unavailable(self, sftp_backend: Backend) -> None:
        """paramiko.SSHException maps to BackendUnavailable."""
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        with (
            patch.object(
                sftp_backend._sftp_client,
                "file",
                side_effect=paramiko.SSHException("SSH session not active"),
            ),
            pytest.raises(BackendUnavailable) as exc_info,
        ):
            sftp_backend.read_bytes("file.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-023")
    def test_ssh_exception_on_remove_maps_to_backend_unavailable(self, sftp_backend: Backend) -> None:
        """paramiko.SSHException on remove maps to BackendUnavailable."""
        from unittest.mock import patch

        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("target.txt", b"data")

        with (
            patch.object(
                sftp_backend._sftp_client,
                "remove",
                side_effect=paramiko.SSHException("Connection lost"),
            ),
            pytest.raises(BackendUnavailable) as exc_info,
        ):
            sftp_backend.delete("target.txt")
        assert exc_info.value.backend == "sftp"

    @pytest.mark.spec("SFTP-024")
    def test_no_native_exception_leaks(self, sftp_backend: Backend) -> None:
        """All errors must be RemoteStoreError subtypes."""
        with pytest.raises(RemoteStoreError):
            sftp_backend.read("nonexistent.txt")

    @pytest.mark.spec("SFTP-024")
    def test_error_has_backend_attribute(self, sftp_backend: Backend) -> None:
        with pytest.raises(RemoteStoreError) as exc_info:
            sftp_backend.read("missing.txt")
        assert exc_info.value.backend == "sftp"


# endregion


# region: Lifecycle (SFTP-025 through SFTP-027)
class TestSFTPLifecycle:
    """SFTP-025 through SFTP-027: close and unwrap."""

    @pytest.mark.spec("SFTP-025")
    def test_close_is_callable(self, sftp_backend: Backend) -> None:
        sftp_backend.close()

    @pytest.mark.spec("SFTP-027")
    def test_close_idempotent(self, sftp_backend: Backend) -> None:
        sftp_backend.close()
        sftp_backend.close()

    @pytest.mark.spec("SFTP-026")
    def test_unwrap_sftp_client(self, sftp_backend: Backend) -> None:
        client = sftp_backend.unwrap(paramiko.SFTPClient)
        assert isinstance(client, paramiko.SFTPClient)

    @pytest.mark.spec("SFTP-026")
    def test_unwrap_wrong_type_raises(self, sftp_backend: Backend) -> None:
        with pytest.raises(CapabilityNotSupported):
            sftp_backend.unwrap(str)


# endregion


# region: PEM Sanitization (SFTP-008)
class TestPEMSanitization:
    """SFTP-008: PEM key sanitization -- unit tests, no server needed."""

    @pytest.mark.spec("SFTP-008")
    def test_sanitize_valid_pem(self) -> None:
        """PEM with spaces as line separators is normalized to newlines."""
        # Build a fake PEM with spaces instead of newlines in payload
        header = "BEGIN RSA PRIVATE KEY"
        footer = "END RSA PRIVATE KEY"
        payload = "AAAA BBBB CCCC DDDD"
        pem = f"-----{header}-----{payload}-----{footer}-----"
        result = _sanitize_pem(pem)
        assert " " not in result.split("-----")[2]
        assert "\n" in result.split("-----")[2]

    @pytest.mark.spec("SFTP-008")
    def test_sanitize_invalid_structure(self) -> None:
        """PEM with wrong number of parts raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PEM"):
            _sanitize_pem("not-a-pem-string")

    @pytest.mark.spec("SFTP-008")
    def test_sanitize_multiple_non_base64_chars(self) -> None:
        """PEM with multiple non-base64 separator types raises ValueError."""
        pem = "-----BEGIN-----A B\tC-----END-----"
        with pytest.raises(ValueError, match="Unexpected PEM"):
            _sanitize_pem(pem)


# endregion


# region: Unit tests for helpers (no server needed)
class TestSFTPHelpers:
    """Unit tests for SFTPBackend helper methods -- no server needed."""

    def test_sftp_path_with_base_path_root(self) -> None:
        """_sftp_path with base_path='/' returns /<path>."""
        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        assert backend._sftp_path("file.txt") == "/file.txt"
        assert backend._sftp_path("a/b.txt") == "/a/b.txt"
        assert backend._sftp_path("") == "/"

    def test_sftp_path_with_base_path_subdir(self) -> None:
        """_sftp_path with base_path='/data' returns /data/<path>."""
        backend = SFTPBackend(host="dummy", base_path="/data", host_key_policy=HostKeyPolicy.AUTO_ADD)
        assert backend._sftp_path("file.txt") == "/data/file.txt"
        assert backend._sftp_path("") == "/data"

    def test_resolve_host_keys_direct(self) -> None:
        """Direct known_host_keys takes precedence."""
        backend = SFTPBackend(
            host="dummy",
            known_host_keys="ssh-rsa AAAA...",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
        )
        assert backend._resolved_host_keys == "ssh-rsa AAAA..."

    def test_stat_to_fileinfo_no_mtime(self) -> None:
        """_stat_to_fileinfo handles None mtime."""

        class FakeAttrs:
            st_size = 42
            st_mtime = None

        backend = SFTPBackend(host="dummy", host_key_policy=HostKeyPolicy.AUTO_ADD)
        fi = backend._stat_to_fileinfo("test.txt", FakeAttrs())
        assert fi.name == "test.txt"
        assert fi.size == 42
        assert fi.modified_at is not None


# endregion


# region: Read/Write roundtrip
class TestSFTPReadWrite:
    """Basic read/write roundtrip to verify full stack."""

    def test_write_and_read_bytes(self, sftp_backend: Backend) -> None:
        sftp_backend.write("hello.txt", b"hello world")
        assert sftp_backend.read_bytes("hello.txt") == b"hello world"

    def test_write_and_read_stream(self, sftp_backend: Backend) -> None:
        sftp_backend.write("stream.bin", b"\x00\x01\x02\xff")
        stream = sftp_backend.read("stream.bin")
        assert stream.read() == b"\x00\x01\x02\xff"

    def test_write_overwrite(self, sftp_backend: Backend) -> None:
        sftp_backend.write("ow.txt", b"first")
        sftp_backend.write("ow.txt", b"second", overwrite=True)
        assert sftp_backend.read_bytes("ow.txt") == b"second"

    def test_write_already_exists(self, sftp_backend: Backend) -> None:
        sftp_backend.write("ae.txt", b"first")
        with pytest.raises(AlreadyExists):
            sftp_backend.write("ae.txt", b"second")

    def test_write_nested_path(self, sftp_backend: Backend) -> None:
        sftp_backend.write("a/b/c/deep.txt", b"deep")
        assert sftp_backend.read_bytes("a/b/c/deep.txt") == b"deep"

    def test_write_from_binaryio(self, sftp_backend: Backend) -> None:
        import io

        sftp_backend.write("bio.txt", io.BytesIO(b"streamed"))
        assert sftp_backend.read_bytes("bio.txt") == b"streamed"


# endregion


# region: Listing and Metadata
class TestSFTPListing:
    """File and folder listing operations."""

    def test_list_files_non_recursive(self, sftp_backend: Backend) -> None:
        sftp_backend.write("lst/a.txt", b"a")
        sftp_backend.write("lst/b.txt", b"b")
        sftp_backend.write("lst/sub/c.txt", b"c")
        files = list(sftp_backend.list_files("lst"))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    def test_list_files_recursive(self, sftp_backend: Backend) -> None:
        sftp_backend.write("lr/a.txt", b"a")
        sftp_backend.write("lr/sub/b.txt", b"b")
        files = list(sftp_backend.list_files("lr", recursive=True))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    def test_list_files_empty_folder(self, sftp_backend: Backend) -> None:
        files = list(sftp_backend.list_files("empty"))
        assert files == []

    def test_list_folders(self, sftp_backend: Backend) -> None:
        sftp_backend.write("lf/sub1/a.txt", b"a")
        sftp_backend.write("lf/sub2/b.txt", b"b")
        sftp_backend.write("lf/root.txt", b"r")
        folders = list(sftp_backend.list_folders("lf"))
        assert {f.name for f in folders} == {"sub1", "sub2"}

    def test_list_folders_empty(self, sftp_backend: Backend) -> None:
        folders = list(sftp_backend.list_folders("empty"))
        assert folders == []


class TestSFTPMetadata:
    """File and folder metadata operations."""

    def test_get_file_info(self, sftp_backend: Backend) -> None:
        sftp_backend.write("info.txt", b"hello world")
        fi = sftp_backend.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "info.txt"
        assert fi.size == 11
        assert fi.modified_at is not None

    def test_get_file_info_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.get_file_info("missing.txt")

    def test_get_folder_info(self, sftp_backend: Backend) -> None:
        sftp_backend.write("fi/a.txt", b"aaa")
        sftp_backend.write("fi/b.txt", b"bb")
        fi = sftp_backend.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    def test_get_folder_info_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.get_folder_info("nodir")

    def test_get_folder_info_empty_folder(self, sftp_backend: Backend) -> None:
        """SFTP has real directories; empty folder should return FolderInfo with file_count=0."""
        # Create a directory by writing a file then deleting it
        sftp_backend.write("emptydir/tmp.txt", b"x")
        sftp_backend.delete("emptydir/tmp.txt")
        fi = sftp_backend.get_folder_info("emptydir")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 0
        assert fi.total_size == 0

    @pytest.mark.parametrize(
        ("setup", "path", "method", "expected"),
        [
            pytest.param(("e.txt", b"x"), "e.txt", "exists", True, id="exists-file"),
            pytest.param(None, "nope.txt", "exists", False, id="exists-missing"),
            pytest.param(("f.txt", b"x"), "f.txt", "is_file", True, id="is-file-true"),
            pytest.param(None, "missing.txt", "is_file", False, id="is-file-missing"),
            pytest.param(("dir2/f.txt", b"x"), "dir2", "is_file", False, id="is-file-not-folder"),
        ],
    )
    def test_existence_checks(
        self,
        sftp_backend: Backend,
        setup: tuple[str, bytes] | None,
        path: str,
        method: str,
        expected: bool,
    ) -> None:
        if setup:
            sftp_backend.write(setup[0], setup[1])
        assert getattr(sftp_backend, method)(path) is expected


class TestSFTPDelete:
    """Delete operations."""

    def test_delete_file(self, sftp_backend: Backend) -> None:
        sftp_backend.write("del.txt", b"x")
        sftp_backend.delete("del.txt")
        assert sftp_backend.exists("del.txt") is False

    @pytest.mark.parametrize(
        ("missing_ok", "raises"),
        [
            pytest.param(True, False, id="missing-ok"),
            pytest.param(False, True, id="missing-raises"),
        ],
    )
    def test_delete_missing(self, sftp_backend: Backend, missing_ok: bool, raises: bool) -> None:
        if raises:
            with pytest.raises(NotFound):
                sftp_backend.delete("nope.txt", missing_ok=missing_ok)
        else:
            sftp_backend.delete("nope.txt", missing_ok=missing_ok)


# endregion


# region: Coverage gap tests (BK-005)


class TestSFTPHostKeyPolicyCoercion:
    """BK-005: string-to-enum coercion in constructor (line 167)."""

    @pytest.mark.parametrize(
        ("input_str", "expected"),
        [
            pytest.param("auto", HostKeyPolicy.AUTO_ADD, id="auto"),
            pytest.param("strict", HostKeyPolicy.STRICT, id="strict"),
            pytest.param("tofu", HostKeyPolicy.TRUST_ON_FIRST_USE, id="tofu"),
            pytest.param("invalid", None, id="invalid"),
        ],
    )
    def test_host_key_policy_string_coercion(self, input_str: str, expected: HostKeyPolicy | None) -> None:
        if expected is None:
            with pytest.raises(ValueError):
                SFTPBackend(host="dummy", host_key_policy=input_str)
        else:
            backend = SFTPBackend(host="dummy", host_key_policy=input_str)
            assert backend._host_key_policy is expected


class TestSFTPToKey:
    """BK-005: to_key() all branches (lines 324, 326, 328)."""

    @pytest.mark.parametrize(
        ("base_path", "native_path", "expected"),
        [
            pytest.param("/", "/file.txt", "file.txt", id="root-file"),
            pytest.param("/", "/a/b/c.txt", "a/b/c.txt", id="root-nested"),
            pytest.param("/data", "/data/file.txt", "file.txt", id="subdir-file"),
            pytest.param("/data", "/data/sub/file.txt", "sub/file.txt", id="subdir-nested"),
            pytest.param("/data", "/data", "", id="equals-base"),
            pytest.param("/data", "/other/file.txt", "/other/file.txt", id="no-match"),
        ],
    )
    def test_to_key(self, base_path: str, native_path: str, expected: str) -> None:
        backend = SFTPBackend(host="dummy", base_path=base_path, host_key_policy="auto")
        assert backend.to_key(native_path) == expected


class TestSFTPMapException:
    """BK-005: _map_exception edge cases (lines 431, 437, 442)."""

    @staticmethod
    def _oserror_enoent() -> OSError:
        exc = OSError("No such file")
        exc.errno = errno.ENOENT
        return exc

    @pytest.mark.parametrize(
        ("exc_factory", "path", "expected_type", "check"),
        [
            pytest.param(
                lambda: NotFound("test", path="p", backend="sftp"),
                "p",
                NotFound,
                "identity",
                id="passthrough",
            ),
            pytest.param(
                _oserror_enoent.__func__,
                "missing.txt",
                NotFound,
                "path",
                id="oserror-enoent",
            ),
            pytest.param(
                lambda: OSError(errno.EIO, "I/O error"),
                "file.txt",
                RemoteStoreError,
                "not-specific",
                id="generic-oserror",
            ),
            pytest.param(
                lambda: FileNotFoundError("gone"),
                "gone.txt",
                NotFound,
                "type",
                id="file-not-found",
            ),
        ],
    )
    def test_map_exception(self, exc_factory: object, path: str, expected_type: type, check: str) -> None:
        backend = SFTPBackend(host="dummy", host_key_policy="auto")
        exc = exc_factory()
        result = backend._map_exception(exc, path)
        assert isinstance(result, expected_type)
        if check == "identity":
            assert result is exc
        elif check == "path":
            assert result.path == path
        elif check == "not-specific":
            assert not isinstance(result, (NotFound, PermissionDenied, AlreadyExists))


class TestSFTPTypeGuards:
    """BK-005: type guards — file/folder confusion (lines 544, 632, 645)."""

    def test_get_file_info_on_directory(self, sftp_backend: Backend) -> None:
        """get_file_info on a directory raises NotFound (line 632)."""
        sftp_backend.write("typedir/file.txt", b"x")
        with pytest.raises(NotFound):
            sftp_backend.get_file_info("typedir")

    def test_get_folder_info_on_file(self, sftp_backend: Backend) -> None:
        """get_folder_info on a file raises NotFound (line 645)."""
        sftp_backend.write("typefile.txt", b"x")
        with pytest.raises(NotFound):
            sftp_backend.get_folder_info("typefile.txt")

    def test_delete_folder_on_file(self, sftp_backend: Backend) -> None:
        """delete_folder on a file raises NotFound (line 544)."""
        sftp_backend.write("notadir.txt", b"x")
        with pytest.raises(NotFound):
            sftp_backend.delete_folder("notadir.txt")


class TestSFTPWriteAtomicStream:
    """BK-005: write_atomic with BinaryIO content (line 509)."""

    def test_write_atomic_stream_content(self, sftp_backend: Backend) -> None:
        sftp_backend.write_atomic("stream_atomic.txt", io.BytesIO(b"streamed atomic"))
        assert sftp_backend.read_bytes("stream_atomic.txt") == b"streamed atomic"

    def test_write_atomic_stream_content_overwrite(self, sftp_backend: Backend) -> None:
        sftp_backend.write_atomic("sa_ow.txt", b"first")
        sftp_backend.write_atomic("sa_ow.txt", io.BytesIO(b"second stream"), overwrite=True)
        assert sftp_backend.read_bytes("sa_ow.txt") == b"second stream"


class TestSFTPWriteAtomicCleanup:
    """BK-005: write_atomic failure cleans up temp file (lines 517-521)."""

    def test_write_atomic_cleanup_on_failure(self, sftp_backend: Backend) -> None:
        """Temp file is cleaned up when write_atomic fails mid-write.

        Uses a stream whose read() raises *after* the temp file has been
        opened on the server, so the except block (lines 517-521) must
        actually remove a real temp file.
        """

        class FailingStream(io.BytesIO):
            """Stream that raises on read — simulates I/O failure after temp file is opened."""

            def read(self, size: int = -1) -> bytes:
                raise OSError(errno.EIO, "Disk full")

        with pytest.raises(RemoteStoreError):
            sftp_backend.write_atomic("fail_atomic.txt", FailingStream())

        # Verify no temp files remain — the except block (lines 517-521) must
        # have removed the temp file that was created by file(tmp_path, "w")
        files = list(sftp_backend.list_files(""))
        temp_files = [f for f in files if f.name.startswith(".~tmp.")]
        assert temp_files == []


class TestSFTPCollectFolderStats:
    """BK-005: _collect_folder_stats recursive subdirectory (lines 675-680)."""

    def test_folder_info_nested_subdirectories(self, sftp_backend: Backend) -> None:
        """get_folder_info counts files in nested subdirectories."""
        sftp_backend.write("nested/a.txt", b"aaa")
        sftp_backend.write("nested/sub1/b.txt", b"bb")
        sftp_backend.write("nested/sub1/sub2/c.txt", b"c")
        fi = sftp_backend.get_folder_info("nested")
        assert fi.file_count == 3
        assert fi.total_size == 6
        assert fi.modified_at is not None


class TestSFTPNonEnoentOSErrors:
    """BK-005: non-ENOENT OSError re-raises via mock (lines 480, 497, 550, 630, 643, 698, 707, 737, 746)."""

    def _stat_eio_on_path(self, sftp_backend: SFTPBackend, target_suffix: str) -> object:
        """Return a stat replacement that raises EIO only for a specific file path."""
        original_stat = sftp_backend._sftp_client.stat

        def selective_stat(path: str) -> object:
            if path.endswith(target_suffix):
                raise OSError(errno.EIO, "I/O error")
            return original_stat(path)

        return selective_stat

    @pytest.mark.parametrize(
        ("setup_file", "target_suffix", "method", "args"),
        [
            pytest.param(None, "w_eio.txt", "write", ("w_eio.txt", b"data"), id="write"),
            pytest.param(None, "wa_eio.txt", "write_atomic", ("wa_eio.txt", b"data"), id="write-atomic"),
            pytest.param(None, "df_eio", "delete_folder", ("df_eio",), id="delete-folder"),
            pytest.param(None, "gfi_eio.txt", "get_file_info", ("gfi_eio.txt",), id="get-file-info"),
            pytest.param(None, "gfoi_eio", "get_folder_info", ("gfoi_eio",), id="get-folder-info"),
            pytest.param(None, "m_src_eio.txt", "move", ("m_src_eio.txt", "m_dst.txt"), id="move-src"),
            pytest.param("m_src2.txt", "m_dst2.txt", "move", ("m_src2.txt", "m_dst2.txt"), id="move-dst"),
            pytest.param(None, "c_src_eio.txt", "copy", ("c_src_eio.txt", "c_dst.txt"), id="copy-src"),
            pytest.param("c_src2.txt", "c_dst2.txt", "copy", ("c_src2.txt", "c_dst2.txt"), id="copy-dst"),
        ],
    )
    def test_non_enoent_reraise(
        self,
        sftp_backend: Backend,
        setup_file: str | None,
        target_suffix: str,
        method: str,
        args: tuple[object, ...],
    ) -> None:
        assert isinstance(sftp_backend, SFTPBackend)
        if setup_file:
            sftp_backend.write(setup_file, b"data")
        else:
            sftp_backend.exists("warmup.txt")

        kwargs: dict[str, object] = {}
        if (
            method in ("write", "write_atomic", "move", "copy")
            and len(args) == 2
            and setup_file
            or method in ("write", "write_atomic")
            and not setup_file
        ):
            kwargs["overwrite"] = False

        with (
            patch.object(
                sftp_backend._sftp_client,
                "stat",
                side_effect=self._stat_eio_on_path(sftp_backend, target_suffix),
            ),
            pytest.raises(RemoteStoreError),
        ):
            getattr(sftp_backend, method)(*args, **kwargs)


class TestSFTPListingExceptions:
    """BK-005: generic exception wrapping in list_files/list_folders (lines 599-602, 614-617)."""

    @pytest.mark.parametrize(
        "list_method",
        [
            pytest.param("list_files", id="list-files"),
            pytest.param("list_folders", id="list-folders"),
        ],
    )
    def test_wraps_generic_exception(self, sftp_backend: Backend, list_method: str) -> None:
        """Non-RemoteStoreError during listing wraps to RemoteStoreError."""
        assert isinstance(sftp_backend, SFTPBackend)
        prefix = "lexc" if list_method == "list_files" else "lfexc/sub"
        sftp_backend.write(f"{prefix}/a.txt", b"a")
        folder = "lexc" if list_method == "list_files" else "lfexc"

        original_listdir_attr = sftp_backend._sftp_client.listdir_attr

        def exploding_listdir(path: str) -> list[object]:
            original_listdir_attr(path)
            raise RuntimeError("boom")

        with (
            patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=exploding_listdir),
            pytest.raises(RemoteStoreError, match="boom"),
        ):
            list(getattr(sftp_backend, list_method)(folder))

    @pytest.mark.parametrize(
        "list_method",
        [
            pytest.param("list_files", id="list-files"),
            pytest.param("list_folders", id="list-folders"),
        ],
    )
    def test_reraises_remote_store_error(self, sftp_backend: Backend, list_method: str) -> None:
        """RemoteStoreError during listing is re-raised directly."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.exists("warmup.txt")

        with (
            patch.object(
                sftp_backend._sftp_client,
                "listdir_attr",
                side_effect=NotFound("injected", path="x", backend="sftp"),
            ),
            pytest.raises(NotFound, match="injected"),
        ):
            list(getattr(sftp_backend, list_method)("any"))


class TestSFTPDeleteFolderEdgeCases:
    """BK-005: delete_folder listdir OSError and _rmtree OSError (lines 558-559, 572-573)."""

    def test_delete_folder_non_recursive_listdir_oserror(self, sftp_backend: Backend) -> None:
        """Non-recursive delete_folder treats OSError on listdir as empty (lines 558-559)."""
        assert isinstance(sftp_backend, SFTPBackend)
        # Create an empty folder
        sftp_backend.write("df_oserr/tmp.txt", b"x")
        sftp_backend.delete("df_oserr/tmp.txt")

        def failing_listdir(path: str) -> None:
            raise OSError(errno.EIO, "I/O error on listdir")

        # With listdir failing, it assumes empty and tries rmdir — should succeed
        with patch.object(sftp_backend._sftp_client, "listdir", side_effect=failing_listdir):
            sftp_backend.delete_folder("df_oserr", recursive=False)

        assert sftp_backend.is_folder("df_oserr") is False

    def test_rmtree_listdir_attr_oserror(self, sftp_backend: Backend) -> None:
        """_rmtree handles OSError on listdir_attr gracefully (lines 572-573)."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("rmtree_oserr/a.txt", b"a")

        def failing_listdir_attr(path: str) -> None:
            raise OSError(errno.EIO, "I/O error on listdir_attr")

        # _rmtree returns early on OSError — folder is NOT deleted
        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=failing_listdir_attr):
            sftp_backend._rmtree(sftp_backend._sftp_path("rmtree_oserr"))

        # Folder still exists because _rmtree bailed out
        assert sftp_backend.is_folder("rmtree_oserr") is True


class TestSFTPCollectFolderStatsOSError:
    """BK-005: _collect_folder_stats OSError on listdir_attr (lines 664-665)."""

    def test_collect_folder_stats_listdir_oserror(self, sftp_backend: Backend) -> None:
        """_collect_folder_stats returns zeros when listdir_attr fails."""
        assert isinstance(sftp_backend, SFTPBackend)
        sftp_backend.write("cfs_oserr/a.txt", b"a")

        def failing_listdir_attr(path: str) -> None:
            raise OSError(errno.EIO, "I/O error")

        with patch.object(sftp_backend._sftp_client, "listdir_attr", side_effect=failing_listdir_attr):
            count, size, latest = sftp_backend._collect_folder_stats(sftp_backend._sftp_path("cfs_oserr"))

        assert count == 0
        assert size == 0
        assert latest is None


# endregion

# region: TOFU persistence (SFTP-028)


class TestSFTPTofuPersistence:
    """SFTP-028: TOFU host key persistence to disk."""

    @pytest.mark.spec("SFTP-028")
    def test_tofu_creates_and_persists_key(self, sftp_server: tuple[int, str]) -> None:
        """TOFU creates known_hosts file and persists the accepted key."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            assert not os.path.isfile(keys_path)
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            backend.close()
            assert os.path.isfile(keys_path)
            assert os.path.getsize(keys_path) > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_persisted_key_verifiable_by_strict(self, sftp_server: tuple[int, str]) -> None:
        """After TOFU persists a key, a STRICT backend can connect using the same file."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            # First connection: TOFU accepts and persists the key
            tofu_backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            tofu_backend.exists("nonexistent.txt")
            tofu_backend.close()

            # Second connection: STRICT should succeed with the persisted key
            strict_backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.STRICT,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            strict_backend.exists("nonexistent.txt")
            strict_backend.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_creates_parent_directories(self, sftp_server: tuple[int, str]) -> None:
        """TOFU creates nested parent directories for the known_hosts file."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "a", "b", "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            backend.close()
            assert os.path.isfile(keys_path)
            assert os.path.isdir(os.path.join(tmpdir, "a", "b"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_reconnect_preserves_keys(self, sftp_server: tuple[int, str]) -> None:
        """Keys survive the close-then-reconnect cycle within one backend lifetime."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            # First operation triggers connection and TOFU key acceptance
            backend.exists("nonexistent.txt")
            # Force disconnect (saves keys) then reconnect (loads them back)
            backend._close_clients()
            backend.exists("nonexistent.txt")
            backend.close()

            # Verify the file still has the persisted key
            assert os.path.isfile(keys_path)
            assert os.path.getsize(keys_path) > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_inline_keys_not_persisted(self, sftp_server: tuple[int, str]) -> None:
        """Inline known_host_keys with TOFU policy do not trigger file persistence."""
        port, host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                known_host_keys=host_key_entry,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            assert backend._tofu_keys_path is None
            backend.close()
            # known_hosts file should not have been created by TOFU persistence
            # (it may exist as an empty file from _ensure, but _tofu_keys_path is None
            # so save_host_keys was never called)
            if os.path.isfile(keys_path):
                assert os.path.getsize(keys_path) == 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.spec("SFTP-028")
    def test_tofu_save_failure_suppressed(self, sftp_server: tuple[int, str]) -> None:
        """Save failure during close does not raise."""
        port, _host_key_entry = sftp_server
        tmpdir = tempfile.mkdtemp(prefix="tofu_test_")
        keys_path = os.path.join(tmpdir, "known_hosts")
        try:
            backend = SFTPBackend(
                host="127.0.0.1",
                port=port,
                username="testuser",
                password="testpass",
                base_path="/",
                host_key_policy=HostKeyPolicy.TRUST_ON_FIRST_USE,
                host_keys_path=keys_path,
                connect_kwargs={"allow_agent": False, "look_for_keys": False},
            )
            backend.exists("nonexistent.txt")
            # Point _tofu_keys_path to a non-writable location to force save failure
            backend._tofu_keys_path = os.path.join(tmpdir, "readonly", "known_hosts")
            os.makedirs(os.path.join(tmpdir, "readonly"), exist_ok=True)
            # Make directory read-only (best-effort on Windows)
            os.chmod(os.path.join(tmpdir, "readonly"), 0o555)
            # close() should not raise despite save failure
            backend.close()
        finally:
            # Restore write permissions for cleanup
            with contextlib.suppress(Exception):
                os.chmod(os.path.join(tmpdir, "readonly"), 0o755)
            shutil.rmtree(tmpdir, ignore_errors=True)


# endregion
