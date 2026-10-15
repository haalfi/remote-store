"""Custom backend guide snippets -- tested source for the Build Your Own Backend guide.

Named regions can be included in the guide via pymdownx.snippets:

    ```python
    ;--8<-- "examples/snippets/custom_backend_guide.py:step1-imports"
    ```

Run directly or via ``hatch run examples`` to verify all snippets.
The Redis driver is syntax-checked on import and driven end to end by
``tests/test_snippets.py`` against a fake Redis client. Usage examples
(Steps 12-13) exercise the patterns with MemoryBackend to avoid
requiring a Redis server.
"""

# ruff: noqa: F401, F811, F821, F841, E402, I001, SIM108, TCH001, TCH002, TCH003
# mypy: ignore-errors
#
# Tutorial source for the Build Your Own Backend guide. Snippet regions
# include partial code (method bodies split across steps, names referenced
# from later steps) that wouldn't pass strict typing as a single file.
# The runtime smoke check at the bottom exercises a subset that does.

# ---------------------------------------------------------------------------
# Step 1: Imports
# ---------------------------------------------------------------------------

# --8<-- [start:step1-imports]
from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING, BinaryIO, ClassVar, Literal, TypeVar

try:
    import redis
except ImportError:  # graceful fallback when redis is not installed
    redis = None  # type: ignore[assignment]

from remote_store import (
    AlreadyExists,
    BackendUnavailable,
    Capability,
    CapabilitySet,
    CapabilityNotSupported,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
    ResolutionPlan,
    RetryPolicy,
    Secret,
)
from remote_store.drivers import Driver, DriverBackend, Entry, Op, Page, PutResult

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

T = TypeVar("T")
# --8<-- [end:step1-imports]

# ---------------------------------------------------------------------------
# Step 2: Declare capabilities
# ---------------------------------------------------------------------------

# --8<-- [start:step2-capabilities]
_REDIS_CAPABILITIES = CapabilitySet(
    {
        Capability.READ,
        Capability.WRITE,
        Capability.DELETE,
        Capability.LIST,
        Capability.MOVE,  # backed by rename() (Step 10)
        Capability.COPY,  # backed by copy() (Step 10)
        Capability.ATOMIC_MOVE,  # RENAME is atomic, and rename_replaces says so
        Capability.ATOMIC_WRITE,  # one HSET is atomic, and put_is_atomic says so
        Capability.METADATA,
        Capability.SEEKABLE_READ,  # get() returns BytesIO, which is always seekable
    }
)
# --8<-- [end:step2-capabilities]


# ---------------------------------------------------------------------------
# Steps 3-10: The RedisDriver class
# ---------------------------------------------------------------------------


# --8<-- [start:step3-driver]
def _glob_escape(text: str) -> str:
    """Escape SCAN MATCH wildcards, so a key holding ``*``, ``?`` or ``[`` matches itself."""
    return "".join(f"[{c}]" if c in "*?[" else c for c in text)


