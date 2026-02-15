"""S3 backend tests -- covers S3-xxx spec items.

Requires: moto[server,s3], s3fs, boto3 (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("moto", reason="moto not installed")
pytest.importorskip("s3fs", reason="s3fs not installed")
boto3 = pytest.importorskip("boto3", reason="boto3 not installed")

from remote_store._capabilities import Capability, CapabilitySet  # noqa: E402
from remote_store._errors import (  # noqa: E402
    AlreadyExists,
    CapabilityNotSupported,
    NotFound,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend

REGION = "us-east-1"


@pytest.fixture()
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
            assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("S3-004")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        # No mock_aws context -- any real network call would fail
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(
            bucket="any-bucket",
            endpoint_url="http://localhost:99999",
            key="k",
            secret="s",
        )
        # Should succeed -- no connection attempted yet
        assert backend.name == "s3"

    @pytest.mark.spec("S3-005")
    def test_empty_bucket_raises(self) -> None:
        from remote_store.backends._s3 import S3Backend

        with pytest.raises(ValueError, match="bucket"):
            S3Backend(bucket="")

    @pytest.mark.spec("S3-005")
    def test_whitespace_bucket_raises(self) -> None:
        from remote_store.backends._s3 import S3Backend

        with pytest.raises(ValueError, match="bucket"):
            S3Backend(bucket="   ")


# endregion


# region: S3 Object Model (S3-006 through S3-009)


class TestS3FolderSemantics:
    """S3-006 through S3-009: virtual folder behavior."""

    @pytest.mark.spec("S3-007")
    def test_is_folder_with_objects(self, s3_backend: Backend) -> None:
        """Folder exists when objects share its prefix."""
        s3_backend.write("data/file.txt", b"x")
        assert s3_backend.is_folder("data") is True

    @pytest.mark.spec("S3-007")
    def test_is_folder_empty_prefix(self, s3_backend: Backend) -> None:
        """No objects under prefix means no folder."""
        assert s3_backend.is_folder("nonexistent") is False

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


class TestS3AtomicWrite:
    """S3-010: atomic write via S3 PUT."""

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


class TestS3DeleteFolder:
    """S3-011, S3-012: delete_folder semantics."""

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
        s3_backend.delete_folder("ghost", recursive=True, missing_ok=True)

    @pytest.mark.spec("S3-012")
    def test_delete_folder_non_recursive_not_found(self, s3_backend: Backend) -> None:
        """Non-recursive delete on non-existent folder raises NotFound."""
        with pytest.raises(NotFound):
            s3_backend.delete_folder("empty", recursive=False)

    @pytest.mark.spec("S3-012")
    def test_delete_folder_non_recursive_non_empty(self, s3_backend: Backend) -> None:
        """Non-recursive delete on non-empty folder must fail."""
        s3_backend.write("nonempty/file.txt", b"x")
        with pytest.raises(RemoteStoreError):
            s3_backend.delete_folder("nonempty", recursive=False)


class TestS3MoveCopy:
    """S3-013, S3-014: move and copy operations."""

    @pytest.mark.spec("S3-013")
    def test_move(self, s3_backend: Backend) -> None:
        s3_backend.write("src.txt", b"data")
        s3_backend.move("src.txt", "dst.txt")
        assert s3_backend.exists("src.txt") is False
        assert s3_backend.read_bytes("dst.txt") == b"data"

    @pytest.mark.spec("S3-013")
    def test_move_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.move("missing.txt", "dst.txt")

    @pytest.mark.spec("S3-013")
    def test_move_already_exists(self, s3_backend: Backend) -> None:
        s3_backend.write("m1.txt", b"a")
        s3_backend.write("m2.txt", b"b")
        with pytest.raises(AlreadyExists):
            s3_backend.move("m1.txt", "m2.txt", overwrite=False)

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
    def test_copy_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.copy("missing.txt", "dst.txt")

    @pytest.mark.spec("S3-014")
    def test_copy_already_exists(self, s3_backend: Backend) -> None:
        s3_backend.write("c1.txt", b"a")
        s3_backend.write("c2.txt", b"b")
        with pytest.raises(AlreadyExists):
            s3_backend.copy("c1.txt", "c2.txt", overwrite=False)

    @pytest.mark.spec("S3-014")
    def test_copy_overwrite(self, s3_backend: Backend) -> None:
        s3_backend.write("co1.txt", b"a")
        s3_backend.write("co2.txt", b"b")
        s3_backend.copy("co1.txt", "co2.txt", overwrite=True)
        assert s3_backend.read_bytes("co2.txt") == b"a"
        assert s3_backend.read_bytes("co1.txt") == b"a"


# endregion


# region: Error Mapping (S3-015 through S3-018)


class TestS3ErrorMapping:
    """S3-015 through S3-018: error mapping."""

    @pytest.mark.spec("S3-015")
    def test_read_missing_maps_to_not_found(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound) as exc_info:
            s3_backend.read_bytes("does-not-exist.txt")
        assert exc_info.value.backend == "s3"

    @pytest.mark.spec("S3-015")
    def test_get_file_info_missing(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.get_file_info("nope.txt")

    @pytest.mark.spec("S3-015")
    def test_delete_missing(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.delete("nope.txt")

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
        s3_backend.close()

    @pytest.mark.spec("S3-019")
    def test_close_idempotent(self, s3_backend: Backend) -> None:
        s3_backend.close()
        s3_backend.close()

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


# region: Configuration (S3-021, S3-022)


class TestS3Configuration:
    """S3-021, S3-022: client options and credential chain."""

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

    @pytest.mark.spec("S3-022")
    def test_credentials_optional(self) -> None:
        """Backend can be constructed without explicit credentials."""
        from remote_store.backends._s3 import S3Backend

        backend = S3Backend(bucket="any-bucket")
        assert backend.name == "s3"


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
        import io

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
        folders = set(s3_backend.list_folders("lf"))
        assert folders == {"sub1", "sub2"}

    def test_list_folders_empty(self, s3_backend: Backend) -> None:
        folders = list(s3_backend.list_folders("empty"))
        assert folders == []


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

    def test_exists_file(self, s3_backend: Backend) -> None:
        s3_backend.write("e.txt", b"x")
        assert s3_backend.exists("e.txt") is True

    def test_exists_missing(self, s3_backend: Backend) -> None:
        assert s3_backend.exists("nope.txt") is False

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
        s3_backend.delete("nope.txt", missing_ok=True)

    def test_delete_missing_raises(self, s3_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3_backend.delete("nope.txt")


# endregion
