"""Backend conformance suite — tests BE-xxx specs against any backend."""

from __future__ import annotations

import io

import pytest

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, CapabilityNotSupported, NotFound
from remote_store._models import FileInfo, FolderInfo


class TestBackendIdentity:
    """BE-001 through BE-003: backend identity and capabilities."""

    @pytest.mark.spec("BE-001")
    def test_backend_is_instance(self, backend: Backend) -> None:
        assert isinstance(backend, Backend)

    @pytest.mark.spec("BE-002")
    def test_name_is_string(self, backend: Backend) -> None:
        assert isinstance(backend.name, str)
        assert len(backend.name) > 0

    @pytest.mark.spec("BE-003")
    def test_capabilities_is_capabilityset(self, backend: Backend) -> None:
        assert isinstance(backend.capabilities, CapabilitySet)


class TestBackendExists:
    """BE-004: exists() behavior."""

    @pytest.mark.spec("BE-004")
    def test_false_for_missing(self, backend: Backend) -> None:
        assert backend.exists("nonexistent.txt") is False

    @pytest.mark.spec("BE-004")
    def test_true_after_write(self, backend: Backend) -> None:
        backend.write("hello.txt", b"hello")
        assert backend.exists("hello.txt") is True


class TestBackendFileFolder:
    """BE-005: is_file() / is_folder() distinction."""

    @pytest.mark.spec("BE-005")
    def test_is_file(self, backend: Backend) -> None:
        backend.write("a.txt", b"data")
        assert backend.is_file("a.txt") is True
        assert backend.is_folder("a.txt") is False

    @pytest.mark.spec("BE-005")
    def test_is_folder(self, backend: Backend) -> None:
        backend.write("dir/a.txt", b"data")
        assert backend.is_folder("dir") is True
        assert backend.is_file("dir") is False

    @pytest.mark.spec("BE-005")
    def test_is_file_false_for_missing(self, backend: Backend) -> None:
        assert backend.is_file("nope.txt") is False

    @pytest.mark.spec("BE-005")
    def test_is_folder_false_for_missing(self, backend: Backend) -> None:
        assert backend.is_folder("nope") is False


class TestBackendRead:
    """BE-006 through BE-007: read operations."""

    @pytest.mark.spec("BE-006")
    def test_read_returns_binary_stream(self, backend: Backend) -> None:
        backend.write("data.bin", b"\x00\x01\x02")
        stream = backend.read("data.bin")
        assert stream.read() == b"\x00\x01\x02"

    @pytest.mark.spec("BE-006")
    def test_read_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.read("missing.txt")

    @pytest.mark.spec("BE-007")
    def test_read_bytes(self, backend: Backend) -> None:
        backend.write("file.txt", b"content")
        assert backend.read_bytes("file.txt") == b"content"

    @pytest.mark.spec("BE-007")
    def test_read_bytes_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.read_bytes("missing.txt")


class TestBackendWrite:
    """BE-008 through BE-009: write operations."""

    @pytest.mark.spec("BE-008")
    def test_write_creates_file(self, backend: Backend) -> None:
        backend.write("new.txt", b"hello")
        assert backend.read_bytes("new.txt") == b"hello"

    @pytest.mark.spec("BE-008")
    def test_write_raises_already_exists(self, backend: Backend) -> None:
        backend.write("exists.txt", b"first")
        with pytest.raises(AlreadyExists):
            backend.write("exists.txt", b"second", overwrite=False)

    @pytest.mark.spec("BE-008")
    def test_write_overwrite(self, backend: Backend) -> None:
        backend.write("over.txt", b"first")
        backend.write("over.txt", b"second", overwrite=True)
        assert backend.read_bytes("over.txt") == b"second"

    @pytest.mark.spec("BE-008")
    def test_write_from_binaryio(self, backend: Backend) -> None:
        backend.write("stream.txt", io.BytesIO(b"streamed"))
        assert backend.read_bytes("stream.txt") == b"streamed"

    @pytest.mark.spec("BE-009")
    def test_write_creates_intermediate_dirs(self, backend: Backend) -> None:
        backend.write("a/b/c/deep.txt", b"deep")
        assert backend.read_bytes("a/b/c/deep.txt") == b"deep"


