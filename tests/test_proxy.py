"""Tests for ProxyStore — delegation and child propagation coverage."""

from __future__ import annotations

import pytest

from remote_store import Store
from remote_store._capabilities import Capability
from remote_store._proxy import ProxyStore
from remote_store.backends._local import LocalBackend

pytestmark = pytest.mark.os_sensitive

# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------


class _TestProxy(ProxyStore):
    """Minimal ProxyStore subclass that implements _wrap_child."""

    def _wrap_child(self, inner_child: Store) -> _TestProxy:
        return _TestProxy(inner_child)


@pytest.fixture
def inner(tmp_path: object) -> Store:
    backend = LocalBackend(str(tmp_path))
    s = Store(backend)
    s.write("hello.txt", b"hello world")
    s.write("dir/sub.txt", b"sub content")
    return s


@pytest.fixture
def proxy(inner: Store) -> _TestProxy:
    return _TestProxy(inner)


# ---------------------------------------------------------------------------
# Construction & properties
# ---------------------------------------------------------------------------


class TestProxyConstruction:
    def test_inner_property(self, proxy: _TestProxy, inner: Store) -> None:
        assert proxy.inner is inner

    def test_backend_is_shared(self, proxy: _TestProxy, inner: Store) -> None:
        inner.write("shared.txt", b"shared")
        assert proxy.read_bytes("shared.txt") == b"shared"

    def test_does_not_own_backend(self, proxy: _TestProxy, inner: Store) -> None:
        proxy.close()
        assert inner.read_bytes("hello.txt") == b"hello world"


class TestWrapChild:
    def test_base_wrap_child_raises(self, inner: Store) -> None:
        base = ProxyStore.__new__(ProxyStore)
        base._inner = inner
        base._backend = inner._backend
        base._root = inner._root
        base._owns_backend = False
        with pytest.raises(NotImplementedError):
            base._wrap_child(inner)


# ---------------------------------------------------------------------------
# Delegation — reading
# ---------------------------------------------------------------------------


class TestReadDelegation:
    def test_read(self, proxy: _TestProxy) -> None:
        stream = proxy.read("hello.txt")
        assert stream.read() == b"hello world"
        stream.close()

    def test_read_bytes(self, proxy: _TestProxy) -> None:
        assert proxy.read_bytes("hello.txt") == b"hello world"

    def test_read_seekable(self, proxy: _TestProxy) -> None:
        stream = proxy.read_seekable("hello.txt")
        assert stream.read() == b"hello world"
        stream.seek(0)
        assert stream.read() == b"hello world"
        stream.close()

    def test_read_text(self, proxy: _TestProxy) -> None:
        assert proxy.read_text("hello.txt") == "hello world"


# ---------------------------------------------------------------------------
# Delegation — writing
# ---------------------------------------------------------------------------


class TestWriteDelegation:
    def test_write(self, proxy: _TestProxy) -> None:
        proxy.write("new.txt", b"new content")
        assert proxy.read_bytes("new.txt") == b"new content"

    def test_write_text(self, proxy: _TestProxy) -> None:
        proxy.write_text("text.txt", "text content")
        assert proxy.read_text("text.txt") == "text content"

    def test_write_atomic(self, proxy: _TestProxy) -> None:
        proxy.write_atomic("atomic.txt", b"atomic content")
        assert proxy.read_bytes("atomic.txt") == b"atomic content"

    def test_open_atomic(self, proxy: _TestProxy) -> None:
        with proxy.open_atomic("opened.txt") as f:
            f.write(b"opened content")
        assert proxy.read_bytes("opened.txt") == b"opened content"


# ---------------------------------------------------------------------------
# Delegation — deleting
# ---------------------------------------------------------------------------


class TestDeleteDelegation:
    def test_delete(self, proxy: _TestProxy) -> None:
        proxy.write("del.txt", b"data")
        proxy.delete("del.txt")
        assert not proxy.exists("del.txt")

    def test_delete_folder(self, proxy: _TestProxy) -> None:
        proxy.delete_folder("dir", recursive=True)
        assert not proxy.exists("dir/sub.txt")


# ---------------------------------------------------------------------------
# Delegation — listing and iteration
# ---------------------------------------------------------------------------