class RedisDriver(Driver):
    """Files as Redis hashes: one hash per file, under a key prefix.

    Each hash holds the fields ``data``, ``size`` and ``modified_at``.
    """

    # -- Step 3: Declarations and constructor -------------------------------

    name: str = "redis"
    namespace: Literal["flat", "hierarchical"] = "flat"  # a key never blocks a prefix
    parents: Literal["none", "implicit", "explicit"] = "none"  # no folder objects
    capabilities: CapabilitySet = _REDIS_CAPABILITIES
    put_is_atomic: bool = True  # put() is one HSET
    close_is_terminal: bool = False  # redis-py reconnects after close()

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "rs:",
        *,
        password: str | Secret | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        # A credential loaded from config arrives wrapped in Secret (Step 12).
        if isinstance(password, Secret):
            password = password.reveal()
        self._client = redis.Redis.from_url(url, password=password, decode_responses=False)
        self._prefix = prefix
        # Map what your client can honour and ignore the rest: RetryPolicy's
        # documented contract. redis-py configures retries on the client.
        self._retry = retry

    # --8<-- [end:step3-driver]

    # -- Step 4: Addressing -------------------------------------------------

    # --8<-- [start:step4-addressing]
    def native_path(self, key: str) -> str:
        """The Redis key of the hash holding *key*."""
        return f"{self._prefix}file:{key}"

    def to_key(self, native_path: str) -> str:
        return native_path.removeprefix(f"{self._prefix}file:")

    def resolve(self, key: str) -> ResolutionPlan:
        return ResolutionPlan(
            kind=self.name,
            backend=self.name,
            key=key,
            native_path=self.native_path(key),
            details={"prefix": self._prefix},
        )

    # --8<-- [end:step4-addressing]

    # -- Step 5: stat and get -----------------------------------------------

    # --8<-- [start:step5-stat-get]
    def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        # Flat: a lookup of the key alone. A folder is the kernel's to find.
        size, modified = self._client.hmget(self.native_path(key), ["size", "modified_at"])
        if size is None:
            return None
        return Entry(
            key=key,
            kind="file",
            size=int(size),
            modified_at=datetime.fromisoformat(modified.decode()),
        )

    def get(self, key: str) -> BinaryIO:
        data = self._client.hget(self.native_path(key), "data")
        if data is None:
            # A folder at the key also lands here: the kernel probes and
            # raises InvalidPath for it, NotFound for nothing.
            raise NotFound(f"Not found: {key}")
        return io.BytesIO(data)

    # --8<-- [end:step5-stat-get]

    # -- Step 6: put and delete ---------------------------------------------

    # --8<-- [start:step6-put-delete]
    def put(
        self,
        key: str,
        content: bytes | BinaryIO,
        *,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
    ) -> PutResult:
        raw = content if isinstance(content, bytes) else content.read()
        target = self.native_path(key)
        # Check-then-set: two writers without overwrite can both pass the check.
        # A production driver closes that window with WATCH/MULTI or a script.
        if not overwrite and self._client.exists(target):
            raise AlreadyExists(f"Already exists: {key}")
        self._client.hset(
            target,
            mapping={"data": raw, "size": len(raw), "modified_at": datetime.now(UTC).isoformat()},
        )
        return PutResult(size=len(raw))

    def delete(self, key: str) -> None:
        if not self._client.delete(self.native_path(key)):
            raise NotFound(f"Not found: {key}")

    # --8<-- [end:step6-put-delete]

    # -- Step 7: list_page --------------------------------------------------

    # --8<-- [start:step7-list-page]
    def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: object | None = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        # SCAN returns keys in no order, and a flat driver owes byte order, so
        # this collects every match, sorts, and returns one page (cursor None).
        # It ignores `limit`, as the shipped Memory driver does. SCAN walks the
        # whole keyspace: a production driver keeps an index per prefix instead.
        base = f"{prefix}/" if prefix else ""
        pattern = _glob_escape(self.native_path(base)) + "*"
        keys: set[str] = set()
        scan_cursor = 0
        while True:
            scan_cursor, found = self._client.scan(cursor=scan_cursor, match=pattern, count=100)
            keys.update(self.to_key(k.decode()) for k in found)
            if scan_cursor == 0:
                break
        entries: list[Entry] = []
        folders: set[str] = set()
        for key in sorted(keys):
            rest = key[len(base) :]
            if delimiter is not None and delimiter in rest:
                folders.add(base + rest.split(delimiter, 1)[0])  # an immediate subfolder
                continue
            entry = self.stat(key)
            if entry is not None:  # gone since the scan
                entries.append(entry)
        return Page(entries=tuple(entries), prefixes=tuple(sorted(folders)))

    # --8<-- [end:step7-list-page]

    # -- Step 8: Error classification ---------------------------------------

    # --8<-- [start:step8-errors]
    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        # Return the error; the kernel raises it, chained to `exc`, and fills
        # in `path` and `backend`. AuthenticationError subclasses
        # ConnectionError in redis-py, so it is tested first.
        if isinstance(exc, redis.AuthenticationError):
            return PermissionDenied(f"Redis authentication failed: {exc}")
        if isinstance(exc, (redis.ConnectionError, redis.TimeoutError)):
            return BackendUnavailable(f"Redis is not reachable: {exc}")
        return RemoteStoreError(f"Redis error during {op.value}: {exc}")

    def container_absent(self, exc: BaseException, *, op: Op) -> bool:
        return False  # a Redis database always exists: there is no container to lose

    def connection_dead(self, exc: BaseException) -> bool:
        return isinstance(exc, redis.ConnectionError)

    # --8<-- [end:step8-errors]

    # -- Step 9: Lifecycle --------------------------------------------------

    # --8<-- [start:step9-lifecycle]
    def probe(self) -> None:
        self._client.ping()  # errors go through classify() like any other

    def close(self) -> None:
        self._client.close()

    def unwrap(self, type_hint: type[T]) -> T:
        if isinstance(self._client, type_hint):
            return self._client
        raise CapabilityNotSupported(
            f"Backend '{self.name}' does not expose native handle of type {type_hint.__name__}.",
            capability="unwrap",
            backend=self.name,
        )

    # --8<-- [end:step9-lifecycle]

    # -- Step 10: Optional protocols ----------------------------------------

    # --8<-- [start:step10-optional]
    # SupportsCopy: backs Capability.COPY (Redis 6.2+ for COPY).
    def copy(self, src: str, dst: str, *, overwrite: bool) -> None:
        if not self._client.copy(self.native_path(src), self.native_path(dst), replace=overwrite):
            # COPY answers 0 for a missing source and for an existing
            # destination alike. Say only that it refused: the kernel probes
            # both keys and raises NotFound or AlreadyExists as they answer.
            raise RemoteStoreError(f"COPY refused: {src} -> {dst}")

    # SupportsRename: backs Capability.MOVE, and ATOMIC_MOVE with rename_replaces.
    rename_replaces: bool = True  # RENAME replaces the destination atomically

    def rename(self, src: str, dst: str, *, replace: bool) -> None:
        source, target = self.native_path(src), self.native_path(dst)
        if replace:
            self._client.rename(source, target)
        elif not self._client.renamenx(source, target):
            raise AlreadyExists(f"Already exists: {dst}")

    # --8<-- [end:step10-optional]