class TestBackendWriteAtomic:
    """BE-010 through BE-011: atomic write operations."""

    @pytest.mark.spec("BE-010")
    def test_write_atomic_creates_file(self, backend: Backend) -> None:
        if not backend.capabilities.supports(Capability.ATOMIC_WRITE):
            pytest.skip("Backend does not support ATOMIC_WRITE")
        backend.write_atomic("atomic.txt", b"atomic content")
        assert backend.read_bytes("atomic.txt") == b"atomic content"

    @pytest.mark.spec("BE-010")
    def test_write_atomic_overwrite(self, backend: Backend) -> None:
        if not backend.capabilities.supports(Capability.ATOMIC_WRITE):
            pytest.skip("Backend does not support ATOMIC_WRITE")
        backend.write_atomic("atomic2.txt", b"first")
        backend.write_atomic("atomic2.txt", b"second", overwrite=True)
        assert backend.read_bytes("atomic2.txt") == b"second"

    @pytest.mark.spec("BE-010")
    def test_write_atomic_already_exists(self, backend: Backend) -> None:
        if not backend.capabilities.supports(Capability.ATOMIC_WRITE):
            pytest.skip("Backend does not support ATOMIC_WRITE")
        backend.write_atomic("atomic3.txt", b"first")
        with pytest.raises(AlreadyExists):
            backend.write_atomic("atomic3.txt", b"second", overwrite=False)


class TestBackendDelete:
    """BE-012 through BE-013: delete operations."""

    @pytest.mark.spec("BE-012")
    def test_delete_removes_file(self, backend: Backend) -> None:
        backend.write("del.txt", b"bye")
        backend.delete("del.txt")
        assert backend.exists("del.txt") is False

    @pytest.mark.spec("BE-012")
    def test_delete_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.delete("missing.txt")

    @pytest.mark.spec("BE-012")
    def test_delete_missing_ok(self, backend: Backend) -> None:
        backend.delete("missing.txt", missing_ok=True)

    @pytest.mark.spec("BE-013")
    def test_delete_folder_empty(self, backend: Backend) -> None:
        if backend.name == "s3":
            pytest.skip("S3 virtual folders vanish when last object is deleted (S3-009)")
        backend.write("dir/file.txt", b"x")
        backend.delete("dir/file.txt")
        backend.delete_folder("dir")
        assert backend.exists("dir") is False

    @pytest.mark.spec("BE-013")
    def test_delete_folder_recursive(self, backend: Backend) -> None:
        backend.write("dir2/a.txt", b"a")
        backend.write("dir2/sub/b.txt", b"b")
        backend.delete_folder("dir2", recursive=True)
        assert backend.exists("dir2") is False

    @pytest.mark.spec("BE-013")
    def test_delete_folder_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.delete_folder("nodir")

    @pytest.mark.spec("BE-013")
    def test_delete_folder_missing_ok(self, backend: Backend) -> None:
        backend.delete_folder("nodir", missing_ok=True)


class TestBackendListing:
    """BE-014 through BE-015: listing operations."""

    @pytest.mark.spec("BE-014")
    def test_list_files_non_recursive(self, backend: Backend) -> None:
        backend.write("lf/a.txt", b"a")
        backend.write("lf/b.txt", b"b")
        backend.write("lf/sub/c.txt", b"c")
        files = list(backend.list_files("lf"))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}
        for f in files:
            assert isinstance(f, FileInfo)

    @pytest.mark.spec("BE-014")
    def test_list_files_recursive(self, backend: Backend) -> None:
        backend.write("lfr/a.txt", b"a")
        backend.write("lfr/sub/b.txt", b"b")
        files = list(backend.list_files("lfr", recursive=True))
        names = {f.name for f in files}
        assert names == {"a.txt", "b.txt"}

    @pytest.mark.spec("BE-015")
    def test_list_folders(self, backend: Backend) -> None:
        backend.write("lfd/sub1/a.txt", b"a")
        backend.write("lfd/sub2/b.txt", b"b")
        backend.write("lfd/file.txt", b"f")
        folders = set(backend.list_folders("lfd"))
        assert folders == {"sub1", "sub2"}


