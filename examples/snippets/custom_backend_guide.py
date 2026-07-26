"""Custom backend guide snippets -- tested source for the Build Your Own Backend guide.

Named regions can be included in the guide via pymdownx.snippets:

    ```python
    ;--8<-- "examples/snippets/custom_backend_guide.py:step1-imports"
    ```

Run directly or via ``hatch run examples`` to verify all snippets.
The RedisBackend class is syntax-checked on import. Usage examples
(Steps 13-14) exercise the patterns with MemoryBackend to avoid
requiring a Redis server.
"""

# ruff: noqa: F401, F811, F821, F841, E402, I001, SIM108, TCH001, TCH002, TCH003
# mypy: ignore-errors
#
# Tutorial source for the Build Your Own Backend guide. Snippet regions
# include partial code (incomplete method bodies, undefined names referenced
# from later steps) that wouldn't pass strict typing as a single file.
# The runtime smoke check at the bottom exercises a subset that does.

# ---------------------------------------------------------------------------
# Step 1: Scaffold the class -- imports
# ---------------------------------------------------------------------------

# --8<-- [start:step1-imports]
from __future__ import annotations

import contextlib
import io
from datetime import datetime, timezone
from typing import TYPE_CHECKING, BinaryIO, ClassVar

try:
    import redis
except ImportError:  # graceful fallback when redis is not installed
    redis = None  # type: ignore[assignment]

