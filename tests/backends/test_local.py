"""Local backend specific tests."""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import InvalidPath
from remote_store._models import WriteResult
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
    """Local backend capabilities — all except USER_METADATA and WRITE_RESULT_NATIVE."""

    @pytest.mark.spec("WR-004", "WR-010")
    def test_excludes_write_result_native_and_user_metadata(self, local_backend: LocalBackend) -> None:
        assert not local_backend.capabilities.supports(Capability.WRITE_RESULT_NATIVE)
        assert not local_backend.capabilities.supports(Capability.USER_METADATA)

    def test_supports_all_other_capabilities(self, local_backend: LocalBackend) -> None:
        excluded = {Capability.WRITE_RESULT_NATIVE, Capability.USER_METADATA}
        for cap in Capability:
            if cap not in excluded:
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
            # Use the backend's own root representation so the comparison is
            # robust to Windows short-path (8.3) normalisation of `tmp`.
            assert backend.to_key(backend.native_path("")) == ""

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

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="symlink creation requires SeCreateSymbolicLinkPrivilege on Windows",
    )
    def test_glob_skips_symlink_escaping_root(self) -> None:
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as root:
            backend = LocalBackend(root=root)
            # Create a real file outside root
            outside_file = Path(outside) / "secret.txt"
            outside_file.write_bytes(b"secret")
            # Create a symlink inside root pointing to the outside file
            symlink = Path(root) / "escape.txt"
            try:
                symlink.symlink_to(str(outside_file))
            except OSError:
                pytest.skip("symlink creation not permitted on this platform")
            # glob should return no files (symlink target is outside root)
            results = list(backend.glob("*.txt"))
            assert all(r.name != "secret.txt" for r in results)


class TestLocalBackendOpenAtomicPermission:
    """open_atomic() maps PermissionError from mkstemp to PermissionDenied (lines 206-207)."""

    def test_open_atomic_permission_denied_during_mkstemp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from remote_store._errors import PermissionDenied
        from remote_store.backends import _local as local_mod

        def _raise_permission(*_args: object, **_kwargs: object) -> tuple[int, str]:
            raise PermissionError("simulated permission denied")

        with tempfile.TemporaryDirectory() as root:
            backend = LocalBackend(root=root)
            monkeypatch.setattr(local_mod.tempfile, "mkstemp", _raise_permission)
            with (
                pytest.raises(PermissionDenied, match="Permission denied"),
                backend.open_atomic("file.txt"),
            ):
                pass


# ---------------------------------------------------------------------------
# WriteResult (WR-001, WR-003, WR-004)
# ---------------------------------------------------------------------------


class TestLocalWriteResult:
    """LocalBackend.write/write_atomic return a valid WriteResult (source='basic')."""

    @pytest.mark.spec("WR-001")
    @pytest.mark.spec("WR-004")
    def test_write_bytes_returns_write_result(self, local_backend: LocalBackend) -> None:
        from remote_store._path import RemotePath

        result = local_backend.write("f.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.source == "basic"
        assert result.path == RemotePath("f.txt")
        assert result.size == 5

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"hello world", 11), (b"", 0)])
    def test_write_bytes_size(self, local_backend: LocalBackend, payload: bytes, expected_size: int) -> None:
        result = local_backend.write("f.txt", payload)
        assert result.size == expected_size

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"streamed", 8), (b"", 0)])
    def test_write_binaryio_size(self, local_backend: LocalBackend, payload: bytes, expected_size: int) -> None:
        result = local_backend.write("f.txt", io.BytesIO(payload))
        assert result.size == expected_size

    @pytest.mark.spec("WR-001")
    def test_write_atomic_returns_write_result(self, local_backend: LocalBackend) -> None:
        from remote_store._path import RemotePath

        result = local_backend.write_atomic("f.txt", b"data")
        assert isinstance(result, WriteResult)
        assert result.source == "basic"
        assert result.path == RemotePath("f.txt")
        assert result.size == 4
