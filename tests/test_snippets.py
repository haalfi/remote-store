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
        keys = [k.encode() for k in sorted(self._hashes) if fnmatch.fnmatchcase(k, match)]
        return 0, keys

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


@pytest.fixture
def guide_redis_store(monkeypatch: pytest.MonkeyPatch):
    """The guide's RedisBackend wrapped in Store, backed by the fake client."""
    import examples.snippets.custom_backend_guide as cbg
    from remote_store import Store

    monkeypatch.setattr(cbg, "redis", _FakeRedisModule)
    backend = cbg.RedisBackend(url="redis://localhost:6379/0", prefix="rs:")
    return Store(backend=backend)


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

        recursive = {f.name for f in store.list_files("a", recursive=True)}
        assert recursive == {"1.txt", "2.txt", "deep.txt"}

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