from remote_store import (
    AlreadyExists,
    Backend,
    BackendUnavailable,
    Capability,
    CapabilitySet,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    FileInfo,
    FolderEntry,
    FolderInfo,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemotePath,
    WriteResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from contextlib import AbstractContextManager

    from remote_store._types import WritableContent
# --8<-- [end:step1-imports]

# ---------------------------------------------------------------------------
# Step 2: Declare capabilities
# ---------------------------------------------------------------------------

# --8<-- [start:step2-capabilities]
# Redis doesn't support atomic rename or native glob.
_REDIS_CAPABILITIES = CapabilitySet(
    {
        Capability.READ,
        Capability.WRITE,
        Capability.DELETE,
        Capability.LIST,
        Capability.MOVE,
        Capability.COPY,
        Capability.METADATA,
        Capability.SEEKABLE_READ,  # We return BytesIO, which is always seekable
    }
)
# --8<-- [end:step2-capabilities]


# ---------------------------------------------------------------------------
# Steps 3-12: The full RedisBackend class
# ---------------------------------------------------------------------------


class RedisBackend(Backend):
    """Redis-backed file storage.

    Files are stored as Redis hash keys under a configurable prefix.
    Each file is a hash with fields: ``data``, ``size``, ``modified_at``.
    """

    # -- Step 3: Constructor and properties --------------------------------

    # --8<-- [start:step3-constructor]
    CAPABILITIES: ClassVar[CapabilitySet] = _REDIS_CAPABILITIES

    def __init__(self, url: str = "redis://localhost:6379/0", prefix: str = "rs:") -> None:
        self._client = redis.Redis.from_url(url, decode_responses=False)
        self._prefix = prefix

    @property
    def name(self) -> str:
        return "redis"

    @property
    def capabilities(self) -> CapabilitySet:
        return self.CAPABILITIES

    # --8<-- [end:step3-constructor]

    # -- Step 4: Internal helpers ------------------------------------------

    # --8<-- [start:step4-helpers]
    # -- Key helpers --

    def _key(self, path: str) -> str:
        """Convert a backend-relative path to a Redis key."""
        return f"{self._prefix}file:{path}"

    def _folder_marker(self, path: str) -> str:
        """Key for folder existence markers."""
        return f"{self._prefix}dir:{path}"

    def _all_file_keys_pattern(self) -> str:
        """Pattern to scan all file keys."""
        return f"{self._prefix}file:*"

    def _path_from_key(self, key: bytes) -> str:
        """Extract the backend-relative path from a Redis key."""
        prefix = f"{self._prefix}file:"
        return key.decode().removeprefix(prefix)

    # --8<-- [end:step4-helpers]

    # --8<-- [start:step4-error-mapping]
    # -- Error mapping --

    def _map_error(self, exc: redis.RedisError, path: str = "") -> None:
        """Map Redis exceptions to remote-store errors. Always raises."""
        if isinstance(exc, redis.AuthenticationError):
            raise PermissionDenied(
                f"Redis authentication failed: {exc}",
                path=path or None,
                backend=self.name,
            ) from exc
        if isinstance(exc, redis.ConnectionError):
            raise BackendUnavailable(
                f"Redis connection failed: {exc}",
                path=path or None,
                backend=self.name,
            ) from exc
        raise BackendUnavailable(
            f"Redis error: {exc}",
            path=path or None,
            backend=self.name,
        ) from exc

    # --8<-- [end:step4-error-mapping]

    # -- Step 5: Existence checks ------------------------------------------

    # --8<-- [start:step5-existence]
    def exists(self, path: str) -> bool:
        if not path or path == ".":
            return True  # Root always exists
        try:
            return bool(self._client.exists(self._key(path)) or self._has_children(path))
        except redis.RedisError as exc:
            self._map_error(exc, path)

    def is_file(self, path: str) -> bool:
        if not path or path == ".":
            return False
        try:
            return bool(self._client.exists(self._key(path)))
        except redis.RedisError as exc:
            self._map_error(exc, path)

    def is_folder(self, path: str) -> bool:
        if not path or path == ".":
            return True  # Root is always a folder
        try:
            return self._has_children(path)
        except redis.RedisError as exc:
            self._map_error(exc, path)

    def _has_children(self, path: str) -> bool:
        """Check if any keys exist under this path prefix."""
        pattern = f"{self._prefix}file:{path}/*"
        cursor, keys = self._client.scan(cursor=0, match=pattern, count=1)
        return bool(keys)

    # --8<-- [end:step5-existence]

    # -- Step 6: Reading ---------------------------------------------------

    # --8<-- [start:step6-reading]
    def read(self, path: str) -> BinaryIO:
        try:
            data = self._client.hget(self._key(path), "data")
        except redis.RedisError as exc:
            self._map_error(exc, path)
        if data is None:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name)
        return io.BytesIO(data)

    def read_bytes(self, path: str) -> bytes:
        try:
            data = self._client.hget(self._key(path), "data")
        except redis.RedisError as exc:
            self._map_error(exc, path)
        if data is None:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name)
        return bytes(data)

    # --8<-- [end:step6-reading]

    # -- Step 7: Writing ---------------------------------------------------

    # --8<-- [start:step7-writing]
    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        if not path or path == ".":
            raise InvalidPath(
                "Path must not be empty for file operations",
                path=path,
                backend=self.name,
            )

        raw = content if isinstance(content, bytes) else content.read()

        try:
            if not overwrite and self._client.exists(self._key(path)):
                raise AlreadyExists(
                    f"File already exists: {path}",
                    path=path,
                    backend=self.name,
                )
            self._client.hset(
                self._key(path),
                mapping={
                    "data": raw,
                    "size": str(len(raw)),
                    "modified_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except (AlreadyExists, InvalidPath):
            raise  # Don't re-map our own errors
        except redis.RedisError as exc:
            self._map_error(exc, path)

        return WriteResult(path=RemotePath(path), size=len(raw))

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        # Redis HSET is already atomic, but we didn't declare ATOMIC_WRITE.
        # Store will reject this call before it reaches us.
        # If you want to support it, declare the capability and implement here.
        raise CapabilityNotSupported(
            "Redis backend does not support atomic writes",
            capability="atomic_write",
            backend=self.name,
        )

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        raise CapabilityNotSupported(
            "Redis backend does not support atomic writes",
            capability="atomic_write",
            backend=self.name,
        )
        yield  # Unreachable, but satisfies the generator contract

    # --8<-- [end:step7-writing]

    # -- Step 8: Deletion --------------------------------------------------

    # --8<-- [start:step8-deletion]
    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        if not path or path == ".":
            raise InvalidPath(
                "Path must not be empty for file operations",
                path=path,
                backend=self.name,
            )
        try:
            removed = self._client.delete(self._key(path))
        except redis.RedisError as exc:
            self._map_error(exc, path)
        if not removed and not missing_ok:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        if not path or path == ".":
            raise InvalidPath(
                "Cannot delete root folder",
                path=path,
                backend=self.name,
            )

        try:
            children = list(self._iter_file_paths_under(path))
        except redis.RedisError as exc:
            self._map_error(exc, path)

        if not children and not self._has_children(path):
            if not missing_ok:
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            return

        if children and not recursive:
            raise DirectoryNotEmpty(
                f"Folder not empty: {path}",
                path=path,
                backend=self.name,
            )

        if recursive:
            try:
                keys = [self._key(p) for p in children]
                if keys:
                    self._client.delete(*keys)
            except redis.RedisError as exc:
                self._map_error(exc, path)

    # --8<-- [end:step8-deletion]

    # -- Step 9: Listing ---------------------------------------------------

    # --8<-- [start:step9-listing]
    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        # max_depth is a pruning hint: backends with native depth limiting
        # honor it; everyone else can ignore it — Store filters client-side.
        try:
            for file_path in self._iter_file_paths_under(path):
                # If not recursive, only yield immediate children
                if not recursive:
                    rel = file_path.removeprefix(f"{path}/" if path else "")
                    if "/" in rel:
                        continue  # Skip nested files

                info = self._build_file_info(file_path)
                if info is not None:
                    yield info
        except redis.RedisError as exc:
            self._map_error(exc, path)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        seen: set[str] = set()
        try:
            for file_path in self._iter_file_paths_under(path):
                # Extract the immediate subfolder name
                prefix = f"{path}/" if path else ""
                rel = file_path.removeprefix(prefix)
                if "/" in rel:
                    folder_name = rel.split("/", 1)[0]
                    if folder_name not in seen:
                        seen.add(folder_name)
                        folder_path = f"{prefix}{folder_name}"
                        yield FolderEntry(
                            path=RemotePath(folder_path),
                            name=folder_name,
                        )
        except redis.RedisError as exc:
            self._map_error(exc, path)

    def _iter_file_paths_under(self, path: str) -> Iterator[str]:
        """Scan Redis for all file keys under a path prefix."""
        if path and path != ".":
            pattern = f"{self._prefix}file:{path}/*"
        else:
            pattern = self._all_file_keys_pattern()

        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                yield self._path_from_key(key)
            if cursor == 0:
                break

    def _build_file_info(self, path: str) -> FileInfo | None:
        """Build a FileInfo from Redis hash fields."""
        fields = self._client.hgetall(self._key(path))
        if not fields:
            return None
        return FileInfo(
            path=RemotePath(path),
            name=path.rsplit("/", 1)[-1],
            size=int(fields.get(b"size", b"0")),
            modified_at=datetime.fromisoformat(fields[b"modified_at"].decode()),
        )

    # --8<-- [end:step9-listing]

    # -- Step 10: Metadata -------------------------------------------------

    # --8<-- [start:step10-metadata]
    def get_file_info(self, path: str) -> FileInfo:
        if not path or path == ".":
            raise NotFound("File not found: (empty path)", path=path, backend=self.name)
        try:
            info = self._build_file_info(path)
        except redis.RedisError as exc:
            self._map_error(exc, path)
        if info is None:
            raise NotFound(f"File not found: {path}", path=path, backend=self.name)
        return info

    def get_folder_info(self, path: str) -> FolderInfo:
        try:
            file_count = 0
            total_size = 0
            latest: datetime | None = None

            for file_path in self._iter_file_paths_under(path):
                info = self._build_file_info(file_path)
                if info is not None:
                    file_count += 1
                    total_size += info.size
                    if latest is None or info.modified_at > latest:
                        latest = info.modified_at
        except redis.RedisError as exc:
            self._map_error(exc, path)

        if file_count == 0 and path and path != ".":
            raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

        return FolderInfo(
            path=RemotePath.from_backend_path(path),
            file_count=file_count,
            total_size=total_size,
            modified_at=latest,
        )

    # --8<-- [end:step10-metadata]

    # -- Step 11: Move and copy --------------------------------------------

    # --8<-- [start:step11-move-copy]
    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        if not src or src == ".":
            raise InvalidPath("Source path must not be empty", path=src, backend=self.name)
        if not dst or dst == ".":
            raise InvalidPath("Destination path must not be empty", path=dst, backend=self.name)

        try:
            # Read source
            data = self._client.hgetall(self._key(src))
            if not data:
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)

            # Check destination
            if not overwrite and self._client.exists(self._key(dst)):
                raise AlreadyExists(
                    f"Destination already exists: {dst}",
                    path=dst,
                    backend=self.name,
                )

            # Atomic: write destination then delete source
            pipe = self._client.pipeline()
            pipe.hset(self._key(dst), mapping=data)
            pipe.delete(self._key(src))
            pipe.execute()
        except (NotFound, AlreadyExists, InvalidPath):
            raise
        except redis.RedisError as exc:
            self._map_error(exc, src)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        if not src or src == ".":
            raise InvalidPath("Source path must not be empty", path=src, backend=self.name)
        if not dst or dst == ".":
            raise InvalidPath("Destination path must not be empty", path=dst, backend=self.name)

        try:
            data = self._client.hgetall(self._key(src))
            if not data:
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)

            if not overwrite and self._client.exists(self._key(dst)):
                raise AlreadyExists(
                    f"Destination already exists: {dst}",
                    path=dst,
                    backend=self.name,
                )

            # Update modified_at for the copy
            data[b"modified_at"] = datetime.now(timezone.utc).isoformat().encode()
            self._client.hset(self._key(dst), mapping=data)
        except (NotFound, AlreadyExists, InvalidPath):
            raise
        except redis.RedisError as exc:
            self._map_error(exc, src)

    # --8<-- [end:step11-move-copy]

    # -- Step 12: Lifecycle ------------------------------------------------

    # --8<-- [start:step12-lifecycle]
    def check_health(self) -> None:
        try:
            self._client.ping()
        except redis.AuthenticationError as exc:
            raise PermissionDenied(
                f"Redis authentication failed: {exc}",
                backend=self.name,
            ) from exc
        except redis.RedisError as exc:
            raise BackendUnavailable(
                f"Redis is not reachable: {exc}",
                backend=self.name,
            ) from exc

    def close(self) -> None:
        self._client.close()

    # --8<-- [end:step12-lifecycle]


