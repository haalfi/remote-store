"""S3 backend tests -- covers S3-xxx spec items.

Requires: moto[server,s3], s3fs, boto3 (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("moto", reason="moto not installed")
pytest.importorskip("s3fs", reason="s3fs not installed")
boto3 = pytest.importorskip("boto3", reason="boto3 not installed")

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
from remote_store._models import FileInfo, FolderInfo, WriteResult  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from remote_store._backend import Backend

REGION = "us-east-1"


@pytest.fixture
def s3_backend(moto_server: str) -> Iterator[Backend]:
    """Create an S3Backend against moto's mock S3 service."""
    bucket = f"test-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name=REGION,
    )
    client.create_bucket(Bucket=bucket)

    from remote_store.backends._s3 import S3Backend

    backend = S3Backend(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name=REGION,
        endpoint_url=moto_server,
    )
    yield backend
    backend.close()


# region: Construction (S3-001 through S3-005)
class TestS3Construction:
    """S3-001 through S3-005: construction and identity."""

    @pytest.mark.spec("S3-001")
    def test_constructor_minimal(self, s3_backend: Backend) -> None:
        """Backend can be constructed with bucket and credentials."""
        assert s3_backend is not None

    @pytest.mark.spec("S3-002")
    def test_name_is_s3(self, s3_backend: Backend) -> None:
        assert s3_backend.name == "s3"

    @pytest.mark.spec("S3-003")
    def test_declares_all_capabilities(self, s3_backend: Backend) -> None:
        caps = s3_backend.capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            if cap is Capability.ATOMIC_MOVE:
                assert not caps.supports(cap), "S3 must not declare ATOMIC_MOVE (copy-then-delete)"
            else:
                assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("S3-004")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(
            bucket="any-bucket",
            endpoint_url="http://localhost:99999",
            key="k",
            secret="s",
        )
        assert backend.name == "s3"

    @pytest.mark.spec("S3-005")
    @pytest.mark.parametrize(
        "bucket",
        [
            pytest.param("", id="empty"),
            pytest.param("   ", id="whitespace"),
        ],
    )
    def test_invalid_bucket_raises(self, bucket: str) -> None:
        from remote_store.backends._s3 import S3Backend

        with pytest.raises(ValueError, match="bucket"):
            S3Backend(bucket=bucket)

    @pytest.mark.spec("S3-025")
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param(None, None, id="none"),
            pytest.param("", None, id="empty"),
            pytest.param("   ", None, id="whitespace"),
            pytest.param("localhost:9000", "https://localhost:9000", id="bare-host-port"),
            pytest.param("my-host.example.com:443", "https://my-host.example.com:443", id="fqdn-port"),
            pytest.param("http://localhost:9000", "http://localhost:9000", id="http-scheme"),
            pytest.param("https://s3.amazonaws.com", "https://s3.amazonaws.com", id="https-scheme"),
            pytest.param("  http://x:9000  ", "http://x:9000", id="whitespace-stripped"),
            pytest.param("HTTP://host:9000", "HTTP://host:9000", id="uppercase-http"),
            pytest.param("HTTPS://host:9000", "HTTPS://host:9000", id="uppercase-https"),
        ],
    )
    def test_endpoint_url_normalization(self, raw: str | None, expected: str | None) -> None:
        """Bare host:port is auto-prefixed with https://."""
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(bucket="b", key="k", secret="s", endpoint_url=raw)
        assert backend._endpoint_url == expected

    @pytest.mark.spec("S3-021")
    def test_client_options_accepted(self) -> None:
        """client_options are accepted without error at construction."""
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(
            bucket="any-bucket",
            key="k",
            secret="s",
            client_options={"connect_timeout": 5, "read_timeout": 10},
        )
        assert backend.name == "s3"

    @pytest.mark.spec("S3-021")
    def test_client_options_not_mutated(self) -> None:
        """client_options nested dicts must not be mutated by lazy init."""
        from remote_store.backends._s3 import S3Backend

        opts: dict = {"client_kwargs": {"timeout": 30}}
        original_inner = dict(opts["client_kwargs"])  # snapshot
        backend = S3Backend(
            bucket="any-bucket",
            key="k",
            secret="s",
            region_name="us-east-1",
            client_options=opts,
        )
        with patch("s3fs.S3FileSystem"):
            _ = backend._fs
        assert opts["client_kwargs"] == original_inner

    @pytest.mark.spec("S3-022")
    def test_credentials_optional(self) -> None:
        """Backend can be constructed without explicit credentials."""
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(bucket="any-bucket")
        assert backend.name == "s3"


