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


class _FakeRedisAuthenticationError(_FakeRedisError):
    pass


class _FakeRedisConnectionError(_FakeRedisError):
    pass


class _FakeRedisPipeline:
    def __init__(self, client: _FakeRedisClient) -> None:
        self._client = client
        self._ops: list = []

    def hset(self, key: str, mapping: dict) -> None:
        self._ops.append(lambda: self._client.hset(key, mapping=mapping))

    def delete(self, *keys: str) -> None:
        self._ops.append(lambda: self._client.delete(*keys))

    def execute(self) -> None:
        for op in self._ops:
            op()
        self._ops.clear()


class _FakeRedisClient:
    """Dict-backed stand-in covering exactly the calls the snippet makes.

    Mirrors redis-py semantics the snippet relies on: hash fields and
    values come back as ``bytes``, ``scan`` returns ``bytes`` keys, and
    MATCH globbing treats ``/`` as an ordinary character.
    """

    def __init__(self) -> None:
        self._hashes: dict[str, dict[bytes, bytes]] = {}

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

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        return dict(self._hashes.get(key, {}))

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._hashes:
                del self._hashes[key]
                removed += 1
        return removed

    def scan(self, cursor: int = 0, match: str = "*", count: int = 10) -> tuple[int, list[bytes]]:
        # Faithful to redis-py: SCAN pages the whole keyspace by ``count``
        # and applies MATCH per page, so a page can be empty while the
        # cursor is still nonzero — the pitfall the snippet's loops handle.
        keys = sorted(self._hashes)
        page = keys[cursor : cursor + count]
        next_cursor = cursor + count if cursor + count < len(keys) else 0
        return next_cursor, [k.encode() for k in page if fnmatch.fnmatchcase(k, match)]

    def pipeline(self) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self)

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        pass


class _FakeRedisModule:
    """Stands in for the ``redis`` module inside the snippet."""

    RedisError = _FakeRedisError
    AuthenticationError = _FakeRedisAuthenticationError
    ConnectionError = _FakeRedisConnectionError

    class Redis:
        @staticmethod
        def from_url(url: str, decode_responses: bool = False) -> _FakeRedisClient:
            return _FakeRedisClient()


def _backend_with_client(monkeypatch: pytest.MonkeyPatch, client: _FakeRedisClient):
    """Build the guide's RedisBackend around a specific (possibly failing) client."""
    import examples.snippets.custom_backend_guide as cbg

    class _Module(_FakeRedisModule):
        class Redis:
            @staticmethod
            def from_url(url: str, decode_responses: bool = False) -> _FakeRedisClient:
                return client

    monkeypatch.setattr(cbg, "redis", _Module)
    return cbg.RedisBackend(url="redis://localhost:6379/0", prefix="rs:")


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


