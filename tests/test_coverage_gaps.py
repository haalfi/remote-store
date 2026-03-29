"""Tests covering specific uncovered code paths to bring coverage above 95%."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RegistryConfig, Secret
from remote_store._errors import (
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderInfo
from remote_store._path import RemotePath
from remote_store._registry import Registry
from remote_store._store import Store
from remote_store._types import Extras, PathLike, WritableContent
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

from .conftest import make_restricted_store

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


# region: _types.py — verify type aliases are importable and usable
@pytest.mark.parametrize("alias", [WritableContent, PathLike, Extras])
def test_type_aliases_importable(alias: Any) -> None:
    assert alias is not None


# endregion


@pytest.fixture
def local_backend():
    """LocalBackend in a temporary directory, cleaned up automatically."""
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalBackend(root=tmp), tmp


# region: _store.py — repr, empty path, context manager, root validation, equality
class TestStoreBehavior:
    """Store repr, empty-path handling, context manager, root validation, equality."""

    def test_repr(self, mem_backend: MemoryBackend) -> None:
        store = Store(backend=mem_backend, root_path="data")
        r = repr(store)
        assert "Store(" in r
        assert "memory" in r
        assert "data" in r

    def test_repr_no_root(self, mem_backend: MemoryBackend) -> None:
        store = Store(backend=mem_backend)
        assert "root_path=''" in repr(store)

    def test_full_path_empty_no_root(self, mem_backend: MemoryBackend) -> None:
        store = Store(backend=mem_backend, root_path="")
        store.write("a.txt", b"data")
        assert store.exists("")
        assert store.is_folder("")
        assert list(store.list_files("")) != []

    def test_full_path_nonempty_no_root(self, mem_backend: MemoryBackend) -> None:
        store = Store(backend=mem_backend, root_path="")
        store.write("sub/a.txt", b"data")
        assert store.exists("sub/a.txt")

    def test_close(self, mem_backend: MemoryBackend) -> None:
        result = Store(backend=mem_backend, root_path="data").close()
        assert result is None

    def test_context_manager(self, mem_backend: MemoryBackend) -> None:
        with Store(backend=mem_backend, root_path="data") as store:
            store.write("a.txt", b"data")
            assert store.exists("a.txt")

    @pytest.mark.parametrize(
        ("root", "match"),
        [
            pytest.param("../escape", r"\.\.", id="dotdot"),
            pytest.param("bad\0path", "null", id="null_byte"),
        ],
    )
    def test_root_path_rejected(self, mem_backend: MemoryBackend, root: str, match: str) -> None:
        with pytest.raises(InvalidPath, match=match):
            Store(backend=mem_backend, root_path=root)

    def test_root_path_normalized(self, mem_backend: MemoryBackend) -> None:
        store = Store(backend=mem_backend, root_path="a//b/./c")
        assert store._root == "a/b/c"

    @pytest.mark.parametrize(
        ("root_a", "root_b", "same_backend", "expected"),
        [
            pytest.param("data", "data", True, True, id="same_root_same_backend"),
            pytest.param("data", "other", True, False, id="diff_root_same_backend"),
        ],
    )
    def test_equality(
        self,
        mem_backend: MemoryBackend,
        root_a: str,
        root_b: str,
        same_backend: bool,
        expected: bool,
    ) -> None:
        b2 = mem_backend if same_backend else MemoryBackend()
        result = Store(backend=mem_backend, root_path=root_a) == Store(backend=b2, root_path=root_b)
        assert result == expected

    def test_different_backend_not_equal(self) -> None:
        assert Store(backend=MemoryBackend(), root_path="data") != Store(backend=MemoryBackend(), root_path="data")

    def test_not_equal_to_non_store(self, mem_store: Store) -> None:
        assert mem_store != "not a store"


_EMPTY_PATH_CASES: list[tuple[str, str, bool]] = [
    ("write", "", False),
    ("write_atomic", "", False),
    ("read", "", False),
    ("read_bytes", "", False),
    ("delete", "", False),
    ("delete_folder", "", False),
    ("delete_folder", ".", False),
    ("write", ".", False),
    ("read_bytes", ".", False),
    ("delete", ".", False),
    ("get_file_info", "", False),
    ("move", "", False),
    ("copy", "", False),
    ("move_dst", "", True),
    ("copy_dst", "", True),
]


@pytest.mark.parametrize(
    ("method", "path", "needs_setup"),
    _EMPTY_PATH_CASES,
    ids=[f"{m}({p!r})" for m, p, _ in _EMPTY_PATH_CASES],
)
def test_empty_path_rejected(method: str, path: str, needs_setup: bool) -> None:
    """File-targeted methods reject empty and dot paths."""
    store = Store(backend=MemoryBackend(), root_path="data")
    if needs_setup:
        store.write("src.txt", b"data")
    with pytest.raises(InvalidPath):  # noqa: PT012
        if method == "move_dst":
            store.move("src.txt", path)
        elif method == "copy_dst":
            store.copy("src.txt", path)
        elif method in ("write", "write_atomic"):
            getattr(store, method)(path, b"data")
        elif method == "delete_folder":
            store.delete_folder(path)
        elif method == "move":
            store.move(path, "dst.txt")
        elif method == "copy":
            store.copy(path, "dst.txt")
        else:
            getattr(store, method)(path)


# endregion


# region: _config.py — TypeError branches in from_dict

_CONFIG_ERROR_CASES = [
    pytest.param({"backends": "bad", "stores": {}}, TypeError, "dicts", id="backends_not_dict"),
    pytest.param({"backends": {}, "stores": "bad"}, TypeError, "dicts", id="stores_not_dict"),
    pytest.param({"backends": {"local": "bad"}, "stores": {}}, TypeError, "Backend config", id="backend_entry"),
    pytest.param({"backends": {}, "stores": {"main": "bad"}}, TypeError, "Store profile", id="store_entry"),
]


@pytest.mark.parametrize(("data", "exc", "match"), _CONFIG_ERROR_CASES)
def test_config_from_dict_errors(data: dict[str, Any], exc: type, match: str) -> None:
    with pytest.raises(exc, match=match):
        RegistryConfig.from_dict(data)


# endregion


# region: _errors.py — repr/str edge cases
class TestErrorRepr:
    """Cover error __repr__ and __str__ branches."""

    @pytest.mark.parametrize(
        ("err", "fragments"),
        [
            pytest.param(
                RemoteStoreError("boom"),
                ["RemoteStoreError('boom')"],
                id="base_no_extras",
            ),
            pytest.param(
                RemoteStoreError("boom", path="a.txt", backend="s3"),
                ["path='a.txt'", "backend='s3'"],
                id="base_with_extras",
            ),
            pytest.param(
                CapabilityNotSupported("msg"),
                ["CapabilityNotSupported('msg')"],
                id="cap_no_extras",
            ),
            pytest.param(
                CapabilityNotSupported("msg", path="p", backend="b", capability="c"),
                ["CapabilityNotSupported", "path='p'", "backend='b'", "capability='c'"],
                id="cap_full",
            ),
        ],
    )
    def test_repr_fragments(self, err: RemoteStoreError, fragments: list[str]) -> None:
        r = repr(err)
        for f in fragments:
            assert f in r

    def test_base_error_str_message_only(self) -> None:
        assert str(RemoteStoreError("just a message")) == "just a message"

    def test_capability_not_supported_str_no_capability(self) -> None:
        assert "nope" in str(CapabilityNotSupported("nope"))

    def test_capability_error_shows_supported(self) -> None:
        caps = CapabilitySet({Capability.READ, Capability.LIST})
        with pytest.raises(CapabilityNotSupported, match="Supported"):
            caps.require(Capability.WRITE, backend="test")


# endregion


# region: _models.py + _path.py + _capabilities.py — equality, hash, immutability, repr
class TestValueObjects:
    """Cover __eq__, __hash__, immutability for models, RemotePath, and CapabilitySet."""

    def test_fileinfo_neq_non_fileinfo(self) -> None:
        fi = FileInfo(path=RemotePath("a.txt"), name="a.txt", size=10, modified_at=NOW)
        assert fi != "not a FileInfo"

    def test_folderinfo_neq_non_folderinfo(self) -> None:
        assert FolderInfo(path=RemotePath("data"), file_count=1, total_size=10) != "not a FolderInfo"

    def test_folderinfo_hash(self) -> None:
        a = FolderInfo(path=RemotePath("data"), file_count=1, total_size=10)
        b = FolderInfo(path=RemotePath("data"), file_count=9, total_size=99)
        assert hash(a) == hash(b)

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param("setattr", id="setattr_blocked"),
            pytest.param("delattr", id="delattr_blocked"),
        ],
    )
    def test_remotepath_immutability(self, action: str) -> None:
        p = RemotePath("a/b")
        with pytest.raises(AttributeError, match="immutable"):  # noqa: PT012
            if action == "setattr":
                p.foo = "bar"  # type: ignore[attr-defined]
            else:
                del p._path  # type: ignore[misc]

    def test_capability_set_repr(self) -> None:
        r = repr(CapabilitySet({Capability.READ, Capability.WRITE}))
        assert "CapabilitySet" in r
        assert "READ" in r
        assert "WRITE" in r


# endregion


# region: _registry.py — repr, unknown backend, bad options, equality
class TestRegistryBehavior:
    """Registry repr, equality, and error paths."""

    def test_repr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = RegistryConfig.from_dict(
                {
                    "backends": {"local": {"type": "local", "options": {"root": tmp}}},
                    "stores": {"data": {"backend": "local", "root_path": "data"}},
                }
            )
            r = repr(Registry(config))
            assert "Registry(" in r
            assert "data" in r

    def test_unknown_backend_type_raises(self) -> None:
        config = RegistryConfig.from_dict(
            {
                "backends": {"bad": {"type": "nonexistent_backend_type"}},
                "stores": {"main": {"backend": "bad"}},
            }
        )
        with pytest.raises(ValueError, match="nonexistent_backend_type"):
            Registry(config).get_store("main")

    def test_bad_backend_options(self) -> None:
        config = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp", "nonexistent_opt": True}}},
                "stores": {"main": {"backend": "local"}},
            }
        )
        with pytest.raises(ValueError, match="Invalid options"):
            Registry(config).get_store("main")

    def test_same_config_equal(self) -> None:
        config = RegistryConfig.from_dict({"backends": {}, "stores": {}})
        assert Registry(config) == Registry(config)

    def test_not_equal_to_non_registry(self) -> None:
        assert Registry() != "not a registry"


# endregion


# region: backend __repr__ — credential masking (AF-008)
class TestBackendRepr:
    """AF-008: Backend __repr__ must mask sensitive fields."""

    def test_local_repr(self, local_backend: tuple[LocalBackend, str]) -> None:
        backend, tmp = local_backend
        real_tmp = str(Path(tmp).resolve())
        r = repr(backend)
        assert "LocalBackend(root=" in r
        assert repr(real_tmp) in r

    def test_memory_repr(self, mem_backend: MemoryBackend) -> None:
        r = repr(mem_backend)
        assert "MemoryBackend(" in r
        assert "files=0" in r
        assert "folders=0" in r

    def test_memory_repr_after_writes(self, mem_backend: MemoryBackend) -> None:
        mem_backend.write("a/b.txt", b"data")
        r = repr(mem_backend)
        assert "files=1" in r
        assert "folders=1" in r


def _s3_with_secrets() -> Any:
    from remote_store.backends._s3 import S3Backend

    return S3Backend(bucket="b", key="AKID", secret="SK", endpoint_url="http://x")


def _s3_no_secrets() -> Any:
    from remote_store.backends._s3 import S3Backend

    return S3Backend(bucket="b")


def _s3pa_with_secrets() -> Any:
    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    return S3PyArrowBackend(bucket="b", key="AKID", secret="SK")


def _s3pa_no_secrets() -> Any:
    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    return S3PyArrowBackend(bucket="b")


def _sftp_with_secrets() -> Any:
    from remote_store.backends._sftp import SFTPBackend

    return SFTPBackend(host="h", password="secret123", pkey="keydata")


def _sftp_no_secrets() -> Any:
    from remote_store.backends._sftp import SFTPBackend

    return SFTPBackend(host="h")


def _azure_with_secrets() -> Any:
    from remote_store.backends._azure import AzureBackend

    return AzureBackend(
        container="c",
        account_name="acct",
        account_key="mykey",
        sas_token="mysas",
        connection_string="conn=str",
        credential="cred_obj",
    )


def _azure_no_secrets() -> Any:
    from remote_store.backends._azure import AzureBackend

    return AzureBackend(container="c", account_url="https://x.blob.core.windows.net")


_MASKING_SET_CASES = [
    pytest.param(
        _s3_with_secrets,
        ["AKID", "SK"],
        ["key='***'", "secret='***'"],
        ["bucket='b'", "endpoint_url='http://x'"],
        id="s3-set",
    ),
    pytest.param(_s3pa_with_secrets, ["AKID", "SK"], ["key='***'", "secret='***'"], [], id="s3pa-set"),
    pytest.param(
        _sftp_with_secrets, ["secret123", "keydata"], ["password='***'", "pkey='***'"], ["host='h'"], id="sftp-set"
    ),
    pytest.param(
        _azure_with_secrets,
        ["mykey", "mysas", "conn=str", "cred_obj"],
        ["account_key='***'", "sas_token='***'", "connection_string='***'", "credential='***'"],
        ["container='c'", "account_name='acct'"],
        id="azure-set",
    ),
]


@pytest.mark.parametrize(("factory", "raw_secrets", "masked", "visible"), _MASKING_SET_CASES)
def test_backend_masks_set_secrets(
    factory: Any,
    raw_secrets: list[str],
    masked: list[str],
    visible: list[str],
) -> None:
    r = repr(factory())
    for raw in raw_secrets:
        assert raw not in r
    for m in masked:
        assert m in r
    for v in visible:
        assert v in r


_MASKING_UNSET_CASES = [
    pytest.param(_s3_no_secrets, ["key=None", "secret=None"], id="s3-unset"),
    pytest.param(_s3pa_no_secrets, ["key=None", "secret=None"], id="s3pa-unset"),
    pytest.param(_sftp_no_secrets, ["password=None", "pkey=None"], id="sftp-unset"),
    pytest.param(
        _azure_no_secrets,
        ["account_key=None", "sas_token=None", "connection_string=None", "credential=None"],
        id="azure-unset",
    ),
]


@pytest.mark.parametrize(("factory", "expected"), _MASKING_UNSET_CASES)
def test_backend_shows_none_for_unset_secrets(factory: Any, expected: list[str]) -> None:
    r = repr(factory())
    for e in expected:
        assert e in r


_SECRET_CASES = [
    pytest.param(
        lambda: __import__("remote_store.backends._s3", fromlist=["S3Backend"]).S3Backend(
            bucket="b", key=Secret("AKID"), secret=Secret("SK")
        ),
        [("_key", "AKID"), ("_secret", "SK")],
        id="s3",
    ),
    pytest.param(
        lambda: __import__("remote_store.backends._s3_pyarrow", fromlist=["S3PyArrowBackend"]).S3PyArrowBackend(
            bucket="b", key=Secret("AKID"), secret=Secret("SK")
        ),
        [("_key", "AKID"), ("_secret", "SK")],
        id="s3pa",
    ),
    pytest.param(
        lambda: __import__("remote_store.backends._sftp", fromlist=["SFTPBackend"]).SFTPBackend(
            host="h", password=Secret("pass123")
        ),
        [("_password", "pass123")],
        id="sftp",
    ),
    pytest.param(
        lambda: __import__("remote_store.backends._azure", fromlist=["AzureBackend"]).AzureBackend(
            container="c",
            account_name="acct",
            account_key=Secret("mykey"),
            sas_token=Secret("tok"),
            connection_string=Secret("conn=str"),
        ),
        [("_account_key", "mykey"), ("_sas_token", "tok"), ("_connection_string", "conn=str")],
        id="azure",
    ),
]


@pytest.mark.spec("SEC-004")
@pytest.mark.parametrize(("factory", "checks"), _SECRET_CASES)
def test_backend_accepts_secret(factory: Any, checks: list[tuple[str, str]]) -> None:
    backend = factory()
    for attr, expected in checks:
        assert getattr(backend, attr) == expected


# endregion


# region: _local.py — delete_folder edge cases, permission errors, write_atomic, unwrap
class TestLocalBackendEdgeCases:
    """Cover delete_folder, write_atomic, unwrap, list, and permission edge cases."""

    def test_delete_non_empty_folder_non_recursive(self, local_backend: tuple[LocalBackend, str]) -> None:
        backend, _ = local_backend
        backend.write("folder/file.txt", b"data")
        with pytest.raises(DirectoryNotEmpty):
            backend.delete_folder("folder", recursive=False)

    def test_delete_folder_path_is_file(self, local_backend: tuple[LocalBackend, str]) -> None:
        backend, _ = local_backend
        backend.write("file.txt", b"data")
        with pytest.raises(NotFound, match="Not a folder"):
            backend.delete_folder("file.txt")

    def test_write_atomic_cleanup_on_failure(self, local_backend: tuple[LocalBackend, str]) -> None:
        backend, _ = local_backend
        original_fdopen = os.fdopen

        def failing_fdopen(fd: int, mode: str = "r") -> Any:
            f = original_fdopen(fd, mode)

            def bad_write(data: bytes) -> int:
                raise OSError("disk full")

            f.write = bad_write
            return f

        with patch("os.fdopen", side_effect=failing_fdopen), pytest.raises(OSError, match="disk full"):
            backend.write_atomic("test.txt", b"data")
        assert not backend.exists("test.txt")

    def test_write_atomic_permission_denied(self, local_backend: tuple[LocalBackend, str]) -> None:
        backend, _ = local_backend
        with patch("tempfile.mkstemp", side_effect=PermissionError("denied")), pytest.raises(PermissionDenied):
            backend.write_atomic("test.txt", b"data")

    def test_unwrap_raises(self, local_backend: tuple[LocalBackend, str]) -> None:
        backend, _ = local_backend
        with pytest.raises(CapabilityNotSupported, match="unwrap"):
            backend.unwrap(dict)

    @pytest.mark.parametrize(
        "method",
        [
            pytest.param("list_files", id="list_files"),
            pytest.param("list_folders", id="list_folders"),
        ],
    )
    def test_list_nonexistent(self, method: str, local_backend: tuple[LocalBackend, str]) -> None:
        backend, _ = local_backend
        assert list(getattr(backend, method)("nonexistent")) == []

    def test_delete_folder_permission_denied(self, local_backend: tuple[LocalBackend, str]) -> None:
        """delete_folder maps OSError to PermissionDenied."""
        backend, _ = local_backend
        backend.write("folder/file.txt", b"data")
        backend.delete("folder/file.txt")
        with (
            patch("pathlib.Path.rmdir", side_effect=OSError("permission error")),
            pytest.raises(PermissionDenied),
        ):
            backend.delete_folder("folder", recursive=False)


_PERM_CASES = [
    pytest.param("builtins.open", True, lambda b: b.read("secret.txt"), id="read"),
    pytest.param("pathlib.Path.read_bytes", True, lambda b: b.read_bytes("secret.txt"), id="read_bytes"),
    pytest.param("pathlib.Path.write_bytes", False, lambda b: b.write("test.txt", b"data"), id="write"),
    pytest.param("pathlib.Path.unlink", True, lambda b: b.delete("file.txt"), id="delete"),
    pytest.param("shutil.move", True, lambda b: b.move("src.txt", "dst.txt"), id="move"),
    pytest.param("shutil.copy2", True, lambda b: b.copy("src.txt", "dst.txt"), id="copy"),
]


@pytest.mark.parametrize(("patch_target", "needs_file", "call"), _PERM_CASES)
def test_local_permission_errors(
    patch_target: str,
    needs_file: bool,
    call: Any,
    local_backend: tuple[LocalBackend, str],
) -> None:
    backend, _ = local_backend
    if needs_file:
        for name in ("secret.txt", "src.txt", "file.txt"):
            backend.write(name, b"data")
    with patch(patch_target, side_effect=PermissionError("denied")), pytest.raises(PermissionDenied):
        call(backend)


# endregion


# region: AF-012 — Store capability gating tests (STORE-006)

_CAPABILITY_GATING_CASES = [
    pytest.param(Capability.READ, lambda s: s.read("test.txt"), "read", id="read"),
    pytest.param(Capability.READ, lambda s: s.read_bytes("test.txt"), "read", id="read_bytes"),
    pytest.param(Capability.WRITE, lambda s: s.write("new.txt", b"data"), "write", id="write"),
    pytest.param(
        Capability.ATOMIC_WRITE, lambda s: s.write_atomic("new.txt", b"data"), "atomic_write", id="write_atomic"
    ),
    pytest.param(Capability.DELETE, lambda s: s.delete("test.txt"), "delete", id="delete"),
    pytest.param(Capability.DELETE, lambda s: s.delete_folder("folder"), "delete", id="delete_folder"),
    pytest.param(Capability.LIST, lambda s: list(s.iter_children("")), "list", id="iter_children"),
    pytest.param(Capability.LIST, lambda s: list(s.list_files("")), "list", id="list_files"),
    pytest.param(Capability.LIST, lambda s: list(s.list_folders("")), "list", id="list_folders"),
    pytest.param(Capability.METADATA, lambda s: s.get_file_info("test.txt"), "metadata", id="get_file_info"),
    pytest.param(Capability.METADATA, lambda s: s.get_folder_info(""), "metadata", id="get_folder_info"),
    pytest.param(Capability.MOVE, lambda s: s.move("test.txt", "moved.txt"), "move", id="move"),
    pytest.param(Capability.COPY, lambda s: s.copy("test.txt", "copied.txt"), "copy", id="copy"),
]


@pytest.mark.spec("STORE-006")
@pytest.mark.parametrize(("capability", "call", "expected_name"), _CAPABILITY_GATING_CASES)
def test_store_capability_gating(capability: Capability, call: Any, expected_name: str) -> None:
    """AF-012: Every Store method raises CapabilityNotSupported when the backend lacks it."""
    store = make_restricted_store(exclude={capability})
    with pytest.raises(CapabilityNotSupported) as exc_info:
        call(store)
    assert exc_info.value.capability == expected_name


@pytest.mark.spec("STORE-006")
def test_capability_error_includes_backend_name() -> None:
    store = make_restricted_store(exclude={Capability.READ})
    with pytest.raises(CapabilityNotSupported) as exc_info:
        store.read("test.txt")
    assert exc_info.value.backend == "memory"


@pytest.mark.spec("STORE-006")
def test_capability_check_before_path_validation() -> None:
    """Capability check fires before _require_file_path validates the path."""
    store = make_restricted_store(exclude={Capability.READ})
    with pytest.raises(CapabilityNotSupported):
        store.read("")


# endregion