# ---------------------------------------------------------------------------
# Step 11: The backend class
# ---------------------------------------------------------------------------


# --8<-- [start:step11-backend]
class RedisBackend(DriverBackend):
    """Redis-backed file storage on the contract kernel."""

    CAPABILITIES: ClassVar[CapabilitySet] = _REDIS_CAPABILITIES

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "rs:",
        *,
        password: str | Secret | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(RedisDriver(url, prefix, password=password, retry=retry))


# --8<-- [end:step11-backend]


# ---------------------------------------------------------------------------
# Step 12-13: Usage examples (exercised with MemoryBackend)
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    from remote_store import Registry, Store


def _demo_direct_usage() -> None:
    # --8<-- [start:step12-direct]
    from remote_store import Store

    backend = RedisBackend(url="redis://localhost:6379/0", prefix="myapp:")
    store = Store(backend=backend)

    store.write("reports/q1.csv", b"revenue,100\n")
    data = store.read_bytes("reports/q1.csv")
    print(data)  # b'revenue,100\n'

    for info in store.list_files("reports"):
        print(f"{info.name}: {info.size} bytes")
    # --8<-- [end:step12-direct]


def _demo_registry_usage() -> bytes:
    # --8<-- [start:step12-registry]
    from remote_store import Registry, register_backend
    from remote_store.ext.yaml import from_yaml  # needs: pip install "remote-store[yaml]"

    register_backend("redis", RedisBackend)

    config = from_yaml("stores.yaml")
    with Registry(config) as registry:  # closes instantiated backends on exit
        store = registry.get_store("cache")
        store.write("hello.txt", b"from-registry")
        data = store.read_bytes("hello.txt")
    # --8<-- [end:step12-registry]
    return data