# ---------------------------------------------------------------------------
# Step 13-14: Usage examples (exercised with MemoryBackend)
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    from remote_store import Store


def _demo_direct_usage() -> None:
    # --8<-- [start:step13-direct]
    from remote_store import Store

    backend = RedisBackend(url="redis://localhost:6379/0", prefix="myapp:")
    store = Store(backend=backend)

    store.write("reports/q1.csv", b"revenue,100\n")
    data = store.read_bytes("reports/q1.csv")
    print(data)  # b'revenue,100\n'

    for info in store.list_files("reports"):
        print(f"{info.name}: {info.size} bytes")
    # --8<-- [end:step13-direct]


def _demo_registry_usage() -> Store:
    # --8<-- [start:step13-registry]
    from remote_store import Registry, register_backend
    from remote_store.ext.yaml import from_yaml  # needs: pip install "remote-store[yaml]"

    register_backend("redis", RedisBackend)

    config = from_yaml("stores.yaml")
    registry = Registry(config)
    store = registry.get_store("cache")
    # --8<-- [end:step13-registry]
    return store


def _demo_extensions(store: Store) -> None:
    # --8<-- [start:step14-extensions]
    from remote_store.ext.batch import batch_copy
    from remote_store.ext.cache import cache
    from remote_store.ext.observe import observe

    events = []

    def my_logging_hook(event) -> None:
        events.append(event)

    # Observability — my_logging_hook fires after every operation
    observed = observe(store, on_any=my_logging_hook)

    # Caching
    fast = cache(store, ttl=300)

    # Batch operations
    results = batch_copy(store, [("a.txt", "b.txt"), ("c.txt", "d.txt")])
    # --8<-- [end:step14-extensions]

    observed.read_bytes("a.txt")
    assert events, "observe hook did not fire"
    assert fast.read_bytes("b.txt") == store.read_bytes("a.txt")
    assert results.all_succeeded, "batch_copy reported failures"