class TestS3TlsCaBundle:
    """TLS-001, TLS-004, TLS-005: tls_ca_bundle on S3Backend."""

    @pytest.mark.spec("TLS-001")
    def test_tls_ca_bundle_accepted(self, tmp_path: Path) -> None:
        from remote_store.backends._s3 import S3Backend

        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = S3Backend(bucket="b", key="k", secret="s", tls_ca_bundle=str(cert))
        assert backend._tls_ca_bundle == str(cert)

    @pytest.mark.spec("TLS-004")
    def test_tls_ca_bundle_missing_file_raises(self) -> None:
        from remote_store.backends._s3 import S3Backend

        with pytest.raises(ValueError, match="does not exist or is not a file"):
            S3Backend(bucket="b", key="k", secret="s", tls_ca_bundle="/no/such/file.pem")

    @pytest.mark.spec("TLS-004")
    def test_tls_ca_bundle_directory_raises(self, tmp_path: Path) -> None:
        from remote_store.backends._s3 import S3Backend

        with pytest.raises(ValueError, match="does not exist or is not a file"):
            S3Backend(bucket="b", key="k", secret="s", tls_ca_bundle=str(tmp_path))

    @pytest.mark.spec("TLS-004")
    def test_tls_ca_bundle_env_var_missing_file_raises(self, tmp_path: Path) -> None:
        from remote_store.backends._s3 import S3Backend

        with (
            patch.dict("os.environ", {"AWS_CA_BUNDLE": "/no/such/env.pem"}, clear=False),
            pytest.raises(ValueError, match="does not exist or is not a file"),
        ):
            S3Backend(bucket="b", key="k", secret="s")

    @pytest.mark.spec("TLS-001")
    def test_tls_ca_bundle_none_default(self) -> None:
        from remote_store.backends._s3 import S3Backend
        from remote_store.backends._s3_base import _S3_CA_ENV_VARS

        with patch.dict("os.environ", {v: "" for v in _S3_CA_ENV_VARS}, clear=False):
            backend = S3Backend(bucket="b", key="k", secret="s")
        assert backend._tls_ca_bundle is None

    @pytest.mark.spec("TLS-005")
    def test_tls_ca_bundle_sets_verify_on_s3fs(self, tmp_path: Path) -> None:
        from remote_store.backends._s3 import S3Backend

        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = S3Backend(bucket="b", key="k", secret="s", tls_ca_bundle=str(cert))
        with patch("s3fs.S3FileSystem") as mock_s3fs_cls:
            _ = backend._fs
            call_kwargs = mock_s3fs_cls.call_args[1]
            assert call_kwargs["client_kwargs"]["verify"] == str(cert)

    @pytest.mark.spec("TLS-005")
    def test_tls_ca_bundle_does_not_override_explicit_verify(self, tmp_path: Path) -> None:
        from remote_store.backends._s3 import S3Backend

        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        backend = S3Backend(
            bucket="b",
            key="k",
            secret="s",
            tls_ca_bundle=str(cert),
            client_options={"client_kwargs": {"verify": "/other/ca.pem"}},
        )
        with patch("s3fs.S3FileSystem") as mock_s3fs_cls:
            _ = backend._fs
            call_kwargs = mock_s3fs_cls.call_args[1]
            assert call_kwargs["client_kwargs"]["verify"] == "/other/ca.pem"


# endregion


# region: S3 Object Model (S3-006 through S3-009)
class TestS3FolderSemantics:
    """S3-006 through S3-009: virtual folder behavior."""

    @pytest.mark.spec("S3-007")
    @pytest.mark.parametrize(
        ("setup_path", "folder", "expected"),
        [
            pytest.param("data/file.txt", "data", True, id="with_objects"),
            pytest.param(None, "nonexistent", False, id="empty_prefix"),
        ],
    )
    def test_is_folder_simple(self, s3_backend: Backend, setup_path: str | None, folder: str, expected: bool) -> None:
        if setup_path:
            s3_backend.write(setup_path, b"x")
        assert s3_backend.is_folder(folder) is expected

    @pytest.mark.spec("S3-007")
    def test_is_folder_nested(self, s3_backend: Backend) -> None:
        s3_backend.write("a/b/c.txt", b"x")
        assert s3_backend.is_folder("a") is True
        assert s3_backend.is_folder("a/b") is True
        assert s3_backend.is_folder("a/b/c") is False

    @pytest.mark.spec("S3-008")
    def test_write_does_not_create_folder_markers(self, s3_backend: Backend) -> None:
        """Writing a nested file must not create folder marker objects."""
        s3_backend.write("x/y/z.txt", b"data")
        assert s3_backend.is_file("x/y/z.txt") is True
        assert s3_backend.is_file("x/") is False
        assert s3_backend.is_file("x/y/") is False

    @pytest.mark.spec("S3-009")
    def test_folder_vanishes_when_empty(self, s3_backend: Backend) -> None:
        """Deleting last file under a prefix makes folder disappear."""
        s3_backend.write("ephemeral/only.txt", b"x")
        assert s3_backend.is_folder("ephemeral") is True
        s3_backend.delete("ephemeral/only.txt")
        assert s3_backend.is_folder("ephemeral") is False

    @pytest.mark.spec("S3-009")
    def test_folder_persists_with_remaining_files(self, s3_backend: Backend) -> None:
        s3_backend.write("keep/a.txt", b"a")
        s3_backend.write("keep/b.txt", b"b")
        s3_backend.delete("keep/a.txt")
        assert s3_backend.is_folder("keep") is True