def _demo_extensions(store: Store) -> None:
    # --8<-- [start:step13-extensions]
    from remote_store.ext.batch import batch_copy
    from remote_store.ext.cache import cache
    from remote_store.ext.observe import StoreEvent, observe

    events = []

    def my_logging_hook(event: StoreEvent) -> None:
        events.append(event)

    # Observability — my_logging_hook fires after every operation
    # that goes through the observed wrapper
    observed = observe(store, on_any=my_logging_hook)
    observed.write("a.txt", b"alpha")
    observed.write("c.txt", b"gamma")

    # Caching (layered on the observed store: one pipeline, no siblings)
    fast = cache(observed, ttl=300)
    fast.read_bytes("a.txt")  # first touch — cache miss
    fast.read_bytes("a.txt")  # within the TTL — served from the cache

    # Batch operations
    results = batch_copy(observed, [("a.txt", "b.txt"), ("c.txt", "d.txt")])
    # --8<-- [end:step13-extensions]

    assert [e.operation for e in events] == ["write", "write", "read_bytes", "copy", "copy"]
    assert fast.stats.hits == 1, "cached re-read did not hit"
    assert fast.read_bytes("b.txt") == store.read_bytes("a.txt")
    assert results.all_succeeded, "batch_copy reported failures"


def _demo_partial_capabilities() -> type[Driver]:
    # --8<-- [start:partial-capabilities]
    class ReadOnlyHttpDriver(Driver):
        name: str = "http-readonly"
        namespace: Literal["flat", "hierarchical"] = "flat"
        parents: Literal["none", "implicit", "explicit"] = "none"
        capabilities: CapabilitySet = CapabilitySet(
            {
                Capability.READ,
                Capability.METADATA,
                Capability.LAZY_READ,
            }
        )
        put_is_atomic: bool = False
        close_is_terminal: bool = False

        # ... the required primitives, as in Steps 4-9 ...

    # --8<-- [end:partial-capabilities]
    return ReadOnlyHttpDriver


def _demo_partial_write():
    # --8<-- [start:partial-write]
    def put(
        self,
        key: str,
        content: bytes | BinaryIO,
        *,
        overwrite: bool,
        metadata: Mapping[str, str] | None,
    ) -> PutResult:
        raise CapabilityNotSupported(
            "HTTP backend is read-only",
            capability="write",
            backend=self.name,
        )

    # --8<-- [end:partial-write]
    return put


def _demo_overclaim(read_only_cls: type[Driver]) -> str:
    """Construction refuses a declaration no protocol backs; return its message."""

    class _Overclaiming(read_only_cls):
        capabilities = CapabilitySet({Capability.READ, Capability.COPY})

    try:
        DriverBackend(_Overclaiming())
    except ValueError as exc:
        return str(exc)
    raise AssertionError("construction accepted COPY without copy()")


def _demo_test_examples() -> dict:
    # --8<-- [start:test-examples]
    import uuid

    import pytest
    from remote_store import AlreadyExists, InvalidPath, NotFound, Store

    @pytest.fixture
    def store():
        # A fresh prefix per test keeps one test's keys out of the next.
        backend = RedisBackend(url="redis://localhost:6379/15", prefix=f"test-{uuid.uuid4().hex[:8]}:")
        with Store(backend=backend) as s:
            yield s

    def test_read_write_roundtrip(store):
        store.write("hello.txt", b"world")
        assert store.read_bytes("hello.txt") == b"world"

    def test_write_no_overwrite(store):
        store.write("hello.txt", b"first")
        with pytest.raises(AlreadyExists):
            store.write("hello.txt", b"second")

    def test_read_missing(store):
        with pytest.raises(NotFound):
            store.read("nope.txt")

    def test_read_a_folder(store):
        store.write("docs/readme.md", b"# Hello")
        with pytest.raises(InvalidPath):
            store.read("docs")

    def test_list_files(store):
        store.write("a/1.txt", b"one")
        store.write("a/2.txt", b"two")
        store.write("b/3.txt", b"three")
        files = list(store.list_files("a"))
        assert len(files) == 2
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt"}

    def test_list_files_recursive(store):
        store.write("a/b/deep.txt", b"deep")
        store.write("a/top.txt", b"top")
        files = list(store.list_files("a", recursive=True))
        assert len(files) == 2

    def test_list_folders(store):
        store.write("docs/readme.md", b"# Hello")
        store.write("src/main.py", b"pass")
        folders = {f.name for f in store.list_folders("")}
        assert "docs" in folders
        assert "src" in folders

    # --8<-- [end:test-examples]
    # Hand the test bodies to the harness (tests/test_snippets.py runs each
    # against a fresh fake-redis Store, so the region is executed, not just
    # defined). The pytest fixture cannot be called directly and stays here.
    return {
        "test_read_write_roundtrip": test_read_write_roundtrip,
        "test_write_no_overwrite": test_write_no_overwrite,
        "test_read_missing": test_read_missing,
        "test_read_a_folder": test_read_a_folder,
        "test_list_files": test_list_files,
        "test_list_files_recursive": test_list_files_recursive,
        "test_list_folders": test_list_folders,
    }


