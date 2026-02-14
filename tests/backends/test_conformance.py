"""Backend conformance suite — tests BE-xxx specs against any backend."""

from __future__ import annotations

import io

import pytest

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import AlreadyExists, CapabilityNotSupported, NotFound
from remote_store._models import FileInfo, FolderInfo

# -- BE-001: ABC --


@pytest.mark.spec("BE-001")
def test_backend_is_instance(backend: Backend) -> None:
    assert isinstance(backend, Backend)


# -- BE-002: name --


@pytest.mark.spec("BE-002")
def test_name_is_string(backend: Backend) -> None:
    assert isinstance(backend.name, str)
    assert len(backend.name) > 0


# -- BE-003: capabilities --


@pytest.mark.spec("BE-003")
def test_capabilities_is_capabilityset(backend: Backend) -> None:
    assert isinstance(backend.capabilities, CapabilitySet)


# -- BE-004: exists --


@pytest.mark.spec("BE-004")
def test_exists_false_for_missing(backend: Backend) -> None:
    assert backend.exists("nonexistent.txt") is False


@pytest.mark.spec("BE-004")
def test_exists_true_after_write(backend: Backend) -> None:
    backend.write("hello.txt", b"hello")
    assert backend.exists("hello.txt") is True


# -- BE-005: is_file / is_folder --


@pytest.mark.spec("BE-005")
def test_is_file(backend: Backend) -> None:
    backend.write("a.txt", b"data")
    assert backend.is_file("a.txt") is True
    assert backend.is_folder("a.txt") is False


@pytest.mark.spec("BE-005")
def test_is_folder(backend: Backend) -> None:
    backend.write("dir/a.txt", b"data")
    assert backend.is_folder("dir") is True
    assert backend.is_file("dir") is False


@pytest.mark.spec("BE-005")
def test_is_file_false_for_missing(backend: Backend) -> None:
    assert backend.is_file("nope.txt") is False


@pytest.mark.spec("BE-005")
def test_is_folder_false_for_missing(backend: Backend) -> None:
    assert backend.is_folder("nope") is False


# -- BE-006: read --


@pytest.mark.spec("BE-006")
def test_read_returns_binary_stream(backend: Backend) -> None:
    backend.write("data.bin", b"\x00\x01\x02")
    stream = backend.read("data.bin")
    assert stream.read() == b"\x00\x01\x02"


@pytest.mark.spec("BE-006")
def test_read_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.read("missing.txt")


# -- BE-007: read_bytes --


@pytest.mark.spec("BE-007")
def test_read_bytes(backend: Backend) -> None:
    backend.write("file.txt", b"content")
    assert backend.read_bytes("file.txt") == b"content"


@pytest.mark.spec("BE-007")
def test_read_bytes_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.read_bytes("missing.txt")


# -- BE-008: write --


@pytest.mark.spec("BE-008")
def test_write_creates_file(backend: Backend) -> None:
    backend.write("new.txt", b"hello")
    assert backend.read_bytes("new.txt") == b"hello"


@pytest.mark.spec("BE-008")
def test_write_raises_already_exists(backend: Backend) -> None:
    backend.write("exists.txt", b"first")
    with pytest.raises(AlreadyExists):
        backend.write("exists.txt", b"second", overwrite=False)


@pytest.mark.spec("BE-008")
def test_write_overwrite(backend: Backend) -> None:
    backend.write("over.txt", b"first")
    backend.write("over.txt", b"second", overwrite=True)
    assert backend.read_bytes("over.txt") == b"second"


@pytest.mark.spec("BE-008")
def test_write_from_binaryio(backend: Backend) -> None:
    backend.write("stream.txt", io.BytesIO(b"streamed"))
    assert backend.read_bytes("stream.txt") == b"streamed"


# -- BE-009: write creates intermediate dirs --