# endregion


# region: Operations (S3-010 through S3-014)
class TestS3Operations:
    """S3-010 through S3-014: write_atomic, delete_folder, move, copy."""

    # -- write_atomic (S3-010) --

    @pytest.mark.spec("S3-010")
    def test_write_atomic_creates_file(self, s3_backend: Backend) -> None:
        s3_backend.write_atomic("atomic.txt", b"atomic content")
        assert s3_backend.read_bytes("atomic.txt") == b"atomic content"

    @pytest.mark.spec("S3-010")
    def test_write_atomic_overwrite(self, s3_backend: Backend) -> None:
        s3_backend.write_atomic("at.txt", b"first")
        s3_backend.write_atomic("at.txt", b"second", overwrite=True)
        assert s3_backend.read_bytes("at.txt") == b"second"

    @pytest.mark.spec("S3-010")
    def test_write_atomic_already_exists(self, s3_backend: Backend) -> None:
        s3_backend.write_atomic("at2.txt", b"first")
        with pytest.raises(AlreadyExists):
            s3_backend.write_atomic("at2.txt", b"second", overwrite=False)

    # -- delete_folder (S3-011, S3-012) --

    @pytest.mark.spec("S3-011")
    def test_delete_folder_recursive(self, s3_backend: Backend) -> None:
        s3_backend.write("rf/a.txt", b"a")
        s3_backend.write("rf/sub/b.txt", b"b")
        s3_backend.delete_folder("rf", recursive=True)
        assert s3_backend.exists("rf/a.txt") is False
        assert s3_backend.exists("rf/sub/b.txt") is False
        assert s3_backend.is_folder("rf") is False

    @pytest.mark.spec("S3-011")
    def test_delete_folder_recursive_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.delete_folder("ghost", recursive=True)

    @pytest.mark.spec("S3-011")
    def test_delete_folder_recursive_missing_ok(self, s3_backend: Backend) -> None:
        result = s3_backend.delete_folder("ghost", recursive=True, missing_ok=True)
        assert result is None

    @pytest.mark.spec("S3-012")
    def test_delete_folder_non_recursive_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.delete_folder("empty", recursive=False)

    @pytest.mark.spec("S3-012")
    def test_delete_folder_non_recursive_non_empty(self, s3_backend: Backend) -> None:
        s3_backend.write("nonempty/file.txt", b"x")
        with pytest.raises(DirectoryNotEmpty):
            s3_backend.delete_folder("nonempty", recursive=False)

    # -- move/copy error variants (S3-013, S3-014) --

    @pytest.mark.spec("S3-013")
    def test_move(self, s3_backend: Backend) -> None:
        s3_backend.write("src.txt", b"data")
        s3_backend.move("src.txt", "dst.txt")
        assert s3_backend.exists("src.txt") is False
        assert s3_backend.read_bytes("dst.txt") == b"data"

    @pytest.mark.spec("S3-013")
    def test_move_overwrite(self, s3_backend: Backend) -> None:
        s3_backend.write("mo1.txt", b"a")
        s3_backend.write("mo2.txt", b"b")
        s3_backend.move("mo1.txt", "mo2.txt", overwrite=True)
        assert s3_backend.read_bytes("mo2.txt") == b"a"
        assert s3_backend.exists("mo1.txt") is False

    @pytest.mark.spec("S3-014")
    def test_copy(self, s3_backend: Backend) -> None:
        s3_backend.write("orig.txt", b"data")
        s3_backend.copy("orig.txt", "clone.txt")
        assert s3_backend.read_bytes("orig.txt") == b"data"
        assert s3_backend.read_bytes("clone.txt") == b"data"

    @pytest.mark.spec("S3-014")
    def test_copy_overwrite(self, s3_backend: Backend) -> None:
        s3_backend.write("co1.txt", b"a")
        s3_backend.write("co2.txt", b"b")
        s3_backend.copy("co1.txt", "co2.txt", overwrite=True)
        assert s3_backend.read_bytes("co2.txt") == b"a"
        assert s3_backend.read_bytes("co1.txt") == b"a"

    @pytest.mark.spec("S3-013")
    def test_move_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.move("missing.txt", "dst.txt")

    @pytest.mark.spec("S3-014")
    def test_copy_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.copy("missing.txt", "dst.txt")

    @pytest.mark.spec("S3-013")
    def test_move_already_exists(self, s3_backend: Backend) -> None:
        s3_backend.write("ae1.txt", b"a")
        s3_backend.write("ae2.txt", b"b")
        with pytest.raises(AlreadyExists):
            s3_backend.move("ae1.txt", "ae2.txt", overwrite=False)

    @pytest.mark.spec("S3-014")
    def test_copy_already_exists(self, s3_backend: Backend) -> None:
        s3_backend.write("ae1.txt", b"a")
        s3_backend.write("ae2.txt", b"b")
        with pytest.raises(AlreadyExists):
            s3_backend.copy("ae1.txt", "ae2.txt", overwrite=False)