# ---------------------------------------------------------------------------
# demo() — exercises patterns with MemoryBackend (no Redis needed)
# ---------------------------------------------------------------------------


def demo() -> None:
    """Execute testable snippets using MemoryBackend as a stand-in."""
    import os
    import tempfile

    from remote_store import Store
    from remote_store.backends import MemoryBackend

    # --- Verify the driver classes are valid Python (importable) ---
    assert RedisBackend.__name__ == "RedisBackend"
    assert RedisDriver.capabilities is _REDIS_CAPABILITIES
    assert RedisBackend.CAPABILITIES is RedisDriver.capabilities
    assert Capability.SEEKABLE_READ in _REDIS_CAPABILITIES
    assert Capability.GLOB not in _REDIS_CAPABILITIES

    # --- Exercise the usage patterns from Steps 12-13 with MemoryBackend ---
    store = Store(MemoryBackend())

    # Step 12: direct usage pattern
    store.write("reports/q1.csv", b"revenue,100\n")
    data = store.read_bytes("reports/q1.csv")
    assert data == b"revenue,100\n"

    files = list(store.list_files("reports"))
    assert len(files) == 1
    assert files[0].name == "q1.csv"

    # Step 12: registry pattern — runs the guide region against a
    # memory-backed stores.yaml (no Redis server in the example runner).
    # Guarded on the YAML *parser* only, so a broken ext.yaml import path
    # still fails loudly instead of being swallowed.
    import importlib.util

    if importlib.util.find_spec("yaml") or importlib.util.find_spec("ruamel.yaml"):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                os.chdir(tmp_dir)
                with open("stores.yaml", "w", encoding="utf-8") as f:
                    f.write(
                        "backends:\n"
                        "  demo-memory:\n"
                        "    type: memory\n"
                        "\n"
                        "stores:\n"
                        "  cache:\n"
                        "    backend: demo-memory\n"
                        '    root_path: "cache/v2"\n'
                    )
                try:
                    round_trip = _demo_registry_usage()
                finally:
                    # The region registers the tutorial class in the process-global
                    # factory map; restore it so in-process callers (pytest) stay clean.
                    from remote_store._registry import _BACKEND_FACTORIES

                    _BACKEND_FACTORIES.pop("redis", None)
                assert round_trip == b"from-registry"
            finally:
                os.chdir(cwd)
    else:
        print("Skipping the registry snippet: no YAML parser installed.")

    # Step 13: extensions work with any backend — runs the guide region itself
    _demo_extensions(store)
    assert store.read_bytes("b.txt") == b"alpha"
    assert store.read_bytes("d.txt") == b"gamma"

    # Root invariants (via MemoryBackend, same kernel)
    assert store.exists("reports/q1.csv")
    assert not store.is_file("")
    assert store.is_folder("")

    # Partial-capability regions: check the declarations against the real
    # ReadOnlyHttpBackend set, run the put body, and show construction
    # refusing a capability no protocol backs.
    import types

    from remote_store.backends import ReadOnlyHttpBackend

    read_only_cls = _demo_partial_capabilities()
    assert set(read_only_cls.capabilities) == set(ReadOnlyHttpBackend.CAPABILITIES)
    assert Capability.WRITE not in read_only_cls.capabilities

    put_fn = _demo_partial_write()
    try:
        put_fn(types.SimpleNamespace(name="http-readonly"), "x.txt", b"data", overwrite=False, metadata=None)
    except CapabilityNotSupported:
        pass
    else:
        raise AssertionError("partial-write region did not raise CapabilityNotSupported")

    assert "declares COPY without copy" in _demo_overclaim(read_only_cls)

    # The test-examples region's bodies run in tests/test_snippets.py against
    # a fake redis client; here we execute the definitions and count them.
    assert len(_demo_test_examples()) == 7

    print("All custom backend guide snippets passed.")


if __name__ == "__main__":
    demo()
