"""SFTP backend tests -- covers SFTP-xxx spec items.

Requires: paramiko, tenacity (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

# Guard: skip entire module if dependencies are missing
paramiko = pytest.importorskip("paramiko", reason="paramiko not installed")
pytest.importorskip("tenacity", reason="tenacity not installed")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    CapabilityNotSupported,
    NotFound,
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
    def test_declares_capabilities_except_glob(self, sftp_backend: Backend) -> None:
        caps = sftp_backend.capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            if cap is Capability.GLOB:
                assert not caps.supports(cap), "SFTP should NOT support GLOB"
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
    def test_empty_host_raises(self) -> None:
        with pytest.raises(ValueError, match="host"):
            SFTPBackend(host="")

    @pytest.mark.spec("SFTP-005")
    def test_whitespace_host_raises(self) -> None:
        with pytest.raises(ValueError, match="host"):
            SFTPBackend(host="   ")


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
        with pytest.raises(RemoteStoreError):
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

    @pytest.mark.spec("SFTP-018")
    def test_move_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.move("missing.txt", "dst.txt")

    @pytest.mark.spec("SFTP-018")
    def test_move_already_exists(self, sftp_backend: Backend) -> None:
        sftp_backend.write("m1.txt", b"a")
        sftp_backend.write("m2.txt", b"b")
        with pytest.raises(AlreadyExists):
            sftp_backend.move("m1.txt", "m2.txt", overwrite=False)

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
    def test_copy_not_found(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.copy("missing.txt", "dst.txt")

    @pytest.mark.spec("SFTP-019")
    def test_copy_already_exists(self, sftp_backend: Backend) -> None:
        sftp_backend.write("c1.txt", b"a")
        sftp_backend.write("c2.txt", b"b")
        with pytest.raises(AlreadyExists):
            sftp_backend.copy("c1.txt", "c2.txt", overwrite=False)

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

    def test_read_content_bytes(self) -> None:
        """_read_content with bytes returns bytes directly."""
        assert SFTPBackend._read_content(b"hello") == b"hello"

    def test_read_content_binaryio(self) -> None:
        """_read_content with BinaryIO returns read bytes."""
        import io

        assert SFTPBackend._read_content(io.BytesIO(b"stream")) == b"stream"

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
        folders = set(sftp_backend.list_folders("lf"))
        assert folders == {"sub1", "sub2"}

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

    def test_exists_file(self, sftp_backend: Backend) -> None:
        sftp_backend.write("e.txt", b"x")
        assert sftp_backend.exists("e.txt") is True

    def test_exists_missing(self, sftp_backend: Backend) -> None:
        assert sftp_backend.exists("nope.txt") is False

    def test_is_file(self, sftp_backend: Backend) -> None:
        sftp_backend.write("f.txt", b"x")
        assert sftp_backend.is_file("f.txt") is True
        assert sftp_backend.is_file("missing.txt") is False

    def test_is_file_not_folder(self, sftp_backend: Backend) -> None:
        sftp_backend.write("dir/f.txt", b"x")
        assert sftp_backend.is_file("dir") is False


class TestSFTPDelete:
    """Delete operations."""

    def test_delete_file(self, sftp_backend: Backend) -> None:
        sftp_backend.write("del.txt", b"x")
        sftp_backend.delete("del.txt")
        assert sftp_backend.exists("del.txt") is False

    def test_delete_missing_ok(self, sftp_backend: Backend) -> None:
        sftp_backend.delete("nope.txt", missing_ok=True)

    def test_delete_missing_raises(self, sftp_backend: Backend) -> None:
        with pytest.raises(NotFound):
            sftp_backend.delete("nope.txt")


# endregion