# endregion


# region: Error Mapping (S3-015 through S3-018)
class TestS3ErrorMapping:
    """S3-015 through S3-018: error mapping."""

    @pytest.mark.spec("S3-015")
    @pytest.mark.parametrize(
        ("method", "args"),
        [
            pytest.param("read_bytes", ("does-not-exist.txt",), id="read_missing"),
            pytest.param("get_file_info", ("nope.txt",), id="get_file_info_missing"),
            pytest.param("delete", ("nope.txt",), id="delete_missing"),
        ],
    )
    def test_missing_key_maps_to_not_found(self, s3_backend: Backend, method: str, args: tuple[str, ...]) -> None:
        with pytest.raises(NotFound):
            getattr(s3_backend, method)(*args)

    @pytest.mark.spec("S3-015")
    def test_not_found_has_backend_attr(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound) as exc_info:
            s3_backend.read_bytes("does-not-exist.txt")
        assert exc_info.value.backend == "s3"

    @pytest.mark.spec("S3-016")
    @pytest.mark.parametrize(
        "message",
        [
            pytest.param("An error occurred (403) AccessDenied", id="http_403"),
            pytest.param("access denied for this resource", id="access_denied_msg"),
        ],
    )
    def test_permission_denied_mapping(self, s3_backend: Backend, message: str) -> None:
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        with (
            patch.object(s3_backend._fs, "cat_file", side_effect=Exception(message)),
            pytest.raises(PermissionDenied) as exc_info,
        ):
            s3_backend.read_bytes("secret.txt")
        assert exc_info.value.backend == "s3"
        assert exc_info.value.path == "secret.txt"

    @pytest.mark.spec("S3-017")
    @pytest.mark.parametrize(
        "message",
        [
            pytest.param("Could not connect to the endpoint URL", id="endpoint"),
            pytest.param("connect timeout reached", id="timeout"),
            pytest.param("dns resolution failed", id="dns"),
            pytest.param("name or service not known", id="name_or_service"),
        ],
    )
    def test_backend_unavailable_mapping(self, s3_backend: Backend, message: str) -> None:
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        with (
            patch.object(s3_backend._fs, "cat_file", side_effect=Exception(message)),
            pytest.raises(BackendUnavailable) as exc_info,
        ):
            s3_backend.read_bytes("file.txt")
        assert exc_info.value.backend == "s3"

    @pytest.mark.spec("S3-018")
    def test_no_native_exception_leaks(self, s3_backend: Backend) -> None:
        """All errors must be RemoteStoreError subtypes."""
        with pytest.raises(RemoteStoreError):
            s3_backend.read("nonexistent.txt")

    @pytest.mark.spec("S3-018")
    def test_error_has_backend_attribute(self, s3_backend: Backend) -> None:
        with pytest.raises(RemoteStoreError) as exc_info:
            s3_backend.read("missing.txt")
        assert exc_info.value.backend == "s3"


# endregion


# region: Resource Management (S3-019, S3-020)
class TestS3Lifecycle:
    """S3-019, S3-020: close and unwrap."""

    @pytest.mark.spec("S3-019")
    def test_close_is_callable(self, s3_backend: Backend) -> None:
        result = s3_backend.close()
        assert result is None

    @pytest.mark.spec("S3-019")
    def test_close_idempotent(self, s3_backend: Backend) -> None:
        s3_backend.close()
        result = s3_backend.close()
        assert result is None

    @pytest.mark.spec("S3-020")
    def test_unwrap_s3fs(self, s3_backend: Backend) -> None:
        import s3fs

        fs = s3_backend.unwrap(s3fs.S3FileSystem)
        assert isinstance(fs, s3fs.S3FileSystem)

    @pytest.mark.spec("S3-020")
    def test_unwrap_wrong_type_raises(self, s3_backend: Backend) -> None:
        with pytest.raises(CapabilityNotSupported):
            s3_backend.unwrap(str)


# endregion


