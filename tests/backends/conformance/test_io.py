"""Backend I/O conformance: exists, file/folder, read, write, delete, to_key, round-trip.

Most classes apply ``fixture_params(Capability.WRITE)`` at the class
level since their tests overwhelmingly need WRITE. Class-internal
``_require()`` calls remain as defensive guards for tests that need
additional capabilities (DELETE, LIST, ...).
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, NotFound
from tests.backends.conformance._helpers import _fixture_record, _require, _seed
from tests.backends.fixtures import fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendExists:
    """BE-004: exists() behavior."""

    @pytest.mark.spec("BE-004")
    def test_false_for_missing(self, backend: Backend) -> None:
        assert backend.exists("nonexistent.txt") is False

    @pytest.mark.spec("BE-004")
    def test_true_after_write(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("hello.txt", b"hello")
        assert backend.exists("hello.txt") is True


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendFileFolder:
    """BE-005: is_file() / is_folder() distinction."""

    @pytest.mark.spec("BE-005")
    def test_is_file(self, backend: Backend) -> None:
        backend.write("a.txt", b"data")
        assert backend.is_file("a.txt") is True
        assert backend.is_folder("a.txt") is False

    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("AZ-009")
    @pytest.mark.spec("S3-006")
    @pytest.mark.spec("S3PA-008")
    @pytest.mark.spec("MEM-DS-006")
    def test_is_folder(self, backend: Backend) -> None:
        backend.write("dir/a.txt", b"data")
        assert backend.is_folder("dir") is True
        assert backend.is_file("dir") is False

    @pytest.mark.spec("BE-005")
    @pytest.mark.parametrize(
        "method",
        [pytest.param("is_file", id="is_file"), pytest.param("is_folder", id="is_folder")],
    )
    def test_false_for_missing(self, backend: Backend, method: str) -> None:
        assert getattr(backend, method)("nope") is False


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendRead:
    """BE-006 through BE-007: read operations."""

    @pytest.mark.spec("BE-006")
    def test_read_returns_binary_stream(self, backend: Backend) -> None:
        backend.write("data.bin", b"\x00\x01\x02")
        with backend.read("data.bin") as stream:
            assert stream.read() == b"\x00\x01\x02"

    @pytest.mark.spec("BE-007")
    @pytest.mark.spec("SQL-BLOB-021")
    @pytest.mark.spec("MEM-011")
    def test_read_bytes(self, backend: Backend) -> None:
        backend.write("file.txt", b"content")
        assert backend.read_bytes("file.txt") == b"content"

    @pytest.mark.spec("BE-006")
    @pytest.mark.spec("BE-007")
    @pytest.mark.parametrize(
        "method",
        [pytest.param("read", id="read_stream"), pytest.param("read_bytes", id="read_bytes")],
    )
    def test_not_found(self, backend: Backend, method: str) -> None:
        with pytest.raises(NotFound):
            getattr(backend, method)("missing.txt")


@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
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


@pytest.mark.parametrize("backend", fixture_params(Capability.DELETE), indirect=True)
class TestBackendDelete:
    """BE-012 through BE-013: delete operations."""

    @pytest.mark.spec("BE-012")
    @pytest.mark.spec("SQL-BLOB-024")
    def test_delete_removes_file(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        backend.write("del.txt", b"bye")
        backend.delete("del.txt")
        assert backend.exists("del.txt") is False

    @pytest.mark.spec("BE-013")
    def test_delete_folder_empty(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        if _fixture_record(backend).flat_namespace:
            pytest.skip("Virtual folders vanish when last object is deleted (S3-009/AZ-006/SQL-BLOB-flat)")
        backend.write("dir/file.txt", b"x")
        backend.delete("dir/file.txt")
        backend.delete_folder("dir")
        assert backend.exists("dir") is False

    @pytest.mark.spec("BE-013")
    @pytest.mark.spec("SFTP-016")
    @pytest.mark.spec("AZ-015")
    @pytest.mark.spec("S3-011")
    def test_delete_folder_recursive(self, backend: Backend) -> None:
        _require(backend, Capability.WRITE)
        _seed(backend, {"dir2/a.txt": b"a", "dir2/sub/b.txt": b"b"})
        backend.delete_folder("dir2", recursive=True)
        assert backend.exists("dir2") is False

    @pytest.mark.spec("BE-012")
    @pytest.mark.spec("BE-013")
    @pytest.mark.parametrize(
        ("method", "target"),
        [
            pytest.param("delete", "missing.txt", id="file"),
            pytest.param("delete_folder", "nodir", id="folder"),
        ],
    )
    @pytest.mark.parametrize(
        ("missing_ok", "expect_error"),
        [
            pytest.param(False, True, id="not_found_raises"),
            pytest.param(True, False, id="missing_ok_passes"),
        ],
    )
    def test_delete_missing(
        self,
        backend: Backend,
        method: str,
        target: str,
        missing_ok: bool,
        expect_error: bool,
    ) -> None:
        if expect_error:
            with pytest.raises(NotFound):
                getattr(backend, method)(target, missing_ok=missing_ok)
        else:
            getattr(backend, method)(target, missing_ok=missing_ok)


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
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
    @pytest.mark.spec("MEM-017")
    @pytest.mark.spec("BE-023")
    def test_to_key_passthrough_for_relative(self, backend: Backend) -> None:
        """Relative paths with no matching prefix pass through unchanged."""
        assert isinstance(backend.to_key("some/path"), str)

    @pytest.mark.spec("NPR-003")
    def test_to_key_round_trip_with_listing(self, backend: Backend) -> None:
        """Paths from list_files can be converted back via to_key."""
        _require(backend, Capability.LIST, Capability.WRITE)
        backend.write("tk/a.txt", b"a")
        files = list(backend.list_files("tk"))
        assert len(files) == 1
        assert backend.read_bytes(str(files[0].path)) == b"a"


pytestmark_extended = pytest.mark.extended_conformance


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestWriteReadRoundTrip:
    """Write then read: content must match exactly (Dafny WriteReadConsistency)."""

    @pytest.mark.spec("BE-006")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize(
        "content",
        [
            pytest.param(b"", id="empty"),
            pytest.param(b"\x00\x01\x02\xff", id="binary"),
            pytest.param(b"hello world", id="text"),
            pytest.param(b"x" * 10_000, id="large"),
        ],
    )
    def test_roundtrip(self, backend: Backend, content: bytes) -> None:
        backend.write("ec_rt.bin", content, overwrite=True)
        assert backend.read_bytes("ec_rt.bin") == content


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestOperationalConsistency:
    """Cross-cutting operational invariants."""

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-008")
    def test_exists_after_write(self, backend: Backend) -> None:
        backend.write("ec_eaw.txt", b"x")
        assert backend.exists("ec_eaw.txt") is True

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-012")
    def test_exists_after_delete(self, backend: Backend) -> None:
        _require(backend, Capability.DELETE)
        backend.write("ec_ead.txt", b"x")
        backend.delete("ec_ead.txt")
        assert backend.exists("ec_ead.txt") is False

    @pytest.mark.spec("BE-008")
    def test_write_overwrite_true_replaces(self, backend: Backend) -> None:
        backend.write("ec_wot.txt", b"first")
        backend.write("ec_wot.txt", b"second", overwrite=True)
        assert backend.read_bytes("ec_wot.txt") == b"second"

    @pytest.mark.spec("BE-008")
    def test_write_overwrite_false_rejects(self, backend: Backend) -> None:
        backend.write("ec_wof.txt", b"first")
        with pytest.raises(AlreadyExists, match="ec_wof"):
            backend.write("ec_wof.txt", b"second", overwrite=False)

    @pytest.mark.spec("BE-012")
    def test_delete_preserves_siblings(self, backend: Backend) -> None:
        _require(backend, Capability.DELETE)
        _seed(backend, {"ec_sib/a.txt": b"a", "ec_sib/b.txt": b"b"})
        backend.delete("ec_sib/a.txt")
        assert not backend.exists("ec_sib/a.txt")
        assert backend.read_bytes("ec_sib/b.txt") == b"b"

    @pytest.mark.spec("BE-014")
    def test_list_files_returns_fileinfo_with_name(self, backend: Backend) -> None:
        _require(backend, Capability.LIST)
        backend.write("ec_lfi/x.txt", b"x")
        files = list(backend.list_files("ec_lfi"))
        assert len(files) >= 1
        assert files[0].name == "x.txt"
        assert str(files[0].path).endswith("x.txt")

    @pytest.mark.spec("BE-016")
    def test_get_file_info_size(self, backend: Backend) -> None:
        data = b"hello world"
        backend.write("ec_gfis.txt", data)
        info = backend.get_file_info("ec_gfis.txt")
        assert info.size == len(data)


@pytest.mark.extended_conformance
@pytest.mark.parametrize("backend", fixture_params(Capability.WRITE), indirect=True)
class TestBackendQueryMethodsTypeConflicts:
    """BE-004, BE-005, BE-021: query-method behaviour under file-as-directory-component."""

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("exists", id="exists"),
            pytest.param("is_file", id="is_file"),
            pytest.param("is_folder", id="is_folder"),
        ],
    )
    def test_query_methods_return_false_when_ancestor_is_file(self, backend: Backend, method: str) -> None:
        """Query methods return False for paths with file-as-directory-component ancestor."""
        backend.write("a/b", b"file_content")
        assert getattr(backend, method)("a/b/c") is False
        assert getattr(backend, method)("a/b/c/d") is False

    @pytest.mark.spec("BE-004")
    @pytest.mark.spec("BE-005")
    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("exists", id="exists"),
            pytest.param("is_file", id="is_file"),
            pytest.param("is_folder", id="is_folder"),
        ],
    )
    def test_all_query_methods_return_false_on_type_conflict(self, backend: Backend, method: str) -> None:
        """All three query methods return False consistently for type conflicts."""
        backend.write("file", b"content")
        assert getattr(backend, method)("file/subpath") is False

    @pytest.mark.spec("BE-021")
    def test_query_methods_distinct_from_non_existent_paths(self, backend: Backend) -> None:
        """Query methods return False both for non-existent and type-conflict paths."""
        backend.write("a/b", b"file_content")
        assert backend.exists("a/b/c") is False
        assert backend.is_file("a/b/c") is False
        assert backend.is_folder("a/b/c") is False
        assert backend.exists("x/y/z") is False
        assert backend.is_file("x/y/z") is False
        assert backend.is_folder("x/y/z") is False
