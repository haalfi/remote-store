"""Tests for documentation code snippets.

Ensures that every snippet script in ``examples/snippets/`` executes
successfully, keeping docs code blocks in sync with the actual API.

See: ID-057 (single-source snippets).
"""

from __future__ import annotations

import fnmatch
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.os_sensitive


class TestHomepageSnippets:
    """Snippets used on the docs landing page (index.md)."""

    @pytest.mark.spec("ID-057")
    def test_homepage_demo(self) -> None:
        from examples.snippets.homepage import demo

        result = demo()
        assert result is None

    @pytest.mark.spec("ID-057")
    def test_homepage_demo_leaves_caller_cwd_untouched(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The core-idea region shows a cwd-relative root, so ``demo()`` runs it
        inside a disposable directory.  A real ``data/`` where the caller happens
        to be standing must survive, and the cwd must be handed back.
        """
        from examples.snippets.homepage import demo

        sentinel = tmp_path / "data" / "keep.txt"
        sentinel.parent.mkdir()
        sentinel.write_text("do not delete me", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        demo()

        assert sentinel.read_text(encoding="utf-8") == "do not delete me"
        # The snippet writes hello.txt into its own ./data; if the isolation
        # regressed it would land in — and its cleanup would erase — this one.
        assert not (tmp_path / "data" / "hello.txt").exists()
        assert Path.cwd().resolve() == tmp_path.resolve()


class TestCoreOperationsSnippets:
    """Snippets used in guides and README."""

    @pytest.mark.spec("ID-057")
    def test_core_operations_demo(self) -> None:
        from examples.snippets.core_operations import demo

        result = demo()
        assert result is None


class TestDagsterGuideSnippets:
    """Snippets used in the Dagster Integration guide."""

    @pytest.mark.spec("DAG-020")
    def test_dagster_guide_demo(self) -> None:
        pytest.importorskip("dagster")

        from examples.snippets.dagster_guide import demo

        result = demo()
        assert result is None


class TestAsyncSyncBridgesSnippets:
    """Snippets used in the Async/Sync Bridges guide."""

    @pytest.mark.spec("ID-143c")
    def test_async_sync_bridges_demo(self) -> None:
        from examples.snippets.async_sync_bridges import demo

        result = demo()
        assert result is None


class TestWriteIntegritySnippets:
    """Snippets used in the Write Integrity guide."""

    @pytest.mark.spec("ID-148")
    def test_write_integrity_demo(self) -> None:
        from examples.snippets.write_integrity import demo

        result = demo()
        assert result is None


class TestAsyncWriteIntegritySnippets:
    """Snippets used in the async section of the Write Integrity guide."""

    @pytest.mark.spec("EW-001")
    def test_async_write_integrity_demo(self) -> None:
        import asyncio

        from examples.snippets.write_integrity_async import demo

        result = asyncio.run(demo())
        assert result is None


class _FakeRedisError(Exception):
    pass


class _FakeRedisConnectionError(_FakeRedisError):
    pass


class _FakeRedisAuthenticationError(_FakeRedisConnectionError):
    """Subclasses ConnectionError, as in redis-py: the order classify() relies on."""


class _FakeRedisTimeoutError(_FakeRedisError):
    pass


class _FakeRedisResponseError(_FakeRedisError):
    pass


class _FakeRedisClient:
    """Dict-backed stand-in covering exactly the calls the snippet makes.

    Mirrors redis-py semantics the snippet relies on: hash fields and
    values come back as ``bytes``, ``scan`` returns ``bytes`` keys in no
    particular order, MATCH globbing treats ``/`` as an ordinary character
    and ``[x]`` as a one-character class, ``COPY`` and ``RENAMENX`` answer
    0 rather than raising, and ``RENAME`` of a missing key raises.
    """

    def __init__(self) -> None:
        self._hashes: dict[str, dict[bytes, bytes]] = {}
        self.closed = False

    @staticmethod
    def _b(value: object) -> bytes:
        return value if isinstance(value, bytes) else str(value).encode()

    def exists(self, key: str) -> int:
        return int(key in self._hashes)

    def hset(self, key: str, mapping: dict) -> None:
        target = self._hashes.setdefault(key, {})
        for field, value in mapping.items():
            target[self._b(field)] = self._b(value)

    def hget(self, key: str, field: str) -> bytes | None:
        return self._hashes.get(key, {}).get(self._b(field))

    def hmget(self, key: str, fields: list[str]) -> list[bytes | None]:
        found = self._hashes.get(key, {})
        return [found.get(self._b(f)) for f in fields]

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._hashes:
                del self._hashes[key]
                removed += 1
        return removed

    def copy(self, source: str, destination: str, replace: bool = False) -> bool:
        if source not in self._hashes or (destination in self._hashes and not replace):
            return False
        self._hashes[destination] = dict(self._hashes[source])
        return True

    def rename(self, src: str, dst: str) -> bool:
        if src not in self._hashes:
            raise _FakeRedisResponseError("no such key")
        self._hashes[dst] = self._hashes.pop(src)
        return True

    def renamenx(self, src: str, dst: str) -> bool:
        if src not in self._hashes:
            raise _FakeRedisResponseError("no such key")
        if dst in self._hashes:
            return False
        self._hashes[dst] = self._hashes.pop(src)
        return True

    def scan(self, cursor: int = 0, match: str = "*", count: int = 10) -> tuple[int, list[bytes]]:
        # Faithful to redis-py: SCAN pages the whole keyspace by ``count``
        # and applies MATCH per page, so a page can be empty while the
        # cursor is still nonzero — the pitfall the snippet's loop handles.
        # Reverse order stands in for "no order": the driver must sort.
        keys = sorted(self._hashes, reverse=True)
        page = keys[cursor : cursor + count]
        next_cursor = cursor + count if cursor + count < len(keys) else 0
        return next_cursor, [k.encode() for k in page if fnmatch.fnmatchcase(k, match)]

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True


class _FakeRedisModule:
    """Stands in for the ``redis`` module inside the snippet."""

    RedisError = _FakeRedisError
    AuthenticationError = _FakeRedisAuthenticationError
    ConnectionError = _FakeRedisConnectionError
    TimeoutError = _FakeRedisTimeoutError
    ResponseError = _FakeRedisResponseError

    class Redis:
        @staticmethod
        def from_url(url: str, **kwargs: object) -> _FakeRedisClient:
            return _FakeRedisClient()


def _backend_with_client(monkeypatch: pytest.MonkeyPatch, client: _FakeRedisClient, **options: object):
    """Build the guide's RedisBackend around a specific (possibly failing) client.

    The ``from_url`` keyword arguments are recorded on ``client.from_url_kwargs``.
    """
    import examples.snippets.custom_backend_guide as cbg

    class _Module(_FakeRedisModule):
        class Redis:
            @staticmethod
            def from_url(url: str, **kwargs: object) -> _FakeRedisClient:
                client.from_url_kwargs = kwargs  # type: ignore[attr-defined]
                return client

    monkeypatch.setattr(cbg, "redis", _Module)
    return cbg.RedisBackend(url="redis://localhost:6379/0", prefix="rs:", **options)


@pytest.fixture
def guide_redis_backend(monkeypatch: pytest.MonkeyPatch):
    """The guide's RedisBackend, backed by the fake client."""
    import examples.snippets.custom_backend_guide as cbg

    monkeypatch.setattr(cbg, "redis", _FakeRedisModule)
    return cbg.RedisBackend(url="redis://localhost:6379/0", prefix="rs:")


@pytest.fixture
def guide_redis_store(guide_redis_backend):
    """The guide's RedisBackend wrapped in Store."""
    from remote_store import Store

    return Store(backend=guide_redis_backend)


def _own_methods(protocol: type) -> list[str]:
    """The public methods a driver protocol declares itself, not inherited ones."""
    return sorted(n for n, v in vars(protocol).items() if inspect.isfunction(v) and not n.startswith("_"))


class TestCustomBackendGuideSnippets:
    """Snippets used in the Build Your Own Backend guide.

    The tutorial ``RedisDriver`` is published as reference code for the
    driver contract, so beyond running ``demo()`` these tests pin the
    driver to the protocols (signature drift) and drive it through the
    kernel and ``Store``.
    """

    @pytest.mark.spec("ID-057")
    def test_custom_backend_guide_demo(self) -> None:
        from examples.snippets.custom_backend_guide import demo

        result = demo()
        assert result is None

    @pytest.mark.spec("ID-057")
    def test_demo_leaves_no_process_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """demo() must restore the cwd and undo its global backend registration."""
        from examples.snippets.custom_backend_guide import demo
        from remote_store._registry import _BACKEND_FACTORIES

        monkeypatch.chdir(tmp_path)
        demo()

        assert Path.cwd().resolve() == tmp_path.resolve()
        assert "redis" not in _BACKEND_FACTORIES  # internal: no public observable

    @pytest.mark.spec("ID-057")
    def test_test_examples_region_executes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Run every test body the test-examples region defines against a fresh store."""
        import examples.snippets.custom_backend_guide as cbg
        from remote_store import Store

        monkeypatch.setattr(cbg, "redis", _FakeRedisModule)
        funcs = cbg._demo_test_examples()
        assert set(funcs) == {
            "test_read_write_roundtrip",
            "test_write_no_overwrite",
            "test_read_missing",
            "test_read_a_folder",
            "test_list_files",
            "test_list_files_recursive",
            "test_list_folders",
        }
        for name, fn in funcs.items():
            backend = cbg.RedisBackend(url="redis://localhost:6379/15", prefix=f"{name}:")
            fn(Store(backend=backend))

    @pytest.mark.spec("ID-057")
    def test_step12_direct_region_executes(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """Run the step12-direct region verbatim against the fake client."""
        import examples.snippets.custom_backend_guide as cbg

        monkeypatch.setattr(cbg, "redis", _FakeRedisModule)
        cbg._demo_direct_usage()
        out = capsys.readouterr().out
        assert "q1.csv: 12 bytes" in out

    @pytest.mark.spec("ID-057")
    def test_driver_signatures_match_the_protocols(self, guide_redis_backend) -> None:
        """Every member the driver implements matches its protocol's signature.

        The guide's quick-reference tables are prose; this is the executable
        version. A parameter added to a driver protocol must show up in the
        tutorial driver, or the kernel breaks any driver written from the guide.
        """
        from examples.snippets.custom_backend_guide import RedisDriver
        from remote_store import drivers

        driver = guide_redis_backend._driver  # internal: the kernel holds the built driver
        assert isinstance(driver, drivers.Driver)
        implemented = [drivers.Driver]
        for name in drivers.__all__:
            proto = getattr(drivers, name)
            if name.startswith("Supports") and isinstance(driver, proto):
                implemented.append(proto)
        assert {p.__name__ for p in implemented} == {"Driver", "SupportsCopy", "SupportsRename"}

        for proto in implemented:
            for name in _own_methods(proto):
                base = [
                    (p.name, p.kind, p.default) for p in inspect.signature(getattr(proto, name)).parameters.values()
                ]
                impl = [
                    (p.name, p.kind, p.default)
                    for p in inspect.signature(getattr(RedisDriver, name)).parameters.values()
                ]
                assert impl == base, (
                    f"RedisDriver.{name} drifted from {proto.__name__}:\n  guide: {impl}\n  protocol: {base}"
                )

    @pytest.mark.spec("ID-057")
    def test_store_roundtrip_and_listing(self, guide_redis_store) -> None:
        store = guide_redis_store
        store.write("a/1.txt", b"one")
        store.write("a/2.txt", b"two")
        store.write("a/b/deep.txt", b"deep")
        store.write("top.txt", b"root-level")

        assert store.read_bytes("a/1.txt") == b"one"

        names = {f.name for f in store.list_files("a")}
        assert names == {"1.txt", "2.txt"}

        store.write("a/b/c/deeper.txt", b"deepest")
        recursive = {f.name for f in store.list_files("a", recursive=True)}
        assert recursive == {"1.txt", "2.txt", "deep.txt", "deeper.txt"}

        # The driver knows nothing of max_depth: the kernel filters the walk.
        assert {f.name for f in store.list_files("a", max_depth=0)} == {"1.txt", "2.txt"}
        assert {f.name for f in store.list_files("a", max_depth=1)} == {"1.txt", "2.txt", "deep.txt"}
        assert {f.name for f in store.list_files("a", max_depth=2)} == {"1.txt", "2.txt", "deep.txt", "deeper.txt"}

        assert {f.name for f in store.list_folders("")} == {"a"}
        assert {f.name for f in store.list_folders("a")} == {"b"}

    @pytest.mark.spec("ID-057")
    def test_store_error_contract(self, guide_redis_store) -> None:
        from remote_store import AlreadyExists, DirectoryNotEmpty, NotFound

        store = guide_redis_store
        with pytest.raises(NotFound, match="missing.txt"):
            store.read_bytes("missing.txt")

        store.write("hello.txt", b"first")
        with pytest.raises(AlreadyExists, match="hello.txt"):
            store.write("hello.txt", b"second")

        with pytest.raises(NotFound, match="gone.txt"):
            store.delete("gone.txt")
        store.delete("gone.txt", missing_ok=True)

        store.write("full/child.txt", b"x")
        with pytest.raises(DirectoryNotEmpty, match="full"):
            store.delete_folder("full")
        store.delete_folder("full", recursive=True)
        assert not store.exists("full/child.txt")
        with pytest.raises(NotFound, match="full"):
            store.delete_folder("full")

    @pytest.mark.spec("ID-057")
    def test_kernel_types_the_wrong_kind(self, guide_redis_store) -> None:
        """The driver raises only NotFound; the kernel's probes find the folder or the file."""
        from remote_store import InvalidPath

        store = guide_redis_store
        store.write("dir/file.txt", b"x")
        with pytest.raises(InvalidPath, match="Is a folder, not a file: dir"):
            store.read_bytes("dir")
        with pytest.raises(InvalidPath, match="Is a folder, not a file: dir"):
            store.write("dir", b"over a folder")
        with pytest.raises(InvalidPath, match="An ancestor of the path is a file: dir/file.txt"):
            store.write("dir/file.txt/under", b"under a file")
        with pytest.raises(InvalidPath, match="Is a file, not a folder: dir/file.txt"):
            store.get_folder_info("dir/file.txt")

    @pytest.mark.spec("ID-057")
    def test_store_move_copy_and_metadata(self, guide_redis_store) -> None:
        store = guide_redis_store
        store.write("src.txt", b"hello")
        store.move("src.txt", "dst.txt")
        assert not store.exists("src.txt")
        assert store.read_bytes("dst.txt") == b"hello"

        store.copy("dst.txt", "copy.txt")
        assert store.read_bytes("copy.txt") == b"hello"

        info = store.get_file_info("dst.txt")
        assert info.name == "dst.txt"
        assert info.size == 5

        store.write("agg/a.txt", b"aa")
        store.write("agg/b.txt", b"bbb")
        folder = store.get_folder_info("agg")
        assert folder.file_count == 2
        assert folder.total_size == 5

    @pytest.mark.spec("ID-057")
    def test_untyped_copy_refusal_is_typed_by_the_kernel(self, guide_redis_backend) -> None:
        """copy() raises a bare RemoteStoreError; the kernel's probes name the cause."""
        from remote_store import AlreadyExists, NotFound

        backend = guide_redis_backend
        backend.write("c1.txt", b"one")
        backend.write("c2.txt", b"two")
        with pytest.raises(AlreadyExists, match="c2.txt"):
            backend.copy("c1.txt", "c2.txt")
        backend.copy("c1.txt", "c2.txt", overwrite=True)
        assert backend.read_bytes("c2.txt") == b"one"
        assert backend.read_bytes("c1.txt") == b"one"
        with pytest.raises(NotFound, match="ghost.txt"):
            backend.copy("ghost.txt", "c3.txt")

    @pytest.mark.spec("ID-057")
    def test_move_through_rename(self, guide_redis_backend) -> None:
        from remote_store import AlreadyExists, NotFound

        backend = guide_redis_backend
        backend.write("m1.txt", b"one")
        backend.write("m2.txt", b"two")
        with pytest.raises(AlreadyExists, match="m2.txt"):
            backend.move("m1.txt", "m2.txt")
        backend.move("m1.txt", "m2.txt", overwrite=True)
        assert backend.read_bytes("m2.txt") == b"one"
        assert not backend.exists("m1.txt")
        with pytest.raises(NotFound, match="ghost.txt"):
            backend.move("ghost.txt", "m3.txt")

    @pytest.mark.spec("ID-057")
    def test_self_op_preserves_data(self, guide_redis_backend) -> None:
        """A self move or copy is the kernel's no-op; the driver never sees it."""
        from remote_store import NotFound

        backend = guide_redis_backend
        for overwrite in (False, True):
            backend.write("self.txt", b"data", overwrite=True)
            backend.move("self.txt", "self.txt", overwrite=overwrite)
            assert backend.read_bytes("self.txt") == b"data"
            backend.copy("self.txt", "self.txt", overwrite=overwrite)
            assert backend.read_bytes("self.txt") == b"data"

        backend.delete("self.txt")
        with pytest.raises(NotFound, match="ghost.txt"):
            backend.move("ghost.txt", "ghost.txt")

    @pytest.mark.spec("ID-057")
    @pytest.mark.parametrize(
        ("operation", "native_exc", "mapped", "match"),
        [
            ("read_bytes", _FakeRedisConnectionError, "BackendUnavailable", "not reachable"),
            ("read_bytes", _FakeRedisTimeoutError, "BackendUnavailable", "not reachable"),
            ("read_bytes", _FakeRedisAuthenticationError, "PermissionDenied", "authentication failed"),
            ("read_bytes", _FakeRedisError, "RemoteStoreError", "Redis error during read_bytes"),
            ("exists", _FakeRedisConnectionError, "BackendUnavailable", "not reachable"),
        ],
    )
    def test_classify_maps_and_never_leaks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        operation: str,
        native_exc: type[Exception],
        mapped: str,
        match: str,
    ) -> None:
        """Step 8's classify, executed: each arm, the base fallback, and a second call site.

        Every client call fails, as a server failure does: a refusal the kernel
        may re-type (PermissionDenied, the base error) is probed with ``stat``,
        and a probe that cannot answer leaves the classified error standing.
        """
        import remote_store as rs

        class _FailClient(_FakeRedisClient):
            pass

        def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise native_exc("simulated")

        for client_method in ("hget", "hmget", "scan", "exists"):
            setattr(_FailClient, client_method, _boom)
        backend = _backend_with_client(monkeypatch, _FailClient())
        op = getattr(backend, operation)
        with pytest.raises(rs.RemoteStoreError, match=match) as caught:
            op("x.txt")
        assert type(caught.value) is getattr(rs, mapped)
        assert isinstance(caught.value.__cause__, native_exc)  # the kernel chains the native error
        assert caught.value.path == "x.txt"
        assert caught.value.backend == "redis"

    @pytest.mark.spec("ID-057")
    def test_lifecycle_and_atomic_writes(self, guide_redis_backend, monkeypatch: pytest.MonkeyPatch) -> None:
        """probe() through check_health(), close(), and the atomic writes put_is_atomic backs."""
        from remote_store import BackendUnavailable, PermissionDenied

        backend = guide_redis_backend
        assert backend.check_health() is None
        assert backend.write_atomic("x.txt", b"data").size == 4
        with backend.open_atomic("y.txt") as f:
            f.write(b"streamed")
        assert backend.read_bytes("y.txt") == b"streamed"

        client = _FakeRedisClient()
        closing = _backend_with_client(monkeypatch, client)
        closing.close()
        assert client.closed

        class _DeadClient(_FakeRedisClient):
            def ping(self) -> bool:
                raise _FakeRedisConnectionError("refused")

        with pytest.raises(BackendUnavailable, match="not reachable"):
            _backend_with_client(monkeypatch, _DeadClient()).check_health()

        class _LockedClient(_FakeRedisClient):
            def ping(self) -> bool:
                raise _FakeRedisAuthenticationError("NOAUTH")

        with pytest.raises(PermissionDenied, match="authentication failed"):
            _backend_with_client(monkeypatch, _LockedClient()).check_health()

    @pytest.mark.spec("ID-057")
    def test_secret_is_revealed_and_retry_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Step 3's constructor: a Secret reaches the client as plain text; retry= is accepted."""
        from remote_store import RetryPolicy, Secret

        client = _FakeRedisClient()
        backend = _backend_with_client(monkeypatch, client, password=Secret("s3cr3t"), retry=RetryPolicy())
        assert client.from_url_kwargs["password"] == "s3cr3t"  # type: ignore[attr-defined]
        assert "s3cr3t" not in repr(backend)

    @pytest.mark.spec("ID-057")
    def test_registry_passes_secret_and_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config wraps `password` in Secret and injects `retry=`; the constructor takes both."""
        import examples.snippets.custom_backend_guide as cbg
        from remote_store import Registry, RegistryConfig, register_backend
        from remote_store._registry import _BACKEND_FACTORIES

        client = _FakeRedisClient()
        _backend_with_client(monkeypatch, client)  # installs the recording fake module
        config = RegistryConfig.from_dict(
            {
                "backends": {
                    "main": {
                        "type": "redis-guide-test",
                        "options": {"url": "redis://h:6379/0", "password": "pw"},
                        "retry": {"max_attempts": 2},
                    }
                },
                "stores": {"s": {"backend": "main"}},
            }
        )
        register_backend("redis-guide-test", cbg.RedisBackend)
        try:
            with Registry(config) as registry:
                registry.get_store("s").write("k.txt", b"v")
                driver = registry._get_backend("main")._driver  # internal: the built driver
                assert driver._retry.max_attempts == 2
            assert client.from_url_kwargs["password"] == "pw"  # type: ignore[attr-defined]
        finally:
            _BACKEND_FACTORIES.pop("redis-guide-test", None)

    @pytest.mark.spec("ID-057")
    @pytest.mark.parametrize(
        ("method", "args", "error", "match"),
        [
            ("write", ("", b"x"), "InvalidPath", "Cannot write to the store root"),
            ("write", ("./", b"x"), "InvalidPath", "Cannot write to the store root"),
            ("move", ("", "dst.txt"), "InvalidPath", "store root is a folder, not a file"),
            ("move", ("src.txt", "./"), "InvalidPath", "Cannot write to the store root"),
            ("copy", ("src.txt", ""), "InvalidPath", "Cannot write to the store root"),
            ("delete", ("",), "InvalidPath", "store root is a folder, not a file"),
            ("delete_folder", ("",), "InvalidPath", "Cannot delete the store root"),
            ("get_file_info", (".",), "InvalidPath", "store root is a folder, not a file"),
            ("read", ("a\\b",), "InvalidPath", "backslash"),
        ],
    )
    def test_kernel_guards_the_root_and_the_key(self, guide_redis_backend, method, args, error, match) -> None:
        """The driver has no root or key guards: the kernel refuses these first."""
        import remote_store as rs

        with pytest.raises(getattr(rs, error), match=match):
            getattr(guide_redis_backend, method)(*args)

    @pytest.mark.spec("ID-057")
    def test_read_returns_seekable_stream(self, guide_redis_store) -> None:
        """The SEEKABLE_READ declaration rests on get() returning BytesIO."""
        store = guide_redis_store
        store.write("s.txt", b"seekme")
        stream = store.read("s.txt")
        assert stream.seekable()
        assert stream.read() == b"seekme"
        stream.seek(0)
        assert stream.read(4) == b"seek"

    @pytest.mark.spec("ID-057")
    def test_scan_pagination_survives_empty_pages(self, guide_redis_backend) -> None:
        """SCAN can return empty pages with a nonzero cursor; the loop must continue.

        120 keys under ``zz/`` come first in the fake's reverse scan order, so
        with its count-sized pages the first page holds no ``aa/`` match.
        """
        backend = guide_redis_backend
        for i in range(120):
            backend.write(f"zz/{i:03}.txt", b"x")
        backend.write("aa/last.txt", b"z")

        assert backend.is_folder("aa")
        assert backend.exists("aa/last.txt")
        assert not backend.is_folder("nothere")
        assert {f.name for f in backend.list_files("aa")} == {"last.txt"}

    @pytest.mark.spec("ID-057")
    def test_match_wildcards_in_keys_are_escaped(self, guide_redis_backend) -> None:
        """A folder named with SCAN wildcards lists only itself."""
        backend = guide_redis_backend
        backend.write("w[1]/a.txt", b"a")
        backend.write("w1/b.txt", b"b")
        backend.write("w*/c.txt", b"c")
        assert {f.name for f in backend.list_files("w[1]")} == {"a.txt"}
        assert {f.name for f in backend.list_files("w*")} == {"c.txt"}

    @pytest.mark.spec("ID-057")
    def test_store_root_invariants(self, guide_redis_store) -> None:
        store = guide_redis_store
        assert store.exists("")
        assert store.is_folder("")
        assert not store.is_file("")


class TestS3BotocoreTuningSnippets:
    """Snippets used in the S3 backend guide's Botocore client tuning section."""

    @pytest.mark.spec("S3-026")
    def test_s3_botocore_tuning_demo(self) -> None:
        # Snippet imports S3Backend, which imports s3fs at module load.
        # Skip cleanly when the s3 extra isn't installed (matches the guard
        # used in tests/backends/s3/test_options.py and test_shared.py).
        pytest.importorskip("s3fs", reason="s3fs not installed")
        pytest.importorskip("botocore", reason="botocore not installed")

        from examples.snippets.s3_botocore_tuning import demo

        result = demo()
        assert result is None