class TestListDelegation:
    def test_list_files(self, proxy: _TestProxy) -> None:
        files = list(proxy.list_files("", recursive=True))
        assert len(files) >= 2

    def test_list_folders(self, proxy: _TestProxy) -> None:
        folders = list(proxy.list_folders(""))
        names = {f.name for f in folders}
        assert "dir" in names

    @pytest.mark.spec("STORE-017")
    def test_list_folders_pattern(self, proxy: _TestProxy) -> None:
        matched = list(proxy.list_folders("", pattern="dir"))
        assert len(matched) == 1
        assert matched[0].name == "dir"
        # If pattern were silently dropped, this would also yield "dir" instead of [].
        no_match = list(proxy.list_folders("", pattern="nonexistent"))
        assert no_match == []

    def test_iter_children(self, proxy: _TestProxy) -> None:
        children = list(proxy.iter_children(""))
        assert len(children) >= 2

    def test_glob(self, proxy: _TestProxy) -> None:
        files = list(proxy.glob("**/*.txt"))
        assert len(files) >= 2


# ---------------------------------------------------------------------------
# Delegation — file operations
# ---------------------------------------------------------------------------


class TestFileOpsDelegation:
    def test_move(self, proxy: _TestProxy) -> None:
        proxy.write("src.txt", b"data")
        proxy.move("src.txt", "dst.txt")
        assert proxy.exists("dst.txt")
        assert not proxy.exists("src.txt")

    def test_copy(self, proxy: _TestProxy) -> None:
        proxy.copy("hello.txt", "copy.txt")
        assert proxy.read_bytes("copy.txt") == b"hello world"


# ---------------------------------------------------------------------------
# Delegation — metadata
# ---------------------------------------------------------------------------


class TestMetadataDelegation:
    def test_exists(self, proxy: _TestProxy) -> None:
        assert proxy.exists("hello.txt") is True
        assert proxy.exists("nope.txt") is False

    def test_is_file(self, proxy: _TestProxy) -> None:
        assert proxy.is_file("hello.txt") is True
        assert proxy.is_file("dir") is False

    def test_is_folder(self, proxy: _TestProxy) -> None:
        assert proxy.is_folder("dir") is True

    def test_get_file_info(self, proxy: _TestProxy) -> None:
        info = proxy.get_file_info("hello.txt")
        assert info.size == 11

    def test_get_folder_info(self, proxy: _TestProxy) -> None:
        info = proxy.get_folder_info("")
        assert info.file_count >= 2


# ---------------------------------------------------------------------------
# Delegation — lifecycle
# ---------------------------------------------------------------------------


class TestLifecycleDelegation:
    def test_ping(self, proxy: _TestProxy) -> None:
        result = proxy.ping()
        assert result is None

    def test_close(self, proxy: _TestProxy) -> None:
        result = proxy.close()
        assert result is None


# ---------------------------------------------------------------------------
# Delegation — interop
# ---------------------------------------------------------------------------


class TestInteropDelegation:
    def test_unwrap_delegates(self, proxy: _TestProxy) -> None:
        from remote_store._errors import CapabilityNotSupported

        with pytest.raises(CapabilityNotSupported):
            proxy.unwrap(str)

    def test_native_path(self, proxy: _TestProxy) -> None:
        path = proxy.native_path("hello.txt")
        assert isinstance(path, str)
        assert "hello.txt" in path

    def test_to_key(self, proxy: _TestProxy) -> None:
        key = proxy.to_key("hello.txt")
        assert key == "hello.txt"

    def test_supports(self, proxy: _TestProxy) -> None:
        assert proxy.supports(Capability.READ) is True


# ---------------------------------------------------------------------------
# child() propagation
# ---------------------------------------------------------------------------


class TestChildPropagation:
    def test_child_returns_proxy(self, proxy: _TestProxy) -> None:
        child = proxy.child("dir")
        assert isinstance(child, _TestProxy)
        assert child.read_bytes("sub.txt") == b"sub content"

    def test_child_reads_inner_data(self, proxy: _TestProxy) -> None:
        child = proxy.child("dir")
        assert child.read_bytes("sub.txt") == b"sub content"


# ---------------------------------------------------------------------------
# __eq__ and __hash__ (BK-143)
# ---------------------------------------------------------------------------