@pytest.mark.spec("BE-009")
def test_write_creates_intermediate_dirs(backend: Backend) -> None:
    backend.write("a/b/c/deep.txt", b"deep")
    assert backend.read_bytes("a/b/c/deep.txt") == b"deep"


# -- BE-010: write_atomic --


@pytest.mark.spec("BE-010")
def test_write_atomic_creates_file(backend: Backend) -> None:
    if not backend.capabilities.supports(Capability.ATOMIC_WRITE):
        pytest.skip("Backend does not support ATOMIC_WRITE")
    backend.write_atomic("atomic.txt", b"atomic content")
    assert backend.read_bytes("atomic.txt") == b"atomic content"


@pytest.mark.spec("BE-010")
def test_write_atomic_overwrite(backend: Backend) -> None:
    if not backend.capabilities.supports(Capability.ATOMIC_WRITE):
        pytest.skip("Backend does not support ATOMIC_WRITE")
    backend.write_atomic("atomic2.txt", b"first")
    backend.write_atomic("atomic2.txt", b"second", overwrite=True)
    assert backend.read_bytes("atomic2.txt") == b"second"


@pytest.mark.spec("BE-010")
def test_write_atomic_already_exists(backend: Backend) -> None:
    if not backend.capabilities.supports(Capability.ATOMIC_WRITE):
        pytest.skip("Backend does not support ATOMIC_WRITE")
    backend.write_atomic("atomic3.txt", b"first")
    with pytest.raises(AlreadyExists):
        backend.write_atomic("atomic3.txt", b"second", overwrite=False)


# -- BE-012: delete --


@pytest.mark.spec("BE-012")
def test_delete_removes_file(backend: Backend) -> None:
    backend.write("del.txt", b"bye")
    backend.delete("del.txt")
    assert backend.exists("del.txt") is False


@pytest.mark.spec("BE-012")
def test_delete_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.delete("missing.txt")


@pytest.mark.spec("BE-012")
def test_delete_missing_ok(backend: Backend) -> None:
    backend.delete("missing.txt", missing_ok=True)  # Should not raise


# -- BE-013: delete_folder --


@pytest.mark.spec("BE-013")
def test_delete_folder_empty(backend: Backend) -> None:
    backend.write("dir/file.txt", b"x")
    backend.delete("dir/file.txt")
    backend.delete_folder("dir")
    assert backend.exists("dir") is False


@pytest.mark.spec("BE-013")
def test_delete_folder_recursive(backend: Backend) -> None:
    backend.write("dir2/a.txt", b"a")
    backend.write("dir2/sub/b.txt", b"b")
    backend.delete_folder("dir2", recursive=True)
    assert backend.exists("dir2") is False


@pytest.mark.spec("BE-013")
def test_delete_folder_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.delete_folder("nodir")


@pytest.mark.spec("BE-013")
def test_delete_folder_missing_ok(backend: Backend) -> None:
    backend.delete_folder("nodir", missing_ok=True)  # Should not raise


# -- BE-014: list_files --


@pytest.mark.spec("BE-014")
def test_list_files_non_recursive(backend: Backend) -> None:
    backend.write("lf/a.txt", b"a")
    backend.write("lf/b.txt", b"b")
    backend.write("lf/sub/c.txt", b"c")
    files = list(backend.list_files("lf"))
    names = {f.name for f in files}
    assert names == {"a.txt", "b.txt"}
    for f in files:
        assert isinstance(f, FileInfo)


@pytest.mark.spec("BE-014")
def test_list_files_recursive(backend: Backend) -> None:
    backend.write("lfr/a.txt", b"a")
    backend.write("lfr/sub/b.txt", b"b")
    files = list(backend.list_files("lfr", recursive=True))
    names = {f.name for f in files}
    assert names == {"a.txt", "b.txt"}


# -- BE-015: list_folders --


