"""S3-PyArrow hybrid backend tests -- covers S3PA-xxx spec items.

Requires: moto[server,s3], s3fs, pyarrow, boto3 (test dependencies).
All tests are skipped if dependencies are not installed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

# Guard: skip entire module if dependencies are missing
pytest.importorskip("moto", reason="moto not installed")
pytest.importorskip("s3fs", reason="s3fs not installed")
pytest.importorskip("pyarrow", reason="pyarrow not installed")
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
def s3pa_backend(moto_server: str) -> Iterator[Backend]:
    """Create an S3PyArrowBackend against moto's mock S3 service."""
    bucket = f"test-pa-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name=REGION,
    )
    client.create_bucket(Bucket=bucket)

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    backend = S3PyArrowBackend(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name=REGION,
        endpoint_url=moto_server,
    )
    yield backend
    backend.close()


# region: Construction (S3PA-001 through S3PA-005)
class TestS3PyArrowConstruction:
    """S3PA-001 through S3PA-005: construction and identity."""

    @pytest.mark.spec("S3PA-001")
    def test_constructor_minimal(self, s3pa_backend: Backend) -> None:
        """Backend can be constructed with bucket and credentials."""
        assert s3pa_backend is not None

    @pytest.mark.spec("S3PA-002")
    def test_name_is_s3_pyarrow(self, s3pa_backend: Backend) -> None:
        assert s3pa_backend.name == "s3-pyarrow"

    @pytest.mark.spec("S3PA-003")
    def test_declares_all_capabilities(self, s3pa_backend: Backend) -> None:
        caps = s3pa_backend.capabilities
        assert isinstance(caps, CapabilitySet)
        for cap in Capability:
            assert caps.supports(cap), f"Missing capability: {cap.value}"

    @pytest.mark.spec("S3PA-004")
    def test_lazy_connection(self) -> None:
        """Construction must not make network calls."""
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        backend = S3PyArrowBackend(
            bucket="any-bucket",
            endpoint_url="http://localhost:99999",
            key="k",
            secret="s",
        )
        assert backend.name == "s3-pyarrow"

    @pytest.mark.spec("S3PA-005")
    def test_empty_bucket_raises(self) -> None:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        with pytest.raises(ValueError, match="bucket"):
            S3PyArrowBackend(bucket="")

    @pytest.mark.spec("S3PA-005")
    def test_whitespace_bucket_raises(self) -> None:
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        with pytest.raises(ValueError, match="bucket"):
            S3PyArrowBackend(bucket="   ")


# endregion