class TestProxyEquality:
    """BK-143: ProxyStore.__eq__ and __hash__ contract."""

    @pytest.mark.spec("BK-143")
    def test_equal_when_same_inner(self, inner: Store) -> None:
        """Two proxies of the same type wrapping the same inner store are equal."""
        p1 = _TestProxy(inner)
        p2 = _TestProxy(inner)
        assert p1 == p2

    @pytest.mark.spec("BK-143")
    def test_not_equal_when_different_inner(self, tmp_path: object) -> None:
        """Two proxies wrapping different inner stores are not equal."""
        import tempfile

        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            s1 = Store(LocalBackend(d1))
            s2 = Store(LocalBackend(d2))
            assert _TestProxy(s1) != _TestProxy(s2)

    @pytest.mark.spec("BK-143")
    def test_not_equal_to_unrelated_type(self, proxy: _TestProxy) -> None:
        """Comparing a proxy to an unrelated type returns False."""
        assert proxy != "not a proxy"
        assert proxy != 42

    @pytest.mark.spec("BK-143")
    def test_hash_equal_when_proxies_are_equal(self, inner: Store) -> None:
        """Equal proxies must have equal hashes."""
        p1 = _TestProxy(inner)
        p2 = _TestProxy(inner)
        assert p1 == p2
        assert hash(p1) == hash(p2)

    @pytest.mark.spec("BK-143")
    def test_usable_in_set(self, inner: Store) -> None:
        """Proxy can be stored in a set; two equal proxies deduplicate."""
        p1 = _TestProxy(inner)
        p2 = _TestProxy(inner)
        assert len({p1, p2}) == 1


# ---------------------------------------------------------------------------
# WR-018: write* return WriteResult, head() forwarding
# ---------------------------------------------------------------------------


class TestWriteResultProxy:
    """WR-018: ProxyStore forwards write* return values and head()."""

    @pytest.mark.spec("WR-018")
    @pytest.mark.parametrize(
        ("method", "args", "expected_size"),
        [
            ("write", ("new.txt", b"content"), 7),
            ("write_text", ("new.txt", "text"), 4),
            ("write_atomic", ("new.txt", b"atomic"), 6),
        ],
    )
    def test_write_methods_return_write_result(
        self,
        proxy: _TestProxy,
        method: str,
        args: tuple[object, ...],
        expected_size: int,
    ) -> None:
        from remote_store._models import WriteResult

        result = getattr(proxy, method)(*args)
        assert isinstance(result, WriteResult)
        assert result.size == expected_size

    @pytest.mark.spec("WR-018")
    def test_head_forwards_to_inner(self, proxy: _TestProxy, inner: Store) -> None:
        from remote_store._models import WriteResult

        result = proxy.head("hello.txt")
        inner_result = inner.head("hello.txt")
        assert isinstance(result, WriteResult)
        assert result.source == "sidecar"
        assert result.path == inner_result.path
        assert result.size == inner_result.size

    @pytest.mark.spec("WR-018")
    def test_write_result_is_forwarded_unchanged(self, proxy: _TestProxy, inner: Store) -> None:
        """ProxyStore.write() returns the inner store's WriteResult directly."""
        from unittest.mock import patch

        from remote_store._models import WriteResult
        from remote_store._path import RemotePath

        sentinel = WriteResult(path=RemotePath("new.txt"), size=3, source="basic")
        with patch.object(inner, "write", return_value=sentinel):
            result = proxy.write("new.txt", b"abc")
        assert result is sentinel

    @pytest.mark.spec("WR-018")
    def test_write_metadata_forwarded_to_inner(self, proxy: _TestProxy, inner: Store) -> None:
        """metadata= kwarg passes through proxy to the inner store."""
        from unittest.mock import patch

        from remote_store._models import WriteResult
        from remote_store._path import RemotePath

        sentinel = WriteResult(path=RemotePath("m.txt"), size=4, source="basic")
        with patch.object(inner, "write", return_value=sentinel) as mock_write:
            proxy.write("m.txt", b"data", metadata={"tag": "val"})
        mock_write.assert_called_once()
        _, kwargs = mock_write.call_args
        assert kwargs.get("metadata") == {"tag": "val"}