@pytest.mark.spec("BE-015")
def test_list_folders(backend: Backend) -> None:
    backend.write("lfd/sub1/a.txt", b"a")
    backend.write("lfd/sub2/b.txt", b"b")
    backend.write("lfd/file.txt", b"f")
    folders = set(backend.list_folders("lfd"))
    assert folders == {"sub1", "sub2"}


# -- BE-016: get_file_info --


@pytest.mark.spec("BE-016")
def test_get_file_info(backend: Backend) -> None:
    backend.write("info.txt", b"hello world")
    fi = backend.get_file_info("info.txt")
    assert isinstance(fi, FileInfo)
    assert fi.name == "info.txt"
    assert fi.size == 11


@pytest.mark.spec("BE-016")
def test_get_file_info_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.get_file_info("missing.txt")


# -- BE-017: get_folder_info --


@pytest.mark.spec("BE-017")
def test_get_folder_info(backend: Backend) -> None:
    backend.write("fi/a.txt", b"aaa")
    backend.write("fi/b.txt", b"bb")
    fi = backend.get_folder_info("fi")
    assert isinstance(fi, FolderInfo)
    assert fi.file_count == 2
    assert fi.total_size == 5


@pytest.mark.spec("BE-017")
def test_get_folder_info_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.get_folder_info("nodir")


# -- BE-018: move --


@pytest.mark.spec("BE-018")
def test_move(backend: Backend) -> None:
    backend.write("mv_src.txt", b"data")
    backend.move("mv_src.txt", "mv_dst.txt")
    assert backend.exists("mv_src.txt") is False
    assert backend.read_bytes("mv_dst.txt") == b"data"


@pytest.mark.spec("BE-018")
def test_move_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.move("missing.txt", "dst.txt")


@pytest.mark.spec("BE-018")
def test_move_already_exists(backend: Backend) -> None:
    backend.write("mv1.txt", b"a")
    backend.write("mv2.txt", b"b")
    with pytest.raises(AlreadyExists):
        backend.move("mv1.txt", "mv2.txt", overwrite=False)


@pytest.mark.spec("BE-018")
def test_move_overwrite(backend: Backend) -> None:
    backend.write("mvo1.txt", b"a")
    backend.write("mvo2.txt", b"b")
    backend.move("mvo1.txt", "mvo2.txt", overwrite=True)
    assert backend.read_bytes("mvo2.txt") == b"a"


# -- BE-019: copy --


@pytest.mark.spec("BE-019")
def test_copy(backend: Backend) -> None:
    backend.write("cp_src.txt", b"data")
    backend.copy("cp_src.txt", "cp_dst.txt")
    assert backend.read_bytes("cp_src.txt") == b"data"
    assert backend.read_bytes("cp_dst.txt") == b"data"


@pytest.mark.spec("BE-019")
def test_copy_not_found(backend: Backend) -> None:
    with pytest.raises(NotFound):
        backend.copy("missing.txt", "dst.txt")


@pytest.mark.spec("BE-019")
def test_copy_already_exists(backend: Backend) -> None:
    backend.write("cp1.txt", b"a")
    backend.write("cp2.txt", b"b")
    with pytest.raises(AlreadyExists):
        backend.copy("cp1.txt", "cp2.txt", overwrite=False)


@pytest.mark.spec("BE-019")
def test_copy_overwrite(backend: Backend) -> None:
    backend.write("cpo1.txt", b"a")
    backend.write("cpo2.txt", b"b")
    backend.copy("cpo1.txt", "cpo2.txt", overwrite=True)
    assert backend.read_bytes("cpo2.txt") == b"a"
    assert backend.read_bytes("cpo1.txt") == b"a"


# -- BE-020: close --


@pytest.mark.spec("BE-020")
def test_close_is_callable(backend: Backend) -> None:
    backend.close()  # Should not raise


# -- BE-022: unwrap --


@pytest.mark.spec("BE-022")
def test_unwrap_raises_by_default(backend: Backend) -> None:
    with pytest.raises(CapabilityNotSupported):
        backend.unwrap(str)