# region: Read/Write roundtrip
class TestS3ReadWrite:
    """Basic read/write roundtrip to verify full stack."""

    def test_write_and_read_bytes(self, s3_backend: Backend) -> None:
        s3_backend.write("hello.txt", b"hello world")
        assert s3_backend.read_bytes("hello.txt") == b"hello world"

    def test_write_and_read_stream(self, s3_backend: Backend) -> None:
        s3_backend.write("stream.bin", b"\x00\x01\x02\xff")
        stream = s3_backend.read("stream.bin")
        assert stream.read() == b"\x00\x01\x02\xff"

    def test_write_overwrite(self, s3_backend: Backend) -> None:
        s3_backend.write("ow.txt", b"first")
        s3_backend.write("ow.txt", b"second", overwrite=True)
        assert s3_backend.read_bytes("ow.txt") == b"second"

    def test_write_already_exists(self, s3_backend: Backend) -> None:
        s3_backend.write("ae.txt", b"first")
        with pytest.raises(AlreadyExists):
            s3_backend.write("ae.txt", b"second")

    def test_write_nested_path(self, s3_backend: Backend) -> None:
        s3_backend.write("a/b/c/deep.txt", b"deep")
        assert s3_backend.read_bytes("a/b/c/deep.txt") == b"deep"

    def test_write_from_binaryio(self, s3_backend: Backend) -> None:
        s3_backend.write("bio.txt", io.BytesIO(b"streamed"))
        assert s3_backend.read_bytes("bio.txt") == b"streamed"


# endregion


# region: Listing and Metadata
class TestS3Listing:
    """File and folder listing operations."""

    def test_list_files_non_recursive(self, s3_backend: Backend) -> None:
        s3_backend.write("lst/a.txt", b"a")
        s3_backend.write("lst/b.txt", b"b")
        s3_backend.write("lst/sub/c.txt", b"c")
        files = list(s3_backend.list_files("lst"))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    def test_list_files_recursive(self, s3_backend: Backend) -> None:
        s3_backend.write("lr/a.txt", b"a")
        s3_backend.write("lr/sub/b.txt", b"b")
        files = list(s3_backend.list_files("lr", recursive=True))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    def test_list_files_empty_folder(self, s3_backend: Backend) -> None:
        files = list(s3_backend.list_files("empty"))
        assert files == []

    def test_list_folders(self, s3_backend: Backend) -> None:
        s3_backend.write("lf/sub1/a.txt", b"a")
        s3_backend.write("lf/sub2/b.txt", b"b")
        s3_backend.write("lf/root.txt", b"r")
        folders = list(s3_backend.list_folders("lf"))
        assert {f.name for f in folders} == {"sub1", "sub2"}

    def test_list_folders_empty(self, s3_backend: Backend) -> None:
        folders = list(s3_backend.list_folders("empty"))
        assert folders == []

    @pytest.mark.spec("S3-003")
    def test_list_files_max_depth(self, s3_backend: Backend) -> None:
        """max_depth limits traversal depth natively."""
        s3_backend.write("md/a.txt", b"a")
        s3_backend.write("md/d1/b.txt", b"b")
        s3_backend.write("md/d1/d2/c.txt", b"c")
        # depth 0: files directly in md/
        files_d0 = list(s3_backend.list_files("md", recursive=True, max_depth=0))
        assert {f.name for f in files_d0} == {"a.txt"}
        # depth 1: md/ + md/d1/
        files_d1 = list(s3_backend.list_files("md", recursive=True, max_depth=1))
        assert {f.name for f in files_d1} == {"a.txt", "b.txt"}
        # depth 2: all
        files_d2 = list(s3_backend.list_files("md", recursive=True, max_depth=2))
        assert {f.name for f in files_d2} == {"a.txt", "b.txt", "c.txt"}


class TestS3Metadata:
    """File and folder metadata operations."""

    def test_get_file_info(self, s3_backend: Backend) -> None:
        s3_backend.write("info.txt", b"hello world")
        fi = s3_backend.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "info.txt"
        assert fi.size == 11
        assert fi.modified_at is not None

    def test_get_file_info_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.get_file_info("missing.txt")

    def test_get_folder_info(self, s3_backend: Backend) -> None:
        s3_backend.write("fi/a.txt", b"aaa")
        s3_backend.write("fi/b.txt", b"bb")
        fi = s3_backend.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    def test_get_folder_info_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.get_folder_info("nodir")

    @pytest.mark.parametrize(
        ("setup_path", "query", "expected"),
        [
            pytest.param("e.txt", "e.txt", True, id="exists_file"),
            pytest.param(None, "nope.txt", False, id="exists_missing"),
        ],
    )
    def test_exists(self, s3_backend: Backend, setup_path: str | None, query: str, expected: bool) -> None:
        if setup_path:
            s3_backend.write(setup_path, b"x")
        assert s3_backend.exists(query) is expected

    def test_is_file(self, s3_backend: Backend) -> None:
        s3_backend.write("f.txt", b"x")
        assert s3_backend.is_file("f.txt") is True
        assert s3_backend.is_file("missing.txt") is False

    def test_is_file_not_folder(self, s3_backend: Backend) -> None:
        s3_backend.write("dir/f.txt", b"x")
        assert s3_backend.is_file("dir") is False