class TestCustomBackendGuideSnippets:
    """Snippets used in the Build Your Own Backend guide.

    The tutorial ``RedisBackend`` is published as reference code for the
    Backend contract, so beyond running ``demo()`` these tests pin the
    class to the ABC (signature drift, BUG-235) and drive it through
    ``Store`` — the layer that calls backends with the full keyword
    surface (``max_depth=`` included).
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
            "test_list_files",
            "test_list_files_recursive",
            "test_list_folders",
        }
        for name, fn in funcs.items():
            backend = cbg.RedisBackend(url="redis://localhost:6379/15", prefix=f"{name}:")
            fn(Store(backend=backend))

    @pytest.mark.spec("ID-057")
    def test_step13_direct_region_executes(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """Run the step13-direct region verbatim against the fake client."""
        import examples.snippets.custom_backend_guide as cbg

        monkeypatch.setattr(cbg, "redis", _FakeRedisModule)
        cbg._demo_direct_usage()
        out = capsys.readouterr().out
        assert "q1.csv: 12 bytes" in out

    @pytest.mark.spec("ID-057")
    def test_redis_backend_signatures_match_backend_abc(self) -> None:
        """Every abstract member's signature must match the ABC exactly.

        The guide's quick-reference table is prose; this is the executable
        version. A parameter added to the ``Backend`` ABC (e.g.
        ``list_files(max_depth=...)``) must show up in the tutorial class,
        or ``Store`` breaks any backend written from the guide.
        """
        from examples.snippets.custom_backend_guide import RedisBackend
        from remote_store import Backend

        for name in sorted(Backend.__abstractmethods__):
            base_attr = inspect.getattr_static(Backend, name)
            impl_attr = inspect.getattr_static(RedisBackend, name)
            if isinstance(base_attr, property):
                assert isinstance(impl_attr, property), f"RedisBackend.{name} must be a property"
                continue
            base = [(p.name, p.kind, p.default) for p in inspect.signature(getattr(Backend, name)).parameters.values()]
            impl = [
                (p.name, p.kind, p.default) for p in inspect.signature(getattr(RedisBackend, name)).parameters.values()
            ]
            assert impl == base, (
                f"RedisBackend.{name} signature drifted from Backend ABC:\n  guide: {impl}\n  ABC:   {base}"
            )

    @pytest.mark.spec("ID-057")
    def test_store_roundtrip_and_listing(self, guide_redis_store) -> None:
        store = guide_redis_store
        store.write("a/1.txt", b"one")
        store.write("a/2.txt", b"two")
        store.write("a/b/deep.txt", b"deep")
        store.write("top.txt", b"root-level")

        assert store.read_bytes("a/1.txt") == b"one"

        # Non-recursive listing goes through Store, which passes max_depth=.
        names = {f.name for f in store.list_files("a")}
        assert names == {"1.txt", "2.txt"}

        store.write("a/b/c/deeper.txt", b"deepest")
        recursive = {f.name for f in store.list_files("a", recursive=True)}
        assert recursive == {"1.txt", "2.txt", "deep.txt", "deeper.txt"}

        # Depth cutoffs are discriminating: each level adds a file.
        assert {f.name for f in store.list_files("a", max_depth=0)} == {"1.txt", "2.txt"}
        assert {f.name for f in store.list_files("a", max_depth=1)} == {"1.txt", "2.txt", "deep.txt"}
        assert {f.name for f in store.list_files("a", max_depth=2)} == {"1.txt", "2.txt", "deep.txt", "deeper.txt"}

        assert {f.name for f in store.list_folders("")} == {"a"}
        assert {f.name for f in store.list_folders("a")} == {"b"}

    @pytest.mark.spec("ID-057")
    def test_store_error_contract(self, guide_redis_store) -> None:
        from remote_store import AlreadyExists, DirectoryNotEmpty, NotFound

        store = guide_redis_store
        with pytest.raises(NotFound, match="File not found"):
            store.read_bytes("missing.txt")

        store.write("hello.txt", b"first")
        with pytest.raises(AlreadyExists, match="already exists"):
            store.write("hello.txt", b"second")

        with pytest.raises(NotFound, match="File not found"):
            store.delete("gone.txt")
        store.delete("gone.txt", missing_ok=True)

        store.write("full/child.txt", b"x")
        with pytest.raises(DirectoryNotEmpty, match="not empty"):
            store.delete_folder("full")
        store.delete_folder("full", recursive=True)

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
    def test_backend_self_op_preserves_data(self, guide_redis_backend) -> None:
        """The ABC requires move/copy with src == dst to be a data-preserving no-op.

        Backend-level on purpose: Store short-circuits self-ops before the
        backend runs, but the conformance suite calls ``backend.move`` /
        ``backend.copy`` directly, and the guide's registration example
        declares ``self_op_supported = true`` — so the tutorial backend
        must satisfy the contract at this layer.
        """
        backend = guide_redis_backend
        from remote_store import NotFound

        for overwrite in (False, True):
            backend.write("self.txt", b"data", overwrite=True)
            backend.move("self.txt", "self.txt", overwrite=overwrite)
            assert backend.read_bytes("self.txt") == b"data"
            backend.copy("self.txt", "self.txt", overwrite=overwrite)
            assert backend.read_bytes("self.txt") == b"data"

        backend.delete("self.txt")
        with pytest.raises(NotFound, match="not found"):
            backend.move("ghost.txt", "ghost.txt")
        with pytest.raises(NotFound, match="not found"):
            backend.copy("ghost.txt", "ghost.txt")

    @pytest.mark.spec("ID-057")
    def test_backend_honors_max_depth_natively(self, guide_redis_backend) -> None:
        """The conformance suite asserts the depth boundary on the backend's own output."""
        backend = guide_redis_backend
        backend.write("pc/a.txt", b"1")
        backend.write("pc/s/b.txt", b"2")
        backend.write("pc/s/t/c.txt", b"3")

        assert {f.name for f in backend.list_files("pc", recursive=True, max_depth=0)} == {"a.txt"}
        files = list(backend.list_files("pc", recursive=True, max_depth=1))
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        for f in files:
            depth = str(f.path).removeprefix("pc/").count("/")
            assert depth <= 1, f"depth boundary violated: {f.path}"
        assert {f.name for f in backend.list_files("pc", recursive=True, max_depth=2)} == {"a.txt", "b.txt", "c.txt"}

        # recursive=False always wins over max_depth (formal contract):
        # immediate children only, whatever the depth limit says.
        assert {f.name for f in backend.list_files("pc", recursive=False, max_depth=2)} == {"a.txt"}

    @pytest.mark.spec("ID-057")
    @pytest.mark.parametrize(
        ("client_method", "native_exc", "mapped", "match"),
        [
            ("hget", _FakeRedisConnectionError, "BackendUnavailable", "connection failed"),
            ("hget", _FakeRedisAuthenticationError, "PermissionDenied", "authentication failed"),
            ("hget", _FakeRedisError, "BackendUnavailable", "Redis error"),
            ("exists", _FakeRedisConnectionError, "BackendUnavailable", "connection failed"),
        ],
    )
    def test_error_mapping_never_leaks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        client_method: str,
        native_exc: type[Exception],
        mapped: str,
        match: str,
    ) -> None:
        """Step 4's cardinal rule, executed: native errors map, never leak.

        Covers both classified arms, the catch-all fallback, and a second
        call site (``exists``) beyond the read path.
        """
        import remote_store as rs

        class _FailClient(_FakeRedisClient):
            pass

        def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise native_exc("simulated")

        setattr(_FailClient, client_method, _boom)
        backend = _backend_with_client(monkeypatch, _FailClient())
        op = backend.read_bytes if client_method == "hget" else backend.exists
        with pytest.raises(getattr(rs, mapped), match=match):
            op("x.txt")

    @pytest.mark.spec("ID-057")
    def test_lifecycle_and_atomic_safety_nets(self, guide_redis_backend, monkeypatch: pytest.MonkeyPatch) -> None:
        """Step 12 check_health()/close() arms and Step 7 CapabilityNotSupported nets."""
        from remote_store import BackendUnavailable, CapabilityNotSupported, PermissionDenied

        assert guide_redis_backend.check_health() is None
        guide_redis_backend.close()

        class _DeadClient(_FakeRedisClient):
            def ping(self) -> bool:
                raise _FakeRedisConnectionError("refused")

        backend = _backend_with_client(monkeypatch, _DeadClient())
        with pytest.raises(BackendUnavailable, match="not reachable"):
            backend.check_health()

        class _LockedClient(_FakeRedisClient):
            def ping(self) -> bool:
                raise _FakeRedisAuthenticationError("NOAUTH")

        backend = _backend_with_client(monkeypatch, _LockedClient())
        with pytest.raises(PermissionDenied, match="authentication failed"):
            backend.check_health()

        with pytest.raises(CapabilityNotSupported, match="atomic"):
            guide_redis_backend.write_atomic("x.txt", b"data")
        with pytest.raises(CapabilityNotSupported, match="atomic"), guide_redis_backend.open_atomic("x.txt"):
            pass

    @pytest.mark.spec("ID-057")
    def test_backend_failure_paths(self, guide_redis_store, guide_redis_backend) -> None:
        """Failure paths the tutorial implements beyond the four basics."""
        from remote_store import AlreadyExists, InvalidPath, NotFound

        store = guide_redis_store
        with pytest.raises(NotFound, match="File not found"):
            store.get_file_info("nope.txt")
        with pytest.raises(NotFound, match="Folder not found"):
            store.get_folder_info("nofolder")
        with pytest.raises(NotFound, match="Folder not found"):
            store.delete_folder("nofolder")
        store.delete_folder("nofolder", missing_ok=True)

        store.write("m1.txt", b"one")
        store.write("m2.txt", b"two")
        with pytest.raises(AlreadyExists, match="already exists"):
            store.move("m1.txt", "m2.txt")
        store.move("m1.txt", "m2.txt", overwrite=True)
        assert store.read_bytes("m2.txt") == b"one"
        assert not store.exists("m1.txt")

        with pytest.raises(InvalidPath, match="must not be empty"):
            guide_redis_backend.write("", b"x")

        store.write("f/x.txt", b"x")
        assert store.is_folder("f")
        assert not store.is_folder("missing")
        assert not store.is_file("f")
        info = store.get_file_info("f/x.txt")
        assert (info.name, info.size) == ("x.txt", 1)
        folder = store.get_folder_info("f")
        assert (folder.file_count, folder.total_size) == (1, 1)

    @pytest.mark.spec("ID-057")
    @pytest.mark.parametrize(
        ("method", "args", "error", "match"),
        [
            ("move", ("", "dst.txt"), "InvalidPath", "Source path must not be empty"),
            ("move", ("src.txt", ""), "InvalidPath", "Destination path must not be empty"),
            ("copy", ("", "dst.txt"), "InvalidPath", "Source path must not be empty"),
            ("copy", ("src.txt", ""), "InvalidPath", "Destination path must not be empty"),
            ("delete", ("",), "InvalidPath", "must not be empty"),
            ("delete_folder", ("",), "InvalidPath", "Cannot delete root"),
            ("get_file_info", ("",), "NotFound", "empty path"),
        ],
    )
    def test_backend_guard_clauses(self, guide_redis_backend, method, args, error, match) -> None:
        """The guide states these guards as contract rules; pin each one."""
        import remote_store as rs

        with pytest.raises(getattr(rs, error), match=match):
            getattr(guide_redis_backend, method)(*args)

    @pytest.mark.spec("ID-057")
    def test_copy_overwrite_semantics(self, guide_redis_backend) -> None:
        """copy() must refuse an existing destination unless overwrite=True."""
        from remote_store import AlreadyExists

        backend = guide_redis_backend
        backend.write("c1.txt", b"one")
        backend.write("c2.txt", b"two")
        with pytest.raises(AlreadyExists, match="already exists"):
            backend.copy("c1.txt", "c2.txt")
        backend.copy("c1.txt", "c2.txt", overwrite=True)
        assert backend.read_bytes("c2.txt") == b"one"
        assert backend.read_bytes("c1.txt") == b"one"

    @pytest.mark.spec("ID-057")
    def test_read_returns_seekable_stream(self, guide_redis_store) -> None:
        """The SEEKABLE_READ declaration rests on read() returning BytesIO."""
        store = guide_redis_store
        store.write("s.txt", b"seekme")
        stream = store.read("s.txt")
        assert stream.seekable()
        assert stream.read() == b"seekme"
        stream.seek(0)
        assert stream.read(4) == b"seek"

    @pytest.mark.spec("ID-057")
    def test_scan_pagination_survives_empty_pages(self, guide_redis_backend) -> None:
        """SCAN can return empty pages with a nonzero cursor; the loops must continue.

        120 keys under ``aa/`` sort ahead of ``zz/``, so with the fake's
        count-sized pages the first page contains no ``zz/`` match.
        """
        backend = guide_redis_backend
        for i in range(120):
            backend.write(f"aa/{i:03}.txt", b"x")
        backend.write("zz/last.txt", b"z")

        assert backend.is_folder("zz")
        assert backend.exists("zz/last.txt")
        assert not backend.is_folder("nothere")
        assert {f.name for f in backend.list_files("zz")} == {"last.txt"}

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