def _demo_partial_capabilities() -> None:
    # --8<-- [start:partial-capabilities]
    class _ReadOnlyBackend(Backend):  # type: ignore[abstract]
        CAPABILITIES: ClassVar[CapabilitySet] = CapabilitySet(
            {
                Capability.READ,
                Capability.LIST,
                Capability.METADATA,
            }
        )

        @property
        def capabilities(self) -> CapabilitySet:
            return self.CAPABILITIES

    # --8<-- [end:partial-capabilities]


def _demo_partial_write() -> None:
    # --8<-- [start:partial-write]
    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        raise CapabilityNotSupported(
            "HTTP backend is read-only",
            capability="write",
            backend=self.name,
        )

    # --8<-- [end:partial-write]


def _demo_test_examples() -> None:
    # --8<-- [start:test-examples]
    import pytest
    from remote_store import AlreadyExists, NotFound, Store

    @pytest.fixture
    def store():
        backend = RedisBackend(url="redis://localhost:6379/15", prefix="test:")
        backend._client.flushdb()  # Clean slate
        return Store(backend=backend)

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


# ---------------------------------------------------------------------------
# demo() — exercises patterns with MemoryBackend (no Redis needed)
# ---------------------------------------------------------------------------


def demo() -> None:
    """Execute testable snippets using MemoryBackend as a stand-in."""
    import os
    import tempfile

    from remote_store import Store
    from remote_store.backends import MemoryBackend

    # --- Verify RedisBackend class is valid Python (importable) ---
    assert RedisBackend.__name__ == "RedisBackend"
    assert Capability.READ in _REDIS_CAPABILITIES
    assert Capability.SEEKABLE_READ in _REDIS_CAPABILITIES
    assert Capability.ATOMIC_WRITE not in _REDIS_CAPABILITIES
    assert Capability.GLOB not in _REDIS_CAPABILITIES

    # --- Exercise the usage patterns from Steps 13-14 with MemoryBackend ---
    store = Store(MemoryBackend())

    # Step 13: direct usage pattern
    store.write("reports/q1.csv", b"revenue,100\n")
    data = store.read_bytes("reports/q1.csv")
    assert data == b"revenue,100\n"

    files = list(store.list_files("reports"))
    assert len(files) == 1
    assert files[0].name == "q1.csv"

    # Step 13: registry pattern — runs the guide region against a
    # memory-backed stores.yaml (no Redis server in the example runner).
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
                registry_store = _demo_registry_usage()
            finally:
                # The region registers the tutorial class in the process-global
                # factory map; restore it so in-process callers (pytest) stay clean.
                from remote_store._registry import _BACKEND_FACTORIES

                _BACKEND_FACTORIES.pop("redis", None)
            registry_store.write("hello.txt", b"from-registry")
            assert registry_store.read_bytes("hello.txt") == b"from-registry"
        finally:
            os.chdir(cwd)

    # Step 14: extensions work with any backend — runs the guide region itself
    store.write("a.txt", b"aaa")
    store.write("c.txt", b"ccc")
    _demo_extensions(store)
    assert store.read_bytes("b.txt") == b"aaa"
    assert store.read_bytes("d.txt") == b"ccc"

    # Step 5 invariants (via MemoryBackend, same contract)
    assert store.exists("reports/q1.csv")
    assert not store.is_file("")
    assert store.is_folder("")

    # Partial capabilities snippet is valid
    partial = CapabilitySet({Capability.READ, Capability.LIST, Capability.METADATA})
    assert Capability.WRITE not in partial

    print("All custom backend guide snippets passed.")


if __name__ == "__main__":
    demo()