class TestS3Delete:
    """Delete operations."""

    def test_delete_file(self, s3_backend: Backend) -> None:
        s3_backend.write("del.txt", b"x")
        s3_backend.delete("del.txt")
        assert s3_backend.exists("del.txt") is False

    def test_delete_missing_ok(self, s3_backend: Backend) -> None:
        result = s3_backend.delete("nope.txt", missing_ok=True)
        assert result is None

    def test_delete_missing_raises(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.delete("nope.txt")


# endregion


# region: ETag and Digest (S3-023, S3-024)
class TestS3ETagAndDigest:
    """S3-023, S3-024: ETag and ContentDigest in FileInfo."""

    @pytest.mark.spec("S3-023")
    def test_get_file_info_has_etag(self, s3_backend: Backend) -> None:
        s3_backend.write("etag.txt", b"hello")
        fi = s3_backend.get_file_info("etag.txt")
        assert fi.etag is not None
        assert isinstance(fi.etag, str)
        assert '"' not in fi.etag
        assert fi.etag == fi.etag.lower()

    @pytest.mark.spec("S3-023")
    def test_list_files_has_etag(self, s3_backend: Backend) -> None:
        s3_backend.write("etag_list.txt", b"hello")
        files = list(s3_backend.list_files(""))
        matches = [f for f in files if f.name == "etag_list.txt"]
        assert len(matches) == 1
        assert matches[0].etag is not None
        assert '"' not in matches[0].etag
        assert matches[0].etag == matches[0].etag.lower()

    @pytest.mark.spec("S3-023")
    def test_digest_type_for_standard_upload(self, s3_backend: Backend) -> None:
        """S3 automatically computes CRC32 for standard uploads."""
        from remote_store._models import ContentDigest

        s3_backend.write("no_explicit_checksum.txt", b"hello")
        fi = s3_backend.get_file_info("no_explicit_checksum.txt")
        assert fi.digest is not None
        assert isinstance(fi.digest, ContentDigest)
        assert fi.digest.algorithm == "crc32"

    @pytest.mark.spec("S3-023")
    @pytest.mark.parametrize(
        ("info_dict", "expected_etag"),
        [
            pytest.param(
                {"etag": '"abc123"', "size": 10},
                "abc123",
                id="lowercase_key_fallback",
            ),
            pytest.param(
                {"ETag": '"d41d8cd98f00b204e9800998ecf8427e-2"', "size": 100},
                "d41d8cd98f00b204e9800998ecf8427e-2",
                id="multipart_suffix_preserved",
            ),
            pytest.param(
                {"size": 5},
                None,
                id="etag_none_when_absent",
            ),
        ],
    )
    def test_info_to_fileinfo_etag(self, info_dict: dict, expected_etag: str | None) -> None:
        """_info_to_fileinfo handles various ETag key forms correctly."""
        from datetime import datetime, timezone

        from remote_store.backends._s3 import S3Backend

        backend = object.__new__(S3Backend)
        info_dict.setdefault("LastModified", datetime(2024, 1, 1, tzinfo=timezone.utc))
        info_dict.setdefault("name", "bucket/file.txt")
        fi = backend._info_to_fileinfo(info_dict, "file.txt")
        assert fi.etag == expected_etag

    @pytest.mark.spec("S3-024")
    def test_get_file_info_digest_sha256(self, s3_backend: Backend, moto_server: str) -> None:
        """get_file_info returns ContentDigest when object uploaded with SHA256."""
        import base64
        import hashlib

        import boto3

        from remote_store._models import ContentDigest
        from remote_store.backends._s3 import S3Backend

        content = b"hello checksum"
        expected_hex = hashlib.sha256(content).hexdigest()
        b64 = base64.b64encode(hashlib.sha256(content).digest()).decode()

        backend = s3_backend
        assert isinstance(backend, S3Backend)
        raw_client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name=REGION,
        )
        raw_client.put_object(
            Bucket=backend._bucket,
            Key="sha256_file.txt",
            Body=content,
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=b64,
        )

        fi = backend.get_file_info("sha256_file.txt")
        assert fi.digest is not None
        assert isinstance(fi.digest, ContentDigest)
        assert fi.digest.algorithm == "sha256"
        assert fi.digest.value == expected_hex

    @pytest.mark.spec("S3-024")
    def test_digest_from_head_response_no_algorithm(self) -> None:
        """Returns None when no known checksum keys are present."""
        from remote_store.backends._s3 import S3Backend

        backend = object.__new__(S3Backend)
        raw = {"ContentLength": 5, "ETag": '"abc"'}
        assert backend._digest_from_head_response(raw) is None

    @pytest.mark.spec("S3-024")
    def test_list_files_digest_always_none(self, s3_backend: Backend, moto_server: str) -> None:
        """Listing paths never populate digest."""
        import base64
        import hashlib

        import boto3

        from remote_store.backends._s3 import S3Backend

        content = b"listed"
        b64 = base64.b64encode(hashlib.sha256(content).digest()).decode()
        backend = s3_backend
        assert isinstance(backend, S3Backend)
        raw_client = boto3.client(
            "s3",
            endpoint_url=moto_server,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name=REGION,
        )
        raw_client.put_object(
            Bucket=backend._bucket,
            Key="listed_sha256.txt",
            Body=content,
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=b64,
        )

        files = list(backend.list_files(""))
        matches = [f for f in files if f.name == "listed_sha256.txt"]
        assert len(matches) == 1
        assert matches[0].digest is None

    @pytest.mark.spec("S3-024")
    def test_digest_from_head_response_sha256(self) -> None:
        """_digest_from_head_response returns ContentDigest for SHA256."""
        import base64
        import hashlib

        from remote_store._models import ContentDigest
        from remote_store.backends._s3 import S3Backend

        content = b"test"
        b64 = base64.b64encode(hashlib.sha256(content).digest()).decode()
        backend = object.__new__(S3Backend)
        raw = {"ContentLength": 4, "ChecksumSHA256": b64}
        result = backend._digest_from_head_response(raw)
        assert isinstance(result, ContentDigest)
        assert result.algorithm == "sha256"
        assert result.value == hashlib.sha256(content).hexdigest()


