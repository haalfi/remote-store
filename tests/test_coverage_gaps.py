"""Tests covering specific uncovered code paths to bring coverage above 95%."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RegistryConfig
from remote_store._errors import (
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo, RemoteFile, RemoteFolder
from remote_store._path import RemotePath
from remote_store._registry import Registry
from remote_store._store import Store
from remote_store._types import Extras, PathLike, WritableContent
from remote_store.backends._local import LocalBackend

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


# region: _types.py — verify type aliases are importable and usable
class TestTypeAliases:
    """Ensure type aliases in _types.py are importable."""

    def test_writable_content_alias(self) -> None:
        assert WritableContent is not None

    def test_pathlike_alias(self) -> None:
        assert PathLike is not None

    def test_extras_alias(self) -> None:
        assert Extras is not None


# endregion


# region: _store.py — __repr__, empty path with no root, _require_file_path, delete_folder("")
class TestStoreRepr:
    """Store.__repr__ for debugging."""

    def test_repr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            r = repr(store)
            assert "Store(" in r
            assert "local" in r
            assert "data" in r

    def test_repr_no_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend)
            assert "root_path=''" in repr(store)


class TestStoreEmptyPathNoRoot:
    """Store with no root_path handles empty path correctly."""

    def test_full_path_empty_no_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="")
            store.write("a.txt", b"data")
            assert store.exists("")
            assert store.is_folder("")
            assert list(store.list_files("")) != []

    def test_full_path_nonempty_no_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="")
            store.write("sub/a.txt", b"data")
            assert store.exists("sub/a.txt")


class TestStoreEmptyPathRejection:
    """File-targeted methods reject empty path."""

    def test_write_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.write("", b"data")

    def test_write_atomic_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.write_atomic("", b"data")

    def test_read_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.read("")

    def test_read_bytes_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.read_bytes("")

    def test_delete_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.delete("")

    def test_delete_folder_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.delete_folder("")

    def test_get_file_info_empty_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.get_file_info("")

    def test_move_empty_src(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.move("", "dst.txt")

    def test_move_empty_dst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            store.write("src.txt", b"data")
            with pytest.raises(InvalidPath):
                store.move("src.txt", "")

    def test_copy_empty_src(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            with pytest.raises(InvalidPath):
                store.copy("", "dst.txt")

    def test_copy_empty_dst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            store.write("src.txt", b"data")
            with pytest.raises(InvalidPath):
                store.copy("src.txt", "")


# endregion


# region: _config.py — TypeError branches in from_dict
class TestConfigFromDictErrors:
    """from_dict() error branches."""

    def test_backends_not_dict(self) -> None:
        with pytest.raises(TypeError, match="dicts"):
            RegistryConfig.from_dict({"backends": "bad", "stores": {}})

    def test_stores_not_dict(self) -> None:
        with pytest.raises(TypeError, match="dicts"):
            RegistryConfig.from_dict({"backends": {}, "stores": "bad"})

    def test_backend_entry_not_dict(self) -> None:
        with pytest.raises(TypeError, match="Backend config"):
            RegistryConfig.from_dict({"backends": {"local": "bad"}, "stores": {}})

    def test_store_entry_not_dict(self) -> None:
        with pytest.raises(TypeError, match="Store profile"):
            RegistryConfig.from_dict({"backends": {}, "stores": {"main": "bad"}})


# endregion


# region: _errors.py — __repr__ edge cases
class TestErrorReprEdgeCases:
    """Cover uncovered __repr__ branches."""

    def test_base_error_repr_no_extras(self) -> None:
        e = RemoteStoreError("boom")
        r = repr(e)
        assert r == "RemoteStoreError('boom')"

    def test_base_error_repr_with_path_and_backend(self) -> None:
        e = RemoteStoreError("boom", path="a.txt", backend="s3")
        r = repr(e)
        assert "path='a.txt'" in r
        assert "backend='s3'" in r

    def test_capability_not_supported_str_no_capability(self) -> None:
        e = CapabilityNotSupported("nope")
        s = str(e)
        assert "nope" in s

    def test_capability_not_supported_repr_full(self) -> None:
        e = CapabilityNotSupported("msg", path="p", backend="b", capability="c")
        r = repr(e)
        assert "CapabilityNotSupported" in r
        assert "path='p'" in r
        assert "backend='b'" in r
        assert "capability='c'" in r

    def test_capability_not_supported_repr_no_extras(self) -> None:
        e = CapabilityNotSupported("msg")
        r = repr(e)
        assert r == "CapabilityNotSupported('msg')"

    def test_base_error_str_message_only(self) -> None:
        e = RemoteStoreError("just a message")
        assert str(e) == "just a message"


# endregion


# region: _models.py — __eq__ NotImplemented, FolderInfo hash
class TestModelEqualityNotImplemented:
    """Cover __eq__ returning NotImplemented for non-model types."""

    def test_fileinfo_neq_non_fileinfo(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=10, modified_at=NOW)
        assert fi != "not a FileInfo"

    def test_folderinfo_neq_non_folderinfo(self) -> None:
        fi = FolderInfo(path=RemotePath("data"), file_count=1, total_size=10)
        assert fi != "not a FolderInfo"

    def test_folderinfo_hash(self) -> None:
        a = FolderInfo(path=RemotePath("data"), file_count=1, total_size=10)
        b = FolderInfo(path=RemotePath("data"), file_count=9, total_size=99)
        assert hash(a) == hash(b)

    def test_remotefile_neq_non_remotefile(self) -> None:
        rf = RemoteFile(path=RemotePath("a.txt"))
        assert rf != "not a RemoteFile"

    def test_remotefolder_neq_non_remotefolder(self) -> None:
        rf = RemoteFolder(path=RemotePath("data"))
        assert rf != 42


# endregion


# region: _capabilities.py — CapabilitySet repr
class TestCapabilitySetRepr:
    """Cover CapabilitySet.__repr__."""

    def test_repr(self) -> None:
        cs = CapabilitySet({Capability.READ, Capability.WRITE})
        r = repr(cs)
        assert "CapabilitySet" in r
        assert "READ" in r
        assert "WRITE" in r


# endregion


# region: _registry.py — __repr__, unknown backend type
class TestRegistryRepr:
    """Registry.__repr__ for debugging."""

    def test_repr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = RegistryConfig.from_dict(
                {
                    "backends": {"local": {"type": "local", "options": {"root": tmp}}},
                    "stores": {"data": {"backend": "local", "root_path": "data"}},
                }
            )
            reg = Registry(config)
            r = repr(reg)
            assert "Registry(" in r
            assert "data" in r


class TestRegistryUnknownBackendType:
    """Cover unknown backend type error path."""

    def test_unknown_backend_type_raises(self) -> None:
        config = RegistryConfig.from_dict(
            {
                "backends": {"bad": {"type": "nonexistent_backend_type"}},
                "stores": {"main": {"backend": "bad"}},
            }
        )
        reg = Registry(config)
        with pytest.raises(ValueError, match="nonexistent_backend_type"):
            reg.get_store("main")


# endregion


# region: _local.py — delete_folder edge cases, _is_fd_closed, non-dir errors
class TestLocalBackendDeleteFolderEdgeCases:
    """Cover delete_folder edge cases."""

    def test_delete_non_empty_folder_non_recursive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("folder/file.txt", b"data")
            with pytest.raises(NotFound, match="not empty"):
                backend.delete_folder("folder", recursive=False)

    def test_delete_folder_path_is_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("file.txt", b"data")
            with pytest.raises(NotFound, match="Not a folder"):
                backend.delete_folder("file.txt")


class TestLocalBackendListEdgeCases:
    """Cover listing on non-directory paths."""

    def test_list_files_on_nonexistent_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            assert list(backend.list_files("nonexistent")) == []

    def test_list_folders_on_nonexistent_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            assert list(backend.list_folders("nonexistent")) == []


class TestLocalBackendPermissionErrors:
    """Cover PermissionError mapping via mocking."""

    def test_read_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("secret.txt", b"data")
            with (
                patch("builtins.open", side_effect=PermissionError("denied")),
                pytest.raises(PermissionDenied),
            ):
                backend.read("secret.txt")

    def test_read_bytes_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("secret.txt", b"data")
            with (
                patch("pathlib.Path.read_bytes", side_effect=PermissionError("denied")),
                pytest.raises(PermissionDenied),
            ):
                backend.read_bytes("secret.txt")

    def test_write_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            with (
                patch("pathlib.Path.write_bytes", side_effect=PermissionError("denied")),
                pytest.raises(PermissionDenied),
            ):
                backend.write("test.txt", b"data")

    def test_delete_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("file.txt", b"data")
            with (
                patch("pathlib.Path.unlink", side_effect=PermissionError("denied")),
                pytest.raises(PermissionDenied),
            ):
                backend.delete("file.txt")

    def test_move_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("src.txt", b"data")
            with (
                patch("shutil.move", side_effect=PermissionError("denied")),
                pytest.raises(PermissionDenied),
            ):
                backend.move("src.txt", "dst.txt")

    def test_copy_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("src.txt", b"data")
            with (
                patch("shutil.copy2", side_effect=PermissionError("denied")),
                pytest.raises(PermissionDenied),
            ):
                backend.copy("src.txt", "dst.txt")

    def test_delete_folder_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            backend.write("folder/file.txt", b"data")
            backend.delete("folder/file.txt")
            with (
                patch("pathlib.Path.rmdir", side_effect=OSError("permission error")),
                pytest.raises(PermissionDenied),
            ):
                backend.delete_folder("folder", recursive=False)


class TestLocalBackendWriteAtomicCleanup:
    """Cover write_atomic error handling paths."""

    def test_write_atomic_cleanup_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            original_fdopen = os.fdopen

            def failing_fdopen(fd, mode="r"):
                f = original_fdopen(fd, mode)
                original_write = f.write

                def bad_write(data: bytes) -> int:
                    raise OSError("disk full")

                f.write = bad_write
                return f

            with patch("os.fdopen", side_effect=failing_fdopen), pytest.raises(OSError, match="disk full"):
                backend.write_atomic("test.txt", b"data")
            # Temp file should be cleaned up
            assert not backend.exists("test.txt")

    def test_write_atomic_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            with patch("tempfile.mkstemp", side_effect=PermissionError("denied")), pytest.raises(PermissionDenied):
                backend.write_atomic("test.txt", b"data")


class TestLocalBackendUnwrap:
    """Cover Backend.unwrap() default implementation."""

    def test_unwrap_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            with pytest.raises(CapabilityNotSupported, match="unwrap"):
                backend.unwrap(dict)


# endregion


# region: _path.py — immutability guards
class TestRemotePathImmutability:
    """Cover __setattr__ and __delattr__."""

    def test_setattr_blocked(self) -> None:
        p = RemotePath("a/b")
        with pytest.raises(AttributeError, match="immutable"):
            p.foo = "bar"  # type: ignore[attr-defined]

    def test_delattr_blocked(self) -> None:
        p = RemotePath("a/b")
        with pytest.raises(AttributeError, match="immutable"):
            del p._path  # type: ignore[misc]


# endregion


# region: new audit items — close/context, __eq__, root_path validation, backend options error
class TestStoreContextManager:
    """Store supports close() and context manager protocol."""

    def test_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="data")
            store.close()  # should not raise

    def test_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            with Store(backend=backend, root_path="data") as store:
                store.write("a.txt", b"data")
                assert store.exists("a.txt")


class TestStoreRootPathValidation:
    """Store constructor validates root_path."""

    def test_root_path_with_dotdot_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            with pytest.raises(InvalidPath, match="\\.\\."):
                Store(backend=backend, root_path="../escape")

    def test_root_path_with_null_byte_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            with pytest.raises(InvalidPath, match="null"):
                Store(backend=backend, root_path="bad\0path")

    def test_root_path_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            store = Store(backend=backend, root_path="a//b/./c")
            assert store._root == "a/b/c"


class TestStoreEquality:
    """Store __eq__ and __hash__."""

    def test_same_store_equal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            a = Store(backend=backend, root_path="data")
            b = Store(backend=backend, root_path="data")
            assert a == b

    def test_different_root_not_equal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalBackend(root=tmp)
            a = Store(backend=backend, root_path="data")
            b = Store(backend=backend, root_path="other")
            assert a != b

    def test_different_backend_not_equal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Store(backend=LocalBackend(root=tmp), root_path="data")
            b = Store(backend=LocalBackend(root=tmp), root_path="data")
            assert a != b  # different backend instances

    def test_not_equal_to_non_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(backend=LocalBackend(root=tmp))
            assert store != "not a store"


class TestRegistryEquality:
    """Registry __eq__."""

    def test_same_config_equal(self) -> None:
        config = RegistryConfig.from_dict({"backends": {}, "stores": {}})
        a = Registry(config)
        b = Registry(config)
        assert a == b

    def test_not_equal_to_non_registry(self) -> None:
        reg = Registry()
        assert reg != "not a registry"


class TestRegistryBadBackendOptions:
    """Registry wraps TypeError from bad backend options."""

    def test_bad_option_key(self) -> None:
        config = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp", "nonexistent_opt": True}}},
                "stores": {"main": {"backend": "local"}},
            }
        )
        reg = Registry(config)
        with pytest.raises(ValueError, match="Invalid options"):
            reg.get_store("main")


class TestCapabilityErrorShowsSupported:
    """Capability error includes supported capabilities."""

    def test_error_lists_supported(self) -> None:
        from remote_store._capabilities import CapabilitySet

        caps = CapabilitySet({Capability.READ, Capability.LIST})
        with pytest.raises(CapabilityNotSupported, match="Supported"):
            caps.require(Capability.WRITE, backend="test")


# endregion