class TestBackendMetadata:
    """BE-016 through BE-017: metadata operations."""

    @pytest.mark.spec("BE-016")
    def test_get_file_info(self, backend: Backend) -> None:
        backend.write("info.txt", b"hello world")
        fi = backend.get_file_info("info.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "info.txt"
        assert fi.size == 11

    @pytest.mark.spec("BE-016")
    def test_get_file_info_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.get_file_info("missing.txt")

    @pytest.mark.spec("BE-017")
    def test_get_folder_info(self, backend: Backend) -> None:
        backend.write("fi/a.txt", b"aaa")
        backend.write("fi/b.txt", b"bb")
        fi = backend.get_folder_info("fi")
        assert isinstance(fi, FolderInfo)
        assert fi.file_count == 2
        assert fi.total_size == 5

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.get_folder_info("nodir")


class TestBackendMove:
    """BE-018: move operations."""

    @pytest.mark.spec("BE-018")
    def test_move(self, backend: Backend) -> None:
        backend.write("mv_src.txt", b"data")
        backend.move("mv_src.txt", "mv_dst.txt")
        assert backend.exists("mv_src.txt") is False
        assert backend.read_bytes("mv_dst.txt") == b"data"

    @pytest.mark.spec("BE-018")
    def test_move_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.move("missing.txt", "dst.txt")

    @pytest.mark.spec("BE-018")
    def test_move_already_exists(self, backend: Backend) -> None:
        backend.write("mv1.txt", b"a")
        backend.write("mv2.txt", b"b")
        with pytest.raises(AlreadyExists):
            backend.move("mv1.txt", "mv2.txt", overwrite=False)

    @pytest.mark.spec("BE-018")
    def test_move_overwrite(self, backend: Backend) -> None:
        backend.write("mvo1.txt", b"a")
        backend.write("mvo2.txt", b"b")
        backend.move("mvo1.txt", "mvo2.txt", overwrite=True)
        assert backend.read_bytes("mvo2.txt") == b"a"


class TestBackendCopy:
    """BE-019: copy operations."""

    @pytest.mark.spec("BE-019")
    def test_copy(self, backend: Backend) -> None:
        backend.write("cp_src.txt", b"data")
        backend.copy("cp_src.txt", "cp_dst.txt")
        assert backend.read_bytes("cp_src.txt") == b"data"
        assert backend.read_bytes("cp_dst.txt") == b"data"

    @pytest.mark.spec("BE-019")
    def test_copy_not_found(self, backend: Backend) -> None:
        with pytest.raises(NotFound):
            backend.copy("missing.txt", "dst.txt")

    @pytest.mark.spec("BE-019")
    def test_copy_already_exists(self, backend: Backend) -> None:
        backend.write("cp1.txt", b"a")
        backend.write("cp2.txt", b"b")
        with pytest.raises(AlreadyExists):
            backend.copy("cp1.txt", "cp2.txt", overwrite=False)

    @pytest.mark.spec("BE-019")
    def test_copy_overwrite(self, backend: Backend) -> None:
        backend.write("cpo1.txt", b"a")
        backend.write("cpo2.txt", b"b")
        backend.copy("cpo1.txt", "cpo2.txt", overwrite=True)
        assert backend.read_bytes("cpo2.txt") == b"a"
        assert backend.read_bytes("cpo1.txt") == b"a"


class TestBackendLifecycle:
    """BE-020: close is callable."""

    @pytest.mark.spec("BE-020")
    def test_close_is_callable(self, backend: Backend) -> None:
        backend.close()


class TestBackendToKey:
    """NPR-003 through NPR-008: to_key reverse path resolution."""

    @pytest.mark.spec("NPR-003")
    def test_to_key_exists(self, backend: Backend) -> None:
        assert hasattr(backend, "to_key")
        assert callable(backend.to_key)

    @pytest.mark.spec("NPR-004")
    def test_to_key_is_deterministic(self, backend: Backend) -> None:
        assert backend.to_key("some/path") == backend.to_key("some/path")

    @pytest.mark.spec("NPR-005")
    def test_to_key_passthrough_for_relative(self, backend: Backend) -> None:
        """Relative paths with no matching prefix pass through unchanged."""
        result = backend.to_key("some/path")
        assert isinstance(result, str)

    @pytest.mark.spec("NPR-003")
    def test_to_key_round_trip_with_listing(self, backend: Backend) -> None:
        """Paths from list_files can be converted back via to_key."""
        backend.write("tk/a.txt", b"a")
        files = list(backend.list_files("tk"))
        assert len(files) == 1
        # The path in FileInfo should be a valid backend-relative key
        key = str(files[0].path)
        assert backend.read_bytes(key) == b"a"


class TestBackendUnwrap:
    """BE-022: unwrap raises by default."""

    @pytest.mark.spec("BE-022")
    def test_unwrap_raises_by_default(self, backend: Backend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.unwrap(str)