# region: S3 Object Model (S3PA-008 through S3PA-011)
class TestS3PyArrowFolderSemantics:
    """S3PA-008 through S3PA-011: virtual folder behavior."""

    @pytest.mark.spec("S3PA-009")
    def test_is_folder_with_objects(self, s3pa_backend: Backend) -> None:
        """Folder exists when objects share its prefix."""
        s3pa_backend.write("data/file.txt", b"x")
        assert s3pa_backend.is_folder("data") is True

    @pytest.mark.spec("S3PA-009")
    def test_is_folder_empty_prefix(self, s3pa_backend: Backend) -> None:
        """No objects under prefix means no folder."""
        assert s3pa_backend.is_folder("nonexistent") is False

    @pytest.mark.spec("S3PA-009")
    def test_is_folder_nested(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("a/b/c.txt", b"x")
        assert s3pa_backend.is_folder("a") is True
        assert s3pa_backend.is_folder("a/b") is True
        assert s3pa_backend.is_folder("a/b/c") is False

    @pytest.mark.spec("S3PA-010")
    def test_write_does_not_create_folder_markers(self, s3pa_backend: Backend) -> None:
        """Writing a nested file must not create folder marker objects."""
        s3pa_backend.write("x/y/z.txt", b"data")
        assert s3pa_backend.is_file("x/y/z.txt") is True
        assert s3pa_backend.is_file("x/") is False
        assert s3pa_backend.is_file("x/y/") is False

    @pytest.mark.spec("S3PA-011")
    def test_folder_vanishes_when_empty(self, s3pa_backend: Backend) -> None:
        """Deleting last file under a prefix makes folder disappear."""
        s3pa_backend.write("ephemeral/only.txt", b"x")
        assert s3pa_backend.is_folder("ephemeral") is True

        s3pa_backend.delete("ephemeral/only.txt")
        assert s3pa_backend.is_folder("ephemeral") is False

    @pytest.mark.spec("S3PA-011")
    def test_folder_persists_with_remaining_files(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("keep/a.txt", b"a")
        s3pa_backend.write("keep/b.txt", b"b")
        s3pa_backend.delete("keep/a.txt")
        assert s3pa_backend.is_folder("keep") is True


# endregion


# region: Operations (S3PA-012 through S3PA-017)
class TestS3PyArrowAtomicWrite:
    """S3PA-013: atomic write via S3 PUT."""

    @pytest.mark.spec("S3PA-013")
    def test_write_atomic_creates_file(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write_atomic("atomic.txt", b"atomic content")
        assert s3pa_backend.read_bytes("atomic.txt") == b"atomic content"

    @pytest.mark.spec("S3PA-013")
    def test_write_atomic_overwrite(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write_atomic("at.txt", b"first")
        s3pa_backend.write_atomic("at.txt", b"second", overwrite=True)
        assert s3pa_backend.read_bytes("at.txt") == b"second"

    @pytest.mark.spec("S3PA-013")
    def test_write_atomic_already_exists(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write_atomic("at2.txt", b"first")
        with pytest.raises(AlreadyExists):
            s3pa_backend.write_atomic("at2.txt", b"second", overwrite=False)


class TestS3PyArrowDeleteFolder:
    """S3PA-016: delete_folder semantics."""

    @pytest.mark.spec("S3PA-016")
    def test_delete_folder_recursive(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("rf/a.txt", b"a")
        s3pa_backend.write("rf/sub/b.txt", b"b")
        s3pa_backend.delete_folder("rf", recursive=True)
        assert s3pa_backend.exists("rf/a.txt") is False
        assert s3pa_backend.exists("rf/sub/b.txt") is False
        assert s3pa_backend.is_folder("rf") is False

    @pytest.mark.spec("S3PA-016")
    def test_delete_folder_recursive_not_found(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.delete_folder("ghost", recursive=True)

    @pytest.mark.spec("S3PA-016")
    def test_delete_folder_recursive_missing_ok(self, s3pa_backend: Backend) -> None:
        s3pa_backend.delete_folder("ghost", recursive=True, missing_ok=True)

    @pytest.mark.spec("S3PA-016")
    def test_delete_folder_non_recursive_not_found(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.delete_folder("empty", recursive=False)

    @pytest.mark.spec("S3PA-016")
    def test_delete_folder_non_recursive_non_empty(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("nonempty/file.txt", b"x")
        with pytest.raises(RemoteStoreError):
            s3pa_backend.delete_folder("nonempty", recursive=False)


class TestS3PyArrowMoveCopy:
    """S3PA-014, S3PA-015: move and copy operations."""

    @pytest.mark.spec("S3PA-015")
    def test_move(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("src.txt", b"data")
        s3pa_backend.move("src.txt", "dst.txt")
        assert s3pa_backend.exists("src.txt") is False
        assert s3pa_backend.read_bytes("dst.txt") == b"data"

    @pytest.mark.spec("S3PA-015")
    def test_move_not_found(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.move("missing.txt", "dst.txt")

    @pytest.mark.spec("S3PA-015")
    def test_move_already_exists(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("m1.txt", b"a")
        s3pa_backend.write("m2.txt", b"b")
        with pytest.raises(AlreadyExists):
            s3pa_backend.move("m1.txt", "m2.txt", overwrite=False)

    @pytest.mark.spec("S3PA-015")
    def test_move_overwrite(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("mo1.txt", b"a")
        s3pa_backend.write("mo2.txt", b"b")
        s3pa_backend.move("mo1.txt", "mo2.txt", overwrite=True)
        assert s3pa_backend.read_bytes("mo2.txt") == b"a"
        assert s3pa_backend.exists("mo1.txt") is False

    @pytest.mark.spec("S3PA-014")
    def test_copy(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("orig.txt", b"data")
        s3pa_backend.copy("orig.txt", "clone.txt")
        assert s3pa_backend.read_bytes("orig.txt") == b"data"
        assert s3pa_backend.read_bytes("clone.txt") == b"data"

    @pytest.mark.spec("S3PA-014")
    def test_copy_not_found(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.copy("missing.txt", "dst.txt")

    @pytest.mark.spec("S3PA-014")
    def test_copy_already_exists(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("c1.txt", b"a")
        s3pa_backend.write("c2.txt", b"b")
        with pytest.raises(AlreadyExists):
            s3pa_backend.copy("c1.txt", "c2.txt", overwrite=False)

    @pytest.mark.spec("S3PA-014")
    def test_copy_overwrite(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("co1.txt", b"a")
        s3pa_backend.write("co2.txt", b"b")
        s3pa_backend.copy("co1.txt", "co2.txt", overwrite=True)
        assert s3pa_backend.read_bytes("co2.txt") == b"a"
        assert s3pa_backend.read_bytes("co1.txt") == b"a"


# endregion


# region: Error Mapping (S3PA-018, S3PA-019)
class TestS3PyArrowErrorMapping:
    """S3PA-018, S3PA-019: error mapping."""

    @pytest.mark.spec("S3PA-018")
    def test_read_missing_maps_to_not_found(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound) as exc_info:
            s3pa_backend.read_bytes("does-not-exist.txt")
        assert exc_info.value.backend == "s3-pyarrow"

    @pytest.mark.spec("S3PA-018")
    def test_get_file_info_missing(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.get_file_info("nope.txt")

    @pytest.mark.spec("S3PA-018")
    def test_delete_missing(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.delete("nope.txt")

    @pytest.mark.spec("S3PA-019")
    def test_no_native_exception_leaks(self, s3pa_backend: Backend) -> None:
        """All errors must be RemoteStoreError subtypes."""
        with pytest.raises(RemoteStoreError):
            s3pa_backend.read("nonexistent.txt")

    @pytest.mark.spec("S3PA-019")
    def test_error_has_backend_attribute(self, s3pa_backend: Backend) -> None:
        with pytest.raises(RemoteStoreError) as exc_info:
            s3pa_backend.read("missing.txt")
        assert exc_info.value.backend == "s3-pyarrow"


# endregion


# region: Resource Management (S3PA-020, S3PA-021)
class TestS3PyArrowLifecycle:
    """S3PA-020, S3PA-021: close and unwrap."""

    @pytest.mark.spec("S3PA-020")
    def test_close_is_callable(self, s3pa_backend: Backend) -> None:
        s3pa_backend.close()

    @pytest.mark.spec("S3PA-020")
    def test_close_idempotent(self, s3pa_backend: Backend) -> None:
        s3pa_backend.close()
        s3pa_backend.close()

    @pytest.mark.spec("S3PA-021")
    def test_unwrap_pyarrow(self, s3pa_backend: Backend) -> None:
        from pyarrow.fs import S3FileSystem as PyArrowS3

        fs = s3pa_backend.unwrap(PyArrowS3)
        assert isinstance(fs, PyArrowS3)

    @pytest.mark.spec("S3PA-021")
    def test_unwrap_s3fs(self, s3pa_backend: Backend) -> None:
        import s3fs

        fs = s3pa_backend.unwrap(s3fs.S3FileSystem)
        assert isinstance(fs, s3fs.S3FileSystem)

    @pytest.mark.spec("S3PA-021")
    def test_unwrap_wrong_type_raises(self, s3pa_backend: Backend) -> None:
        with pytest.raises(CapabilityNotSupported):
            s3pa_backend.unwrap(str)


# endregion


# region: Configuration (S3PA-022)
class TestS3PyArrowConfiguration:
    """S3PA-022: client options and credential chain."""

    @pytest.mark.spec("S3PA-022")
    def test_client_options_accepted(self) -> None:
        """client_options are accepted without error at construction."""
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        backend = S3PyArrowBackend(
            bucket="any-bucket",
            key="k",
            secret="s",
            client_options={"connect_timeout": 5, "read_timeout": 10},
        )
        assert backend.name == "s3-pyarrow"

    @pytest.mark.spec("S3PA-001")
    def test_credentials_optional(self) -> None:
        """Backend can be constructed without explicit credentials."""
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        backend = S3PyArrowBackend(bucket="any-bucket")
        assert backend.name == "s3-pyarrow"


# endregion


# region: Read/Write roundtrip
class TestS3PyArrowReadWrite:
    """Basic read/write roundtrip to verify full stack."""

    def test_write_and_read_bytes(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("hello.txt", b"hello world")
        assert s3pa_backend.read_bytes("hello.txt") == b"hello world"

    def test_write_and_read_stream(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("stream.bin", b"\x00\x01\x02\xff")
        stream = s3pa_backend.read("stream.bin")
        assert stream.read() == b"\x00\x01\x02\xff"

    def test_write_overwrite(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("ow.txt", b"first")
        s3pa_backend.write("ow.txt", b"second", overwrite=True)
        assert s3pa_backend.read_bytes("ow.txt") == b"second"

    def test_write_already_exists(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("ae.txt", b"first")
        with pytest.raises(AlreadyExists):
            s3pa_backend.write("ae.txt", b"second")

    def test_write_nested_path(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("a/b/c/deep.txt", b"deep")
        assert s3pa_backend.read_bytes("a/b/c/deep.txt") == b"deep"

    def test_write_from_binaryio(self, s3pa_backend: Backend) -> None:
        import io

        s3pa_backend.write("bio.txt", io.BytesIO(b"streamed"))
        assert s3pa_backend.read_bytes("bio.txt") == b"streamed"


# endregion


# region: Listing and Metadata
class TestS3PyArrowListing:
    """File and folder listing operations."""

    def test_list_files_non_recursive(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("lst/a.txt", b"a")
        s3pa_backend.write("lst/b.txt", b"b")
        s3pa_backend.write("lst/sub/c.txt", b"c")
        files = list(s3pa_backend.list_files("lst"))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    def test_list_files_recursive(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("lr/a.txt", b"a")
        s3pa_backend.write("lr/sub/b.txt", b"b")
        files = list(s3pa_backend.list_files("lr", recursive=True))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    def test_list_files_empty_folder(self, s3pa_backend: Backend) -> None:
        files = list(s3pa_backend.list_files("empty"))
        assert files == []

    def test_list_folders(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("lf/sub1/a.txt", b"a")
        s3pa_backend.write("lf/sub2/b.txt", b"b")
        s3pa_backend.write("lf/root.txt", b"r")
        folders = set(s3pa_backend.list_folders("lf"))
        assert folders == {"sub1", "sub2"}

    def test_list_folders_empty(self, s3pa_backend: Backend) -> None:
        folders = list(s3pa_backend.list_folders("empty"))
        assert folders == []


class TestS3PyArrowMetadata:
    """File and folder metadata operations."""

    def test_get_file_info(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("info.txt", b"hello world")
        fi = s3pa_backend.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "info.txt"
        assert fi.size == 11
        assert fi.modified_at is not None

    def test_get_file_info_not_found(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.get_file_info("missing.txt")

    def test_get_folder_info(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("fi/a.txt", b"aaa")
        s3pa_backend.write("fi/b.txt", b"bb")
        fi = s3pa_backend.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    def test_get_folder_info_not_found(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.get_folder_info("nodir")

    def test_exists_file(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("e.txt", b"x")
        assert s3pa_backend.exists("e.txt") is True

    def test_exists_missing(self, s3pa_backend: Backend) -> None:
        assert s3pa_backend.exists("nope.txt") is False

    def test_is_file(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("f.txt", b"x")
        assert s3pa_backend.is_file("f.txt") is True
        assert s3pa_backend.is_file("missing.txt") is False

    def test_is_file_not_folder(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("dir/f.txt", b"x")
        assert s3pa_backend.is_file("dir") is False


class TestS3PyArrowDelete:
    """Delete operations."""

    def test_delete_file(self, s3pa_backend: Backend) -> None:
        s3pa_backend.write("del.txt", b"x")
        s3pa_backend.delete("del.txt")
        assert s3pa_backend.exists("del.txt") is False

    def test_delete_missing_ok(self, s3pa_backend: Backend) -> None:
        s3pa_backend.delete("nope.txt", missing_ok=True)

    def test_delete_missing_raises(self, s3pa_backend: Backend) -> None:
        with pytest.raises(NotFound):
            s3pa_backend.delete("nope.txt")


# endregion
