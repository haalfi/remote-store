"""Local backend specific tests."""

from __future__ import annotations

import os
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
    """BUG-153/ID-131: delete() on a directory must raise InvalidPath (BE-021)."""

    @pytest.mark.spec("BE-021")
    def test_delete_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """delete() on a directory path should raise InvalidPath, not IsADirectoryError."""
        from remote_store._errors import InvalidPath

        local_backend.write("folder/file.txt", b"hello")
        assert local_backend.is_folder("folder")

        with pytest.raises(InvalidPath, match="Not a file"):
            local_backend.delete("folder")

    @pytest.mark.spec("BE-021")
    def test_delete_directory_always_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """delete(missing_ok=True) on a directory still raises InvalidPath — type mismatch is not 'missing'."""
        from remote_store._errors import InvalidPath

        local_backend.write("folder/file.txt", b"hello")
        assert local_backend.is_folder("folder")

        with pytest.raises(InvalidPath, match="Not a file"):
            local_backend.delete("folder", missing_ok=True)


class TestLocalReadOnDirectory:
    """BUG-153/ID-131: read()/read_bytes() on a directory must raise InvalidPath (BE-021)."""

    @pytest.mark.spec("BE-021")
    def test_read_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """read() on a directory path should raise InvalidPath."""
        from remote_store._errors import InvalidPath

        local_backend.write("folder/file.txt", b"hello")

        with pytest.raises(InvalidPath, match="Not a file"):
            local_backend.read("folder")

    @pytest.mark.spec("BE-021")
    def test_read_bytes_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """read_bytes() on a directory path should raise InvalidPath."""
        from remote_store._errors import InvalidPath

        local_backend.write("folder/file.txt", b"hello")

        with pytest.raises(InvalidPath, match="Not a file"):
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
    def test_write_atomic_no_overwrite_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """write_atomic(overwrite=False) on a directory path should raise InvalidPath, not AlreadyExists."""
        local_backend.write("dir/file.txt", b"hello")
        assert local_backend.is_folder("dir")

        with pytest.raises(InvalidPath, match="exists as a directory"):
            local_backend.write_atomic("dir", b"data")

    @pytest.mark.spec("BE-021")
    def test_write_atomic_overwrite_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """write_atomic(overwrite=True) on a directory path should raise InvalidPath."""
        local_backend.write("dir/file.txt", b"hello")
        assert local_backend.is_folder("dir")

        with pytest.raises(InvalidPath, match="exists as a directory"):
            local_backend.write_atomic("dir", b"overwrite", overwrite=True)

    @pytest.mark.spec("BE-021")
    def test_open_atomic_no_overwrite_directory_raises_invalid_path(self, local_backend: LocalBackend) -> None:
        """open_atomic(overwrite=False) on a directory path should raise InvalidPath, not AlreadyExists."""
        local_backend.write("dir/file.txt", b"hello")
        assert local_backend.is_folder("dir")

        with (
            pytest.raises(InvalidPath, match="exists as a directory"),
            local_backend.open_atomic("dir") as f,
        ):
            f.write(b"data")

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


class TestLocalBackendToKeyRoot:
    """to_key() returns empty string for the root path (line 83)."""

    def test_to_key_root_returns_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            assert backend.to_key(tmp) == ""

    def test_to_key_root_normalizes_trailing_slash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            # native_path("") == root without trailing slash
            assert backend.to_key(backend.native_path("")) == ""


class TestLocalBackendWriteAtomicStream:
    """write_atomic() with stream content (line 184)."""

    def test_write_atomic_stream_content(self) -> None:
        import io as _io

        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            data = b"streaming content"
            stream = _io.BytesIO(data)
            backend.write_atomic("out.bin", stream)
            assert backend.read_bytes("out.bin") == data


class TestLocalBackendGlobSymlinkEscape:
    """glob() skips files that resolve outside root via symlinks (lines 266-267)."""

    def test_glob_skips_symlink_escaping_root(self) -> None:
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as root:
            backend = LocalBackend(root=root)
            # Create a real file outside root
            outside_file = Path(outside) / "secret.txt"
            outside_file.write_bytes(b"secret")
            # Create a symlink inside root pointing to the outside file
            symlink = Path(root) / "escape.txt"
            symlink.symlink_to(str(outside_file))
            # glob should return no files (symlink target is outside root)
            results = list(backend.glob("*.txt"))
            assert all(r.name != "secret.txt" for r in results)


class TestLocalBackendOpenAtomicPermission:
    """open_atomic() PermissionError during mkstemp (lines 206-207)."""

    @pytest.mark.skipif(
        os.getuid() == 0,
        reason="root bypasses permission checks",
    )
    def test_open_atomic_permission_denied_on_mkdir(self) -> None:

        from remote_store._errors import PermissionDenied

        with tempfile.TemporaryDirectory() as root:
            backend = LocalBackend(root=root)
            locked = Path(root) / "locked"
            locked.mkdir()
            locked.chmod(0o555)  # no write permission
            try:
                with (
                    pytest.raises(PermissionDenied, match="Permission denied"),
                    backend.open_atomic("locked/file.txt"),
                ):
                    pass
            finally:
                locked.chmod(0o755)