# endregion


# region: Glob (GLOB-018)
class TestS3Glob:
    """GLOB-018: S3Backend native glob via prefix-optimized listing."""

    def _populate(self, backend: Backend) -> None:
        backend.write("report.csv", b"r1")
        backend.write("report.txt", b"r2")
        backend.write("data/sales.csv", b"d1")
        backend.write("data/sub/deep.csv", b"d2")
        backend.write("logs/app.log", b"l1")
        backend.write("logs/archive/old.log", b"l2")
        backend.write("file1.txt", b"f1")
        backend.write("file2.txt", b"f2")

    @pytest.mark.spec("GLOB-018")
    @pytest.mark.parametrize(
        ("pattern", "expected"),
        [
            pytest.param("*.csv", ["report.csv"], id="star_csv"),
            pytest.param("**/*.log", ["logs/app.log", "logs/archive/old.log"], id="recursive"),
            pytest.param("data/*.csv", ["data/sales.csv"], id="subdirectory"),
            pytest.param("*.xyz", [], id="no_matches"),
            pytest.param("file?.txt", ["file1.txt", "file2.txt"], id="question_mark"),
        ],
    )
    def test_glob_pattern(self, s3_backend: Backend, pattern: str, expected: list[str]) -> None:
        self._populate(s3_backend)
        results = sorted(str(f.path) for f in s3_backend.glob(pattern))
        assert results == expected

    @pytest.mark.spec("GLOB-018")
    def test_glob_files_only(self, s3_backend: Backend) -> None:
        self._populate(s3_backend)
        for info in s3_backend.glob("**/*"):
            assert isinstance(info, FileInfo)


# endregion


# region: Paginated Listing (BK-123 H-1/H-2)
class TestS3PaginatedListing:
    """BK-123 H-1/H-2: recursive listing uses BFS via ls() instead of s3fs.find()."""

    @pytest.mark.spec("BK-123")
    def test_list_files_recursive_nested_dirs(self, s3_backend: Backend) -> None:
        """list_files(recursive=True) returns files across nested directories."""
        s3_backend.write("a/1.txt", b"one")
        s3_backend.write("a/b/2.txt", b"two")
        s3_backend.write("a/b/c/3.txt", b"three")
        files = list(s3_backend.list_files("a", recursive=True))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt", "3.txt"}
        # Verify paths are fully qualified relative keys
        paths = {str(f.path) for f in files}
        assert "a/1.txt" in paths
        assert "a/b/2.txt" in paths
        assert "a/b/c/3.txt" in paths

    @pytest.mark.spec("BK-123")
    def test_get_folder_info_aggregates_nested(self, s3_backend: Backend) -> None:
        """get_folder_info aggregates count, size, modified across nested dirs."""
        s3_backend.write("nest/x.txt", b"xx")
        s3_backend.write("nest/sub/y.txt", b"yyyy")
        s3_backend.write("nest/sub/deep/z.txt", b"zzzzzz")
        info = s3_backend.get_folder_info("nest")
        assert info.file_count == 3
        assert info.total_size == 2 + 4 + 6
        assert info.modified_at is not None

    @pytest.mark.spec("BK-123")
    def test_find_not_called_for_recursive_list(self, s3_backend: Backend) -> None:
        """Verify _s3fs.find is NOT used for recursive listing (BFS via ls instead)."""
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        s3_backend.write("chk/a.txt", b"a")
        s3_backend.write("chk/b/c.txt", b"c")

        with patch.object(
            s3_backend._s3fs,
            "find",
            side_effect=AssertionError("find() should not be called"),
        ):
            files = list(s3_backend.list_files("chk", recursive=True))
        assert len(files) == 2

    @pytest.mark.spec("BK-123")
    def test_find_not_called_for_get_folder_info(self, s3_backend: Backend) -> None:
        """Verify _s3fs.find is NOT used for get_folder_info (BFS via ls instead)."""
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        s3_backend.write("fi2/a.txt", b"aaa")

        with patch.object(
            s3_backend._s3fs,
            "find",
            side_effect=AssertionError("find() should not be called"),
        ):
            info = s3_backend.get_folder_info("fi2")
        assert info.file_count == 1
        assert info.total_size == 3

    @pytest.mark.spec("BK-123")
    def test_find_not_called_for_list_folders(self, s3_backend: Backend) -> None:
        """Verify _s3fs.find is NOT used for list_folders."""
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        s3_backend.write("lf/sub/a.txt", b"a")

        with patch.object(
            s3_backend._s3fs,
            "find",
            side_effect=AssertionError("find() should not be called"),
        ):
            folders = list(s3_backend.list_folders("lf"))
        assert len(folders) == 1
        assert folders[0].name == "sub"


