"""Local backend specific tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath
from remote_store.backends._local import LocalBackend

pytestmark = pytest.mark.os_sensitive


@pytest.fixture
def local_backend() -> LocalBackend:
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalBackend(root=tmp)  # type: ignore[misc]


class TestLocalBackendErrorMapping:
    """BE-021: Backend-native exceptions never leak."""

    @pytest.mark.spec("BE-021")
    def test_path_traversal_rejected(self, local_backend: LocalBackend) -> None:
        """Resolved paths must stay within root."""
        with pytest.raises(InvalidPath):
            local_backend.read("../../etc/passwd")

    @pytest.mark.spec("BE-021")
    def test_native_errors_mapped(self, local_backend: LocalBackend) -> None:
        """FileNotFoundError maps to NotFound."""
        from remote_store._errors import NotFound

        with pytest.raises(NotFound):
            local_backend.read_bytes("nonexistent.txt")


class TestLocalBackendIdentity:
    """BE-002: Local backend name."""

    @pytest.mark.spec("BE-002")
    def test_name(self, local_backend: LocalBackend) -> None:
        assert local_backend.name == "local"


class TestLocalBackendCapabilities:
    """Local backend supports all capabilities."""

    def test_supports_all_capabilities(self, local_backend: LocalBackend) -> None:
        for cap in Capability:
            assert local_backend.capabilities.supports(cap), f"Missing: {cap.name}"


class TestLocalBackendResolve:
    """RES-050: LocalBackend.resolve() returns kind='local' with root and absolute_path."""

    @pytest.mark.spec("RES-050")
    def test_kind_is_local(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        assert plan.kind == "local"

    @pytest.mark.spec("RES-050")
    def test_details_has_root(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        assert "root" in plan.details

    @pytest.mark.spec("RES-050")
    def test_details_has_absolute_path(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        assert "absolute_path" in plan.details
        assert "file.txt" in plan.details["absolute_path"]

    @pytest.mark.spec("RES-050")
    def test_details_root_matches_backend(self, local_backend: LocalBackend) -> None:
        plan = local_backend.resolve("file.txt")
        # root in details matches the backend's native root (Path normalizes separators)
        assert Path(plan.details["root"]) == Path(local_backend.native_path(""))


class TestLocalDeleteOnDirectory:
    """BUG-153: delete() on a directory must raise RemoteStoreError, not leak IsADirectoryError."""

    @pytest.mark.spec("BE-021")
    def test_delete_directory_raises_not_found(self, local_backend: LocalBackend) -> None:
        """delete() on a directory path should raise NotFound, not IsADirectoryError."""
        from remote_store._errors import NotFound

        local_backend.write("folder/file.txt", b"hello")
        assert local_backend.is_folder("folder")

        with pytest.raises(NotFound, match="Not a file"):
            local_backend.delete("folder")

    @pytest.mark.spec("BE-021")
    def test_delete_directory_missing_ok_silenced(self, local_backend: LocalBackend) -> None:
        """delete(missing_ok=True) on a directory should be silenced, consistent with MemoryBackend."""
        local_backend.write("folder/file.txt", b"hello")
        assert local_backend.is_folder("folder")

        # Should not raise — missing_ok silences directory paths
        local_backend.delete("folder", missing_ok=True)


class TestLocalReadOnDirectory:
    """BUG-153: read()/read_bytes() on a directory must not leak IsADirectoryError."""

    @pytest.mark.spec("BE-021")
    def test_read_directory_raises_not_found(self, local_backend: LocalBackend) -> None:
        """read() on a directory path should raise NotFound."""
        from remote_store._errors import NotFound

        local_backend.write("folder/file.txt", b"hello")

        with pytest.raises(NotFound, match="Not a file"):
            local_backend.read("folder")

    @pytest.mark.spec("BE-021")
    def test_read_bytes_directory_raises_not_found(self, local_backend: LocalBackend) -> None:
        """read_bytes() on a directory path should raise NotFound."""
        from remote_store._errors import NotFound

        local_backend.write("folder/file.txt", b"hello")

        with pytest.raises(NotFound, match="Not a file"):
            local_backend.read_bytes("folder")


class TestLocalWriteOnDirectory:
    """BUG-154: write/write_atomic/open_atomic on a directory must raise InvalidPath."""

    @pytest.mark.spec("BE-021")
    def test_write_no_overwrite_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """write(overwrite=False) on a directory path should raise InvalidPath, not AlreadyExists."""
        local_backend.write("dir/file.txt", b"hello")
        assert local_backend.is_folder("dir")

        with pytest.raises(InvalidPath, match="exists as a directory"):
            local_backend.write("dir", b"data")

    @pytest.mark.spec("BE-021")
    def test_write_overwrite_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """write(overwrite=True) on a directory path should raise InvalidPath."""
        local_backend.write("dir/file.txt", b"hello")
        assert local_backend.is_folder("dir")

        with pytest.raises(InvalidPath, match="exists as a directory"):
            local_backend.write("dir", b"overwrite", overwrite=True)

    @pytest.mark.spec("BE-021")
    def test_write_atomic_overwrite_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """write_atomic(overwrite=True) on a directory path should raise InvalidPath."""
        local_backend.write("dir/file.txt", b"hello")
        assert local_backend.is_folder("dir")

        with pytest.raises(InvalidPath, match="exists as a directory"):
            local_backend.write_atomic("dir", b"overwrite", overwrite=True)

    @pytest.mark.spec("BE-021")
    def test_open_atomic_overwrite_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """open_atomic(overwrite=True) on a directory path should raise InvalidPath."""
        local_backend.write("dir/file.txt", b"hello")
        assert local_backend.is_folder("dir")

        with (
            pytest.raises(InvalidPath, match="exists as a directory"),
            local_backend.open_atomic("dir", overwrite=True) as f,
        ):
            f.write(b"overwrite")
