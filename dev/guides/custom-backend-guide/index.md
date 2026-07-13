# Build Your Own Backend

Write file storage code once. Run it against local files, S3, SFTP, Azure, OneDrive — or your own custom storage system.

This guide walks you through implementing a custom [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md) for remote-store. By the end, you'll have a working backend that plugs into [`Store`](https://docs.remotestore.dev/stable/reference/api/store/index.md), [`Registry`](https://docs.remotestore.dev/stable/reference/api/registry/index.md), and every extension in the ecosystem.

______________________________________________________________________

## What you'll build

A **Redis backend** that stores files as Redis keys. It's simple enough to fit in one module, yet exercises every part of the Backend contract: reads, writes, listing, metadata, error mapping, and capability declarations.

**Prerequisites:** `pip install remote-store redis`

______________________________________________________________________

## The Backend contract

Every backend is a subclass of [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md). The contract is straightforward:

1. **Declare capabilities** — which operations does your backend support?
1. **Implement abstract members** — methods and properties covering CRUD, listing, and metadata. See [Abstract methods](#abstract-methods-must-implement) for the full list.
1. **Map all exceptions** — native errors must become `remote_store` errors. No leaks.

The [`Store`](https://docs.remotestore.dev/stable/reference/api/store/index.md) class wraps your backend, adds path validation, capability gating, and scoping. You implement the raw operations; `Store` handles the policy.

______________________________________________________________________

## Step 1: Scaffold the class

```
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
```

Every backend starts with these imports. The key types:

| Import                                                                                                                                                                                                                                                 | Purpose                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md)                                                                                                                                                                        | Abstract base class you subclass                                                                                        |
| [`Capability`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md), [`CapabilitySet`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md)                                                                    | Declare supported operations                                                                                            |
| [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), ...                                                                             | Normalized error types                                                                                                  |
| [`FileInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md), [`FolderEntry`](https://docs.remotestore.dev/stable/reference/api/models/index.md), [`FolderInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md) | Return types for listing and metadata                                                                                   |
| [`RemotePath`](https://docs.remotestore.dev/stable/reference/api/models/index.md)                                                                                                                                                                      | Immutable, validated path type                                                                                          |
| [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/index.md)                                                                                                                                                                     | Return type for `write()` and `write_atomic()`; carries the written path, size, and optional backend-native digest/etag |
| `WritableContent`                                                                                                                                                                                                                                      | Type alias: `bytes \| BinaryIO`                                                                                         |

______________________________________________________________________

## Step 2: Declare capabilities

```
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
```

**Capabilities gate Store methods.** If you don't declare `ATOMIC_WRITE`, calls to `store.write_atomic()` raise `CapabilityNotSupported` automatically — you don't need to handle it.

`_REDIS_CAPABILITIES` is assigned to the class-level `CAPABILITIES` attribute in Step 3. Tooling and conformance tests read `YourBackend.CAPABILITIES` without instantiating the class, so the constant must be a class attribute — not computed in `__init__`.

Three capabilities added in v0.23.0 are worth declaring when they apply:

- **`USER_METADATA`** — declare this when your backend stores the `metadata=` mapping passed to `write()` and `write_atomic()`. Without it, `Store` raises `CapabilityNotSupported` if the caller passes non-empty metadata.
- **`WRITE_RESULT_NATIVE`** — declare this when your backend populates `WriteResult` fields beyond the two mandatory ones (`path` and `size`). See the [WriteResult reference](https://docs.remotestore.dev/stable/reference/api/models/index.md) for the full field list.
- **`LAZY_READ`** — declare this when `read()` fetches data lazily from the remote source. A `BytesIO` return does not qualify — data is already materialized.

The Redis example declares neither `USER_METADATA` nor `WRITE_RESULT_NATIVE` (it stores raw bytes without a metadata column and returns only `path` and `size` at write time).

Each capability gates specific Store methods. See the [Capability reference](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md) for the full list.

______________________________________________________________________

## Step 3: Constructor and properties

```
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
```

**Rules:**

- `name` must be a unique string. Used in error messages and the registry.
- `CAPABILITIES: ClassVar[CapabilitySet]` exposes the capability set at class level — no instantiation required. The `capabilities` property delegates to `self.CAPABILITIES` so both the class view and the instance view always agree.
- Constructor parameters become `options:` in YAML config (more on this later).

______________________________________________________________________

## Step 4: Internal helpers

Before implementing the abstract methods, add helpers for key management and error mapping.

```
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
```

Redis has no concept of folders, so we use key prefixes to simulate a hierarchical namespace. Files live under `rs:file:<path>`, and folder markers (optional) under `rs:dir:<path>`.

```
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
```

**The cardinal rule:** backend-native exceptions must never leak. Every Redis error becomes a `remote_store` error. The `from exc` preserves the original traceback for debugging.

______________________________________________________________________

## Step 5: Existence checks

```
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
```

**Key invariants:**

- `exists()` **never raises `NotFound`** — always returns `bool`.
- `""` and `"."` are root aliases. Root always exists and is always a folder.
- `is_file("")` is always `False`. `is_folder("")` is always `True`.

______________________________________________________________________

## Step 6: Reading

```
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
```

**Notes:**

- `read()` returns a `BinaryIO`. Since we return `BytesIO`, streams are seekable — that's why we declared `SEEKABLE_READ`.
- `read_bytes()` can be more efficient than `read().read()` because it avoids wrapping in a stream object.
- Both raise `NotFound` for missing files.

Since our `read()` returns seekable streams, we don't need to override `read_seekable()` — the default implementation detects seekability and returns the stream as-is.

______________________________________________________________________

## Step 7: Writing

```
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
```

**Key patterns:**

- `content` is `bytes | BinaryIO`. Normalize with `content if isinstance(content, bytes) else content.read()`.
- **Both `write()` and `write_atomic()` accept `metadata: Mapping[str, str] | None = None`.** If your backend declares `USER_METADATA`, persist the mapping alongside the file. If it doesn't, ignore the argument — `Store` rejects non-empty metadata before reaching your implementation.
- **Both methods must return [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/index.md).** Construct it with at minimum `path=RemotePath(path)` and `size=len(raw)`. If your backend can populate richer fields, declare `WRITE_RESULT_NATIVE` and include them. The Redis example returns the two-field minimum.
- **Write creates parent folders implicitly** — in Redis, there's nothing to create, but filesystem-based backends must `mkdir -p`.
- Re-raise your own errors (`AlreadyExists`, `InvalidPath`) before the catch-all `RedisError` handler.
- Even though Store gates `write_atomic()` via capabilities, implement the methods anyway (they're abstract). Raise `CapabilityNotSupported` as a safety net.

______________________________________________________________________

## Step 8: Deletion

```
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
```

**Invariants:**

- `delete()` targets files. `delete_folder()` targets folders.
- `missing_ok=True` suppresses `NotFound`.
- `delete_folder(recursive=False)` raises `DirectoryNotEmpty` if the folder has contents.
- You cannot delete root (`""` or `"."`).

______________________________________________________________________

## Step 9: Listing

```
def list_files(self, path: str, *, recursive: bool = False) -> Iterator[FileInfo]:
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
```

**Key rules:**

- `list_files(path="")` lists from root.
- `recursive=False` (default) yields only immediate children.
- `list_folders()` is always non-recursive — only immediate subfolders.
- Non-existent paths yield nothing (no exception).
- [`FileInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md)`.path` must be a [`RemotePath`](https://docs.remotestore.dev/stable/reference/api/models/index.md).

______________________________________________________________________

## Step 10: Metadata

```
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
```

**Contrast with existence checks:**

- `get_file_info()` raises `NotFound` if missing.
- `get_folder_info()` raises `NotFound` if the folder doesn't exist.
- `exists()` never raises — returns `bool`.

______________________________________________________________________

## Step 11: Move and copy

```
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
```

______________________________________________________________________

## Step 12: Lifecycle methods

```
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
```

`check_health()` should be the **cheapest possible read-only operation**. Redis `PING` is ideal. For S3 it's a `HEAD` on the bucket. For a database it's `SELECT 1`.

______________________________________________________________________

## Step 13: Register and use

### Direct instantiation

```
from remote_store import Store

backend = RedisBackend(url="redis://localhost:6379/0", prefix="myapp:")
store = Store(backend=backend)

store.write("reports/q1.csv", b"revenue,100\n")
data = store.read_bytes("reports/q1.csv")
print(data)  # b'revenue,100\n'

for info in store.list_files("reports"):
    print(f"{info.name}: {info.size} bytes")
```

### Via Registry (YAML config)

Register your backend type before creating a [`Registry`](https://docs.remotestore.dev/stable/reference/api/registry/index.md):

```
from remote_store import Registry, RegistryConfig, register_backend

register_backend("redis", RedisBackend)

config = RegistryConfig.from_yaml("stores.yaml")
registry = Registry(config)
store = registry.get_store("cache")
```

```
# stores.yaml
backends:
  redis-main:
    type: redis
    options:
      url: "redis://localhost:6379/0"
      prefix: "app:"

stores:
  cache:
    backend: redis-main
    root_path: "cache/v2"
```

The `options` dict is unpacked as `**kwargs` to your constructor. Parameter names in YAML must match your `__init__` signature exactly.

______________________________________________________________________

## Step 14: Extensions work automatically

Because your backend implements the `Backend` contract, every remote-store extension works out of the box:

```
from remote_store.ext.batch import batch_copy
from remote_store.ext.cache import cache
from remote_store.ext.observe import observe

# Observability
observed = observe(store, hooks=[my_logging_hook])

# Caching
fast = cache(store, ttl=300)

# Batch operations
results = batch_copy(store, [("a.txt", "b.txt"), ("c.txt", "d.txt")])
```

Extensions that require specific capabilities will check at runtime. For example, `ext.glob.glob_files()` works with any `LIST`-capable backend — it doesn't need the `GLOB` capability.

______________________________________________________________________

## Partial-capability backends

Not every backend supports every operation. The HTTP backend, for example, is read-only:

```
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
```

When a user calls `store.write()` on an HTTP-backed store, the `Store` layer raises `CapabilityNotSupported` before your backend code runs. You still need to implement the abstract methods (Python requires it), but they can raise `CapabilityNotSupported`:

```
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
```

______________________________________________________________________

## Error mapping checklist

Every backend-native exception must map to one of these:

| remote-store error                                                                            | When to raise                                              |
| --------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)               | File/folder doesn't exist (for operations that require it) |
| [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)          | Target exists and `overwrite=False`                        |
| [`PermissionDenied`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)       | Auth failure, insufficient permissions                     |
| [`InvalidPath`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)            | Malformed path, null bytes, `..` traversal                 |
| [`DirectoryNotEmpty`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)      | Non-empty folder and `recursive=False`                     |
| [`BackendUnavailable`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)     | Network error, service down                                |
| [`CapabilityNotSupported`](https://docs.remotestore.dev/stable/reference/api/errors/index.md) | Operation not supported by this backend                    |

**Pattern:** catch the SDK's base exception class, classify by error code/type, and raise the appropriate remote-store error with `from exc`.

______________________________________________________________________

## Testing your backend

remote-store ships a per-topic conformance suite under `tests/backends/conformance/` that validates any backend against the formal `BackendContract` specification. Backends contributed to the repo plug into this infrastructure and run through the full suite automatically. Standalone backends can either reuse this suite or write focused tests against the same categories.

______________________________________________________________________

### Conformance suite overview

The suite lives in [`tests/backends/conformance/`](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance), split into per-topic files that share the same parameterized `backend` fixture — every registered backend runs the full suite automatically.

| Topic file                                                                                                                   | Coverage                                                                         | Run with                                                 |
| ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------- |
| [`test_identity.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_identity.py)         | Identity, capabilities, lifecycle, `resolve`, native path round-trip             | `pytest tests/backends/conformance/test_identity.py`     |
| [`test_io.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_io.py)                     | `exists`, `is_file`/`is_folder`, read, write, delete, `to_key` round-trip        | `pytest tests/backends/conformance/test_io.py`           |
| [`test_listing.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_listing.py)           | `list_files`/`list_folders`, `iter_children`, glob, completeness                 | `pytest tests/backends/conformance/test_listing.py`      |
| [`test_atomic.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_atomic.py)             | `write_atomic`, `open_atomic` (SAW-*), `WriteResult` (WR-*), move/copy semantics | `pytest tests/backends/conformance/test_atomic.py`       |
| [`test_metadata.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_metadata.py)         | `get_file_info`/`get_folder_info`, `size`, `modified_at`, aggregates             | `pytest tests/backends/conformance/test_metadata.py`     |
| [`test_streaming.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_streaming.py)       | Streaming reads, `LAZY_READ` laziness, resource cleanup                          | `pytest tests/backends/conformance/test_streaming.py`    |
| [`test_errors.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_errors.py)             | Typed-error fidelity across read/write/delete/move/copy paths                    | `pytest tests/backends/conformance/test_errors.py`       |
| [`test_check_health.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_check_health.py) | `check_health()` contract — error mapping never leaks native SDK exceptions      | `pytest tests/backends/conformance/test_check_health.py` |

Run the whole suite at once with `pytest tests/backends/conformance/`.

**Extended (Dafny-derived) cases** — error fidelity, precondition ordering, depth filtering, move/copy edge semantics, resource cleanup — are not a separate file. They are individual tests marked [`@pytest.mark.extended_conformance`](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance) spread across the topic files above, so they run with the rest of the suite by default and can be selected on their own:

```
pytest -m extended_conformance
```

Async backends have their own extended sibling, [`test_async_extended.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_async_extended.py), which exercises the `AsyncBackend` contract (ASYNC- *mirroring BE-*).

The conformance suite itself is validated by running it against a mathematically verified oracle compiled from the formal Dafny specification (`sdd/formal/MemoryBackend.dfy`). If the oracle passes a test, the test is known-correct. This means passing the conformance suite is a strong guarantee of correctness — not just "matches what existing backends happen to do." See [`sdd/formal/README.md`](https://github.com/haalfi/remote-store/blob/master/sdd/formal/README.md) § Compiled Oracle for details.

______________________________________________________________________

### Registering in the conformance fixture (contributing backends)

If you are contributing a backend to remote-store, this is step 3 of [CONTRIBUTING.md § Adding a New Backend](https://docs.remotestore.dev/stable/explanation/contributing/#adding-a-new-backend). Add your backend to [`tests/backends/conftest.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conftest.py); the entire conformance suite then runs against it automatically.

**1. Add an availability guard near the top of `conftest.py`:**

```
def _redis_available() -> bool:
    try:
        import redis  # noqa: F401
        return True
    except ImportError:
        return False
```

**2. Add a `pytest.param` constant:**

```
_redis_param = pytest.param(
    "redis",
    marks=pytest.mark.skipif(not _redis_available(), reason="redis-py not installed"),
)
```

If your backend requires an external service (like S3, SFTP, or Azurite), add a reachability check and a session-scoped server fixture following the existing `moto_server` / `sftp_server` / `azurite_server` pattern.

**3. Add it to the `backend` fixture's `params` list and `elif` branch:**

```
@pytest.fixture(
    params=[
        _local_param,
        _memory_param,
        # ... existing params ...
        _redis_param,   # ← add here
    ]
)
def backend(request, moto_server, sftp_server, azurite_server, http_server):
    ...
    elif request.param == "redis":
        from remote_store.backends._redis import RedisBackend
        b = RedisBackend(url="redis://localhost:6379/0", prefix=f"test-{uuid.uuid4().hex}:")
        yield b
        b.close()
```

`conftest.py` already imports `uuid` at the top — ensure yours does too if you are starting from scratch. Use a unique prefix per test so isolation is guaranteed even without a full teardown.

______________________________________________________________________

### Capability gating with `_require()`

Backends may declare a subset of capabilities. The `_require()` helper skips a test when the backend lacks the needed capability — so a read-only backend cleanly skips all write, move, copy, and delete tests without failures:

```
def _require(backend: Backend, *caps: Capability) -> None:
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")
```

Use the same pattern in your own tests:

```
from remote_store import Capability
import pytest

def test_move_preserves_content(backend):
    _require(backend, Capability.MOVE)
    backend.write("src.txt", b"hello")
    backend.move("src.txt", "dst.txt")
    assert backend.read_bytes("dst.txt") == b"hello"
```

A backend declaring only `READ` and `LIST` will skip every `WRITE`, `MOVE`, `COPY`, and `DELETE` test. The suite still passes — skips are not failures.

______________________________________________________________________

### Flat-namespace vs. hierarchical backends

Backends fall into two models that affect a handful of conformance tests.

**Hierarchical** backends (Local, SFTP, Memory) have real directory objects. Writing a file creates its parent directories; a path can be either a file *or* a directory, never both.

**Flat-namespace** backends (S3, Azure, HTTP) have no real directory entries. Folders are virtual — inferred from key prefixes. A path `a/b/c` implies a prefix `a/b/` but no actual directory object exists.

The conformance suite reads this from the per-backend `flat_namespace` flag declared in `tests/backends/fixtures/backends.toml`:

```
# tests/backends/fixtures/backends.toml
[backend.<your-backend>]
transport         = "fs"        # http | ssh | fs | memory | sql
flat_namespace    = true        # set true for flat-namespace backends
self_op_supported = true
```

A per-fixture override in `fixtures.toml` is also possible — Azurite (the flat emulator) and live ADLS Gen2 (HNS) share `backend == "azure"` but disagree on `flat_namespace`, so the fixture-level value takes precedence. Tests that rely on real directory semantics call `_skip_flat_namespace()`, which reads the resolved flag from the per-fixture record attached by the conformance indirect fixture; no identity-set lookup is needed.

Key behavioral differences that the conformance tests check:

| Behavior                                             | Hierarchical (Local, SFTP, Memory) | Flat-namespace (S3, Azure, HTTP)             |
| ---------------------------------------------------- | ---------------------------------- | -------------------------------------------- |
| Write to a path that is an existing directory        | Raises `InvalidPath`               | Typically allowed (no real directory)        |
| `delete_folder(recursive=False)` on non-empty folder | Raises `DirectoryNotEmpty`         | Behaviour varies; some tests are skipped     |
| Explicit directory creation                          | Required (mkdir semantics)         | Not needed; folders emerge from key prefixes |
| `is_folder(path)` for a prefix with no keys          | `False`                            | `False`                                      |

If your backend is hierarchical (the common case), no action is needed — the full extended suite applies.

______________________________________________________________________

### Conformance checklist

Before a backend is considered conformant, verify:

| Level             | What                                                                                    | Command                                                                         |
| ----------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Conformance**   | All `tests/backends/conformance/` tests pass or self-skip (declared capability missing) | `pytest tests/backends/conformance/ -k <backend-name>`                          |
| **Extended**      | All `@pytest.mark.extended_conformance` cases pass or self-skip                         | `pytest -m extended_conformance -k <backend-name>`                              |
| **Error mapping** | Every native exception maps to a `remote_store` error — nothing leaks                   | Error mapping checklist above                                                   |
| **Repr safety**   | `repr(backend)` does not expose secrets                                                 | `pytest tests/backends/conformance/test_identity.py -k test_repr_masks_secrets` |

Skips are expected and acceptable when a backend doesn't declare the relevant capability. Failures (not skips) in either suite are blocking.

______________________________________________________________________

### Standalone backend testing

> **Not contributing to the repo?** Skip the fixture registration above and write focused tests directly. The categories below mirror what the conformance suite verifies.

If you are building a backend outside the remote-store repository, write focused tests covering the same categories the conformance suite verifies:

#### Happy paths

- Read/write round-trip
- Overwrite behavior (`overwrite=True` and `overwrite=False`)
- List files and folders (recursive and non-recursive)
- Move and copy
- Metadata accuracy (`size`, `modified_at`)

#### Error paths

- `read()` on missing file raises `NotFound`
- `write()` on existing file with `overwrite=False` raises `AlreadyExists`
- `delete(missing_ok=False)` on missing file raises `NotFound`
- `delete_folder(recursive=False)` on non-empty folder raises `DirectoryNotEmpty`
- Path naming a wrong type (file path to `get_folder_info`, directory path to `read`) raises `InvalidPath`
- Backend unavailable raises `BackendUnavailable`

#### Edge cases

- Empty path (`""`) and root alias (`"."`) — root always exists and is always a folder
- `is_file("")` always returns `False`; `exists("")` never raises
- Deeply nested paths (`"a/b/c/d/e/file.txt"`)
- Non-existent paths to `list_files` / `list_folders` yield nothing (no exception)
- `repr(backend)` does not expose credentials or secrets
- Concurrent access (if thread-safety matters)

#### Example test structure

```
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
```

______________________________________________________________________

## Design decisions

### When to declare `SEEKABLE_READ`

Declare it only if `read()` **always** returns a seekable stream with zero overhead. `BytesIO` qualifies. Streams backed by network iterators don't.

If your `read()` returns a non-seekable stream, don't worry — `Store` handles it. `read_seekable()` will spool to a temp file automatically. You can also override `read_seekable()` for an optimized path (like Azure's HTTP Range reader).

### When to support `ATOMIC_WRITE`

Support it if your backend can guarantee that readers never see partial content. Filesystem backends use temp-file-and-rename. Databases can use transactions. If your backend's writes are inherently atomic (single Redis `HSET`), you could declare it — but be honest about the guarantee. "Atomic at the key level" isn't the same as "atomic rename of a visible path."

### Thread safety

Backends may be called from multiple threads (e.g., `batch_copy` with concurrency). Use locking if your internal state is mutable. Redis clients are generally thread-safe, so our example doesn't need explicit locking.

______________________________________________________________________

## Quick reference

### Abstract methods (must implement)

| Member                                                  | Type                                                                                                 | Raises on error                                                                                                                                                                     |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CAPABILITIES` (class attribute)                        | [`ClassVar[CapabilitySet]`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md) | —                                                                                                                                                                                   |
| `name` (property)                                       | `str`                                                                                                | —                                                                                                                                                                                   |
| `capabilities` (property)                               | [`CapabilitySet`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md)           | —                                                                                                                                                                                   |
| `exists(path)`                                          | `bool`                                                                                               | Never raises [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)                                                                                        |
| `is_file(path)`                                         | `bool`                                                                                               | —                                                                                                                                                                                   |
| `is_folder(path)`                                       | `bool`                                                                                               | —                                                                                                                                                                                   |
| `read(path)`                                            | `BinaryIO`                                                                                           | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)                                                                                                     |
| `read_bytes(path)`                                      | `bytes`                                                                                              | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)                                                                                                     |
| `write(path, content, overwrite, metadata=None)`        | [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/index.md)                   | [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)                                                                                                |
| `write_atomic(path, content, overwrite, metadata=None)` | [`WriteResult`](https://docs.remotestore.dev/stable/reference/api/models/index.md)                   | [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), [`CapabilityNotSupported`](https://docs.remotestore.dev/stable/reference/api/errors/index.md) |
| `open_atomic(path, overwrite)`                          | `ContextManager[BinaryIO]`                                                                           | [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), [`CapabilityNotSupported`](https://docs.remotestore.dev/stable/reference/api/errors/index.md) |
| `delete(path, missing_ok)`                              | `None`                                                                                               | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)                                                                                                     |
| `delete_folder(path, recursive, missing_ok)`            | `None`                                                                                               | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), [`DirectoryNotEmpty`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)           |
| `list_files(path, recursive)`                           | `Iterator[`[`FileInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md)`]`        | —                                                                                                                                                                                   |
| `list_folders(path)`                                    | `Iterator[`[`FolderEntry`](https://docs.remotestore.dev/stable/reference/api/models/index.md)`]`     | —                                                                                                                                                                                   |
| `get_file_info(path)`                                   | [`FileInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md)                      | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)                                                                                                     |
| `get_folder_info(path)`                                 | [`FolderInfo`](https://docs.remotestore.dev/stable/reference/api/models/index.md)                    | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)                                                                                                     |
| `move(src, dst, overwrite)`                             | `None`                                                                                               | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)               |
| `copy(src, dst, overwrite)`                             | `None`                                                                                               | [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md)               |

### Optional overrides

| Method                | Default behavior                         |
| --------------------- | ---------------------------------------- |
| `read_seekable(path)` | Spools non-seekable streams to temp file |
| `iter_children(path)` | Chains `list_files()` + `list_folders()` |
| `glob(pattern)`       | Raises `CapabilityNotSupported`          |
| `to_key(native_path)` | Identity function                        |
| `native_path(path)`   | Identity function                        |
| `check_health()`      | No-op                                    |
| `close()`             | No-op                                    |
| `unwrap(type_hint)`   | Raises `CapabilityNotSupported`          |

______________________________________________________________________

## See also

- [Backend API reference](https://docs.remotestore.dev/stable/reference/api/backend/index.md) — full method documentation
- [Error types API reference](https://docs.remotestore.dev/stable/reference/api/errors/index.md) — all error classes
- [Backend Adapter Contract](https://docs.remotestore.dev/stable/explanation/design/specs/003-backend-adapter-contract/index.md) — formal spec
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — all backends and their capabilities
- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md) — decision guide for built-in backends
- [Architecture Overview](https://docs.remotestore.dev/stable/explanation/architecture/index.md) — how Store, Backend, and extensions fit together