# endregion


# region: Resolution (RES-051)
class TestS3Resolve:
    """RES-051: S3Backend.resolve() returns kind='s3' with bucket, object_key, endpoint_url."""

    @pytest.mark.spec("RES-051")
    def test_kind_is_s3(self, s3_backend: Backend) -> None:
        plan = s3_backend.resolve("file.txt")
        assert plan.kind == "s3"

    @pytest.mark.spec("RES-051")
    def test_details_has_bucket(self, s3_backend: Backend) -> None:
        plan = s3_backend.resolve("file.txt")
        assert "bucket" in plan.details
        assert isinstance(plan.details["bucket"], str)
        assert len(plan.details["bucket"]) > 0

    @pytest.mark.spec("RES-051")
    def test_details_has_object_key(self, s3_backend: Backend) -> None:
        plan = s3_backend.resolve("dir/file.txt")
        assert "object_key" in plan.details
        assert plan.details["object_key"] == "dir/file.txt"

    @pytest.mark.spec("RES-051")
    def test_details_has_endpoint_url(self, s3_backend: Backend) -> None:
        plan = s3_backend.resolve("file.txt")
        assert "endpoint_url" in plan.details

    @pytest.mark.spec("RES-051")
    def test_endpoint_url_strips_userinfo(self) -> None:
        """Endpoint URL with embedded credentials has userinfo removed."""
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(
            bucket="test-bucket",
            key="k",
            secret="s",
            endpoint_url="http://user:pass@localhost:9000",
        )
        plan = backend.resolve("file.txt")
        assert "user" not in plan.details["endpoint_url"]
        assert "pass" not in plan.details["endpoint_url"]
        assert "localhost:9000" in plan.details["endpoint_url"]


# endregion


# ---------------------------------------------------------------------------
# WriteResult (WR-001, WR-003, WR-004, WR-012)
# ---------------------------------------------------------------------------


class TestS3WriteResult:
    """S3Backend.write/write_atomic return a valid WriteResult."""

    @pytest.mark.spec("WR-001")
    @pytest.mark.spec("WR-004")
    def test_write_returns_write_result(self, s3_backend: Backend) -> None:
        from remote_store._path import RemotePath

        result = s3_backend.write("f.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.path == RemotePath("f.txt")
        assert result.size == 5

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"hello world", 11), (b"", 0)])
    def test_write_size_bytes(self, s3_backend: Backend, payload: bytes, expected_size: int) -> None:
        result = s3_backend.write("f.txt", payload)
        assert result.size == expected_size

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"streamed", 8), (b"", 0)])
    def test_write_size_binaryio(self, s3_backend: Backend, payload: bytes, expected_size: int) -> None:
        import io

        result = s3_backend.write("f.txt", io.BytesIO(payload))
        assert result.size == expected_size

    @pytest.mark.spec("WR-001")
    def test_write_atomic_returns_write_result(self, s3_backend: Backend) -> None:
        from remote_store._path import RemotePath

        result = s3_backend.write_atomic("f.txt", b"data")
        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.path == RemotePath("f.txt")
        assert result.size == 4

    @pytest.mark.spec("WR-012")
    def test_write_metadata_echoed(self, s3_backend: Backend) -> None:
        result = s3_backend.write("f.txt", b"x", metadata={"k": "v"})
        assert result.metadata == {"k": "v"}

    @pytest.mark.spec("WR-012")
    def test_write_metadata_passed_to_sdk(self, s3_backend: Backend) -> None:
        """Metadata kwarg reaches the S3 object (verified via HeadObject)."""
        from remote_store.backends._s3 import S3Backend

        assert isinstance(s3_backend, S3Backend)
        s3_backend.write("meta.txt", b"x", metadata={"env": "test"})
        info = s3_backend.get_file_info("meta.txt")
        assert info.metadata == {"env": "test"}
