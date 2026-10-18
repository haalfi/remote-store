# Build Your Own Backend

Write file storage code once. Run it against local files, S3, SFTP, Azure, OneDrive — or your own custom storage system.

This guide walks you through writing a **driver** for remote-store and turning it into a backend. By the end, you'll have a working backend that plugs into [`Store`](https://docs.remotestore.dev/stable/reference/api/store/index.md), [`Registry`](https://docs.remotestore.dev/stable/reference/api/registry/index.md), and every extension in the ecosystem.

______________________________________________________________________

## What you'll build

A **Redis driver** that stores each file as a Redis hash. It's small enough to fit in one module, yet exercises every part of the driver contract: reads, writes, listing, metadata, error classification, capability declarations and two optional protocols.

**Prerequisites:** `pip install remote-store redis`

______________________________________________________________________

## How a driver fits

A backend is two pieces:

- **The driver** is yours. It maps one-to-one onto your storage system's own calls: look up a key, read it, write it, delete it, list a prefix. It carries no path, root, closed-state or error-typing logic.
- **The contract kernel** is ours. [`DriverBackend`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.DriverBackend) is a complete [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md) built over a driver. It decides once, for every driver, what the backend contract says: which keys are valid and how they normalise, that the store root is a folder, what a closed backend answers, which error a refusal becomes, how deep a listing goes, how a folder's totals add up, and how a move, a copy or a recursive folder delete is sequenced.

The contract asks three things of a driver:

1. **Declare what the storage is:** a name, its namespace, whether it has folder objects, its capabilities and two posture flags.
1. **Implement the required primitives:** fourteen methods, listed in [Required driver members](#required-driver-members).
1. **Classify native errors:** `classify()` turns an exception from your client library into a `remote_store` error. The kernel calls it; you never wrap a call yourself.

Optional protocols (copy, rename, ranged reads, and so on) back further capabilities. [`Store`](https://docs.remotestore.dev/stable/reference/api/store/index.md) wraps the backend as it wraps any other, adding capability gating and scoping.

Subclassing `Backend` directly

A class that subclasses [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md) and implements every abstract method still works. It then owns everything the kernel decides: path rules, root and closed guards, error typing, listing depth. A driver is the documented route because the kernel gets those right once for every backend.

______________________________________________________________________

## Step 1: Imports

```
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
```

| Import                                                                                                                                                                                                                                                                                                     | Purpose                                                            |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [`Driver`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Driver)                                                                                                                                                                                                         | The protocol your driver class implements                          |
| [`DriverBackend`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.DriverBackend)                                                                                                                                                                                           | The kernel: the `Backend` your class subclasses to wrap the driver |
| [`Entry`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Entry), [`Page`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Page), [`PutResult`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.PutResult) | Records a driver hands the kernel                                  |
| [`Op`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Op)                                                                                                                                                                                                                 | The operation a `classify` call is asked about                     |
| [`Capability`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md), [`CapabilitySet`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md)                                                                                                                        | Declare supported operations                                       |
| [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/index.md), ...                                                                                                                                 | Typed errors a driver may raise or return                          |
| [`Secret`](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.Secret), [`RetryPolicy`](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.RetryPolicy)                                                                                                             | What config loading hands your constructor                         |
| [`ResolutionPlan`](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.ResolutionPlan)                                                                                                                                                                                                  | Return type of `resolve()`                                         |

Subclassing `Driver` explicitly is optional, since the kernel only calls the members, but it gives you a type checker's help and the protocol's no-op `probe()` for a store that is always healthy. `probe()` is the only member you may inherit from the protocol: building the backend raises `ValueError` naming any member your driver leaves out or inherits from it otherwise, so a forgotten `delete()` fails at startup instead of reporting success. A driver that does not subclass `Driver` has no `probe()` to inherit, and must define its own.

______________________________________________________________________

## Step 2: Declare capabilities

```
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
```

**Capabilities gate Store methods.** If you don't declare `GLOB`, calls to `store.glob()` raise `CapabilityNotSupported` automatically; your driver is never asked.

**A declaration needs something behind it.** Constructing the backend raises `ValueError` when a declared capability has no protocol to back it:

| Capability     | Backed by                                                                                      |
| -------------- | ---------------------------------------------------------------------------------------------- |
| `COPY`         | [`SupportsCopy`](#optional-protocols)                                                          |
| `MOVE`         | `SupportsAtomicMove`, `SupportsRename` or `SupportsCopy` (the kernel copies, then deletes)     |
| `ATOMIC_MOVE`  | `SupportsAtomicMove`, or `SupportsRename` with `rename_replaces = True`                        |
| `ATOMIC_WRITE` | `put_is_atomic = True`, `SupportsOpenWrite`, or `SupportsRename` with `rename_replaces = True` |
| `GLOB`         | `SupportsGlob`                                                                                 |

The other capabilities need only the required primitives. The Redis driver declares `ATOMIC_WRITE` because one `HSET` is atomic, so a reader never sees half a file, and `ATOMIC_MOVE` because `RENAME` is.

Three further capabilities are worth declaring when they apply:

- **`USER_METADATA`**: your `put()` stores the `metadata=` mapping. Without it, the caller's non-empty metadata is refused before your driver runs.
- **`WRITE_RESULT_NATIVE`**: your `put()` fills the rich [`PutResult`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.PutResult) fields from the storage system's own write response, with `source="native"`. The criterion is provenance, not field count. Without the flag, results carry `path`, `size` and `source == "basic"`.
- **`LAZY_READ`**: the stream `get()` returns fetches data on demand. A `BytesIO` does not qualify; its data is already in memory.

The Redis driver declares neither `USER_METADATA` nor `WRITE_RESULT_NATIVE`. See the [Capability reference](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md) for the full list.

______________________________________________________________________

## Step 3: The driver class and its declarations

```
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
```

The six declared attributes tell the kernel what it is working with:

- **`name`**: a unique string, carried as `backend` on every error.
- **`namespace`**: `"flat"` when a key can sit beside a prefix of the same name and under another key (object stores, Redis); `"hierarchical"` when the storage system refuses both itself (a filesystem). On a flat namespace the kernel checks before every write that the key is no folder and lies under no file. On a hierarchical one your write primitives refuse those cases, in whatever shape the storage system has, and the kernel types the refusal.
- **`parents`**: `"none"` when folders are only prefixes, `"implicit"` when a write creates them, `"explicit"` when they must be created first. A flat driver must say `"none"`. With `"explicit"` you implement `SupportsEnsureParents`, and with any value other than `"none"`, `SupportsRemoveFolder`; construction refuses the driver otherwise.
- **`capabilities`**: the set from Step 2.
- **`put_is_atomic`**: whether `put()` alone never exposes partial content.
- **`close_is_terminal`**: whether the backend must refuse use after `close()`. The kernel's closed guard reads it; you write no closed check.

The constructor takes `password` as `str | Secret` and a `retry` keyword. Config loading passes both to your backend class, which forwards them here ([Step 11](#step-11-wrap-the-driver)); [Step 12](#via-registry-yaml-config) explains when they arrive. Don't keep the revealed credential on the driver: pass it to the client, so it cannot surface in a `repr`.

______________________________________________________________________

## Step 4: Addressing

```
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
```

**The kernel hands your primitives canonical keys.** It refuses a leading `/`, a `..` segment, a null byte and a backslash with `InvalidPath`, and drops empty and `.` segments, so the root in every spelling arrives as `""`. Your primitives never see `./a`, `a//b` or the root as a file. You need no root guard and no alias handling.

`native_path`, `to_key` and `resolve` are the exceptions: they answer for a key the key rule refuses too, passed raw, so each must be **total**, never raising. `to_key(native_path(key))` must return `key`; the conformance suite checks the round trip. `resolve` does no I/O.

______________________________________________________________________

## Step 5: `stat` and `get`

```
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
```

- **`stat()`** returns an [`Entry`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Entry) for the node at the key, or `None`. On a flat namespace it may look up the key alone and be blind to a prefix: where a folder matters, the kernel finds one with a one-item listing. A miss may also be raised, as `NotFound` or `InvalidPath`.
- **`get()`** returns a binary stream. It refuses an absent key, or one that is no file, in whatever shape your storage system has. Here that is `NotFound` for both; the kernel probes and raises `InvalidPath` when a folder is there. The stream ends where your client's own read reports the end of data, so a length or checksum check the client makes there still runs; never stop at a byte count of your own.
- `follow_links=False` matters only to storage with symbolic links: it is the view of `delete`, a `move` source and `delete_folder`, which name the link itself.

`modified_at` is optional on an `Entry`. Leave it out when the storage system does not record one; the kernel reports it as unknown.

______________________________________________________________________

## Step 6: `put` and `delete`

```
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
```

- `content` is `bytes` or a binary stream. Read it in full, as here, or stream it to your storage system.
- `put()` refuses an existing file unless `overwrite`. Where your storage system has a conditional write (an `If-None-Match` header, an exclusive create), make the refusal that one step rather than a check followed by the write. Return a [`PutResult`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.PutResult) with at least `size`; the kernel builds the result's path from the key before your driver writes, so a path that cannot be built never costs a write.
- `delete()` refuses an absent key without removing anything. A storage system whose delete succeeds for a missing key, unlike Redis `DEL`, checks first.
- Parent folders, the root, a write over a folder and a write under a file are the kernel's to handle, before or after your call.

______________________________________________________________________

## Step 7: Listing

```
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
```

`list_page()` returns one [`Page`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Page) of what lies under a folder (`""` is the root):

- With `delimiter="/"`, the immediate files as `entries` and the immediate subfolders as `prefixes`, folder keys without a trailing `/`.
- With `delimiter=None`, every file below the folder, at any depth.
- Return a `cursor` to hand out further pages, `None` on the last one.
- `limit` asks for at most that many items; the kernel passes `limit=1` when it only needs to know whether anything is there. Returning more is safe, as the Redis driver does.

The kernel builds `list_files`, `list_folders`, `iter_children` and `get_folder_info` from these pages. It applies `max_depth` itself, so your driver never sees it. It also omits any listed key that is not canonical, such as one another tool stored with a backslash, and logs the omission.

**A flat driver owes two more things:**

- **Byte order.** Keys come in byte-lexicographic order, a prefix `p` ordered as `p/`, so an item arrives before every key below it. Redis `SCAN` returns keys in no order, which is why this driver collects and sorts.
- **`NotFound` or `InvalidPath` only for nothing.** A listing may raise either only when nothing lies under the prefix, an absent container included. No other call can tell a flat folder from nothing, so the kernel reads those two as an empty folder.

Escape your storage system's wildcard characters when a key becomes a pattern: the `_glob_escape` helper from Step 3 keeps a folder named `w[1]` from matching `w1`.

______________________________________________________________________

## Step 8: Error classification

```
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
```

**Raise whatever your client library raises.** Every driver call runs inside the kernel's error boundary. A native exception leaving it goes to `classify()`, which **returns** the matching `remote_store` error; the kernel raises it chained to the original (`raise ... from exc`), so the traceback keeps the cause. It fills in `path` and `backend` when your error leaves them out. A `remote_store` error your driver raises itself passes through unchanged.

**A refusal about the key may be re-typed.** After a `NotFound`, `InvalidPath`, `AlreadyExists`, `PermissionDenied` or a base `RemoteStoreError`, the kernel probes the keys involved to find what is really there: a folder where a file belongs makes it `InvalidPath`, nothing makes it `NotFound`, and a file at a destination written without `overwrite` makes it `AlreadyExists`. A probe that cannot answer leaves your error standing. So a driver can say "refused" without knowing why, as `copy()` does in [Step 10](#step-10-optional-protocols). An error about the service, such as `BackendUnavailable`, is never probed.

`classify()` returns one of these; a primitive may also raise one directly, as `get()` and `put()` do above.

| `remote_store` error                                                                                                      | Use it for                                                                      |
| ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| [`NotFound`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.NotFound)                             | The key is absent                                                               |
| [`AlreadyExists`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.AlreadyExists)                   | The target exists and `overwrite` is false                                      |
| [`PermissionDenied`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.PermissionDenied)             | Authentication failed, or access was refused                                    |
| [`InvalidPath`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.InvalidPath)                       | The storage system rejected the key, or found the wrong kind of node            |
| [`DirectoryNotEmpty`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.DirectoryNotEmpty)           | `remove_folder()` on a folder that still holds something                        |
| [`BackendUnavailable`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.BackendUnavailable)         | Network error, timeout, service down                                            |
| [`CapabilityNotSupported`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.CapabilityNotSupported) | A primitive a read-only driver cannot perform, or `unwrap()` of a type it lacks |
| [`RemoteStoreError`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.RemoteStoreError)             | Anything else: the fallback, so nothing native ever leaks                       |

**`op`** names the operation that asked, so the same native error can be typed by scope. **`container_absent()`** says whether an exception means the bucket, container or table is gone; the kernel then answers as for an absent path, except on writes, `check_health()` and `close()`, which keep `classify()`'s answer. A storage system with no container, like Redis, returns `False`.

**Errors while a stream is read** arrive after `get()` has returned. The kernel wraps the stream and classifies an `OSError` or `EOFError` it raises, with `op=Op.READ`. If your stream raises anything else mid-read, as a lazy network stream may, list those types in a `stream_catch` attribute (a tuple of exception types), or they reach the caller unmapped. This holds for the async twin's chunk iterator too. **`connection_dead()`** says whether an exception means the connection is gone, from the exception alone and without I/O; the kernel then skips closing the stream it condemned rather than wait on a dead connection a second time, and logs its answer beside a failed write cleanup (an `abort`, a temporary's delete). Answer `True` only when the transport itself is gone, the socket or session, never for an error the next request on the same connection survives.

______________________________________________________________________

## Step 9: Lifecycle

```
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
```

`probe()` backs `check_health()`. Make it the **cheapest possible read-only call that touches the storage**: Redis `PING`, a `HEAD` on an S3 bucket, `SELECT 1` on a database. Its errors go through `classify()` like any other. Only a store that is always healthy, like the in-memory one, may skip it and inherit the protocol's no-op.

`close()` releases resources, and must be safe to call again: the kernel passes on every call, a repeated one included. The kernel marks the backend closed first; with `close_is_terminal = True` it then refuses every later operation on storage, and `unwrap()`, with `BackendUnavailable`, before any key check reaches your driver.

`unwrap()` hands out the native client when the caller asks for its type, and raises `CapabilityNotSupported` otherwise.

**What the kernel cleans up for you.** When a write fails or is cancelled, the kernel calls your write handle's `abort()` (from `open_write`), deletes a temporary it wrote, and closes the caller's async content iterator if it started reading it and stopped short of the end. A write cleanup that fails is logged, never raised, so the caller sees why the write failed. Your `abort()` must work after a `commit()` that failed, and be safe to call twice.

______________________________________________________________________

## Step 10: Optional protocols

```
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
```

Each optional protocol is detected on the driver instance when the backend is constructed: define the method, and the kernel uses it. The kernel has already checked a move or copy's source and, on a flat namespace, that the destination is no folder and lies under no file. A move or copy onto itself never reaches your driver.

- **`copy()`** turns Redis `COPY`'s ambiguous `0` into a bare `RemoteStoreError`. The kernel probes both keys and raises `NotFound` for a missing source or `AlreadyExists` for a taken destination.
- **`rename()`** with `rename_replaces = True` backs `MOVE` and `ATOMIC_MOVE`. Without `rename_replaces`, the kernel moves an existing destination aside first and puts it back if the rename fails.

The full set is in [Optional protocols](#optional-protocols). Without any of them a driver still gets a recursive `delete_folder` (the kernel lists and deletes each file), `get_folder_info` (the kernel adds up a listing) and `read_seekable` (the kernel spools the stream to a temporary file).

______________________________________________________________________

## Step 11: Wrap the driver

```
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
```

The backend class builds its driver and hands it to `DriverBackend`. Two class attributes keep it consistent with the driver:

- **`CAPABILITIES: ClassVar[CapabilitySet]`**: tooling, the registry and the conformance suite read it without instantiating the class. Assign the same constant the driver declares: nothing checks that the two agree, and the instance's `capabilities`, which `Store` gates on, come from the driver.
- **`close_is_terminal: ClassVar[bool]`**: the class default is `False`. If your driver declares `True`, declare it here too; construction refuses a class and driver that disagree.

Construction runs the checks from Steps 2 and 3, so a mis-declared driver fails at `RedisBackend(...)`, not at its first call.

______________________________________________________________________

## Step 12: Register and use

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

Register your backend type before creating a [`Registry`](https://docs.remotestore.dev/stable/reference/api/registry/index.md). YAML loading lives in the `remote_store.ext.yaml` extension and requires the `yaml` extra (`pip install "remote-store[yaml]"`):

```
from remote_store import Registry, register_backend
from remote_store.ext.yaml import from_yaml  # needs: pip install "remote-store[yaml]"

register_backend("redis", RedisBackend)

config = from_yaml("stores.yaml")
with Registry(config) as registry:  # closes instantiated backends on exit
    store = registry.get_store("cache")
    store.write("hello.txt", b"from-registry")
    data = store.read_bytes("hello.txt")
```

```
# stores.yaml
backends:
  redis-main:
    type: redis
    options:
      url: "redis://localhost:6379/0"
      prefix: "app:"
      password: "${REDIS_PASSWORD}"
    retry:
      max_attempts: 5

stores:
  cache:
    backend: redis-main
    root_path: "cache/v2"
```

The `options` mapping is unpacked as keyword arguments to your backend's constructor, so parameter names must match its `__init__` exactly. Two keys arrive changed:

- **Credentials arrive wrapped in [`Secret`](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.Secret).** A string option named `key`, `secret`, `password`, `account_key`, `sas_token`, `connection_string`, `client_secret` or `client_certificate` is wrapped when config is loaded, so its `repr` stays masked. Type such a parameter `str | Secret` and call `.reveal()` where the client needs the value, as Step 3 does. A caller constructing the backend directly may pass a plain `str`.
- **A `retry:` block becomes a `retry=` keyword**, a [`RetryPolicy`](https://docs.remotestore.dev/stable/reference/api/config/#remote_store.RetryPolicy). It is passed only when the block is present, but then it is always passed: a constructor without a `retry` parameter makes the registry raise `ValueError`. Map the policy onto your client's own retry mechanism, and ignore what it cannot express, as `RetryPolicy` documents.

One ownership note: stores from `registry.get_store()` do not own their backend, so `store.close()` is a no-op on them; the registry closes the backends it instantiated. Call `registry.close()` when done, or use `Registry` as a context manager (`with Registry(config) as registry:`).

______________________________________________________________________

## Step 13: Extensions work automatically

Because the kernel makes your driver a complete `Backend`, every remote-store extension works out of the box:

```
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
```

Extensions that require specific capabilities check at runtime. For example, `ext.glob.glob_files()` works with any `LIST`-capable backend; it doesn't need the `GLOB` capability.

______________________________________________________________________

## The async twin

For an async client library, write an [`AsyncDriver`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.AsyncDriver) and subclass [`AsyncDriverBackend`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.AsyncDriverBackend). The members are the same, with three differences:

- The I/O primitives (`stat`, `get`, `put`, `delete`, `list_page`, `probe`) are coroutines, and so is every optional protocol's method except `glob`, which returns an async iterator.
- `aclose()` replaces `close()`.
- `get()` returns an async iterator of `bytes` chunks, and `put()` accepts `bytes` or one.

`classify`, `container_absent`, `connection_dead`, `unwrap`, `native_path`, `to_key` and `resolve` stay synchronous. The optional protocols are the `AsyncSupports*` mirrors. `AsyncBackend` has no `read_seekable` and no `open_atomic`, so the async kernel never asks for `get_range` or `size_probe`, and asks for `open_write` only from `write_atomic`, when `put_is_atomic` is false. The shipped [`AsyncMemoryBackend`](https://docs.remotestore.dev/stable/reference/api/aio/backends/memory/index.md) is a complete example of this route, and [`MemoryBackend`](https://docs.remotestore.dev/stable/reference/api/backends/memory/index.md) of the sync one.

______________________________________________________________________

## Partial-capability backends

Not every backend supports every operation. A read-only HTTP driver declares only what it can do; this is the shipped `ReadOnlyHttpBackend`'s capability set (note there is no `LIST`: plain HTTP has no directory listing):

```
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
```

When a user calls `store.write()` on such a store, `Store` raises `CapabilityNotSupported` before your driver runs. `put()` and `delete()` are still required primitives, so implement them to refuse:

```
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
```

Declaring more than the driver backs is caught early: a driver that adds `COPY` to that set without a `copy()` method makes construction raise `ValueError: driver 'http-readonly' declares COPY without copy`.

______________________________________________________________________

## Testing your backend

remote-store ships a per-topic conformance suite under `tests/backends/conformance/` that validates any backend against the formal backend contract. Backends contributed to the repo plug into this infrastructure and run through the full suite automatically. Standalone backends can either reuse this suite or write focused tests against the same categories.

______________________________________________________________________

### Conformance suite overview

The suite lives in [`tests/backends/conformance/`](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance), split into per-topic files that share the same parameterized `backend` fixture: every registered backend runs the full suite automatically.

| Topic file                                                                                                                                     | Coverage                                                                                                                                                                     | Run with                                                          |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| [`test_identity.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_identity.py)                           | Identity, capabilities, lifecycle, `resolve`, native path round-trip                                                                                                         | `pytest tests/backends/conformance/test_identity.py`              |
| [`test_io.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_io.py)                                       | `exists`, `is_file`/`is_folder`, read, write, delete, `to_key` round-trip                                                                                                    | `pytest tests/backends/conformance/test_io.py`                    |
| [`test_listing.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_listing.py)                             | `list_files`/`list_folders`, `iter_children`, glob, completeness                                                                                                             | `pytest tests/backends/conformance/test_listing.py`               |
| [`test_atomic.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_atomic.py)                               | `write_atomic`, `open_atomic`, `WriteResult`, move/copy semantics                                                                                                            | `pytest tests/backends/conformance/test_atomic.py`                |
| [`test_metadata.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_metadata.py)                           | `get_file_info`/`get_folder_info`, `size`, `modified_at`, aggregates                                                                                                         | `pytest tests/backends/conformance/test_metadata.py`              |
| [`test_streaming.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_streaming.py)                         | Streaming reads, `LAZY_READ` laziness, no native error escaping a stream, resource cleanup                                                                                   | `pytest tests/backends/conformance/test_streaming.py`             |
| [`test_errors.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_errors.py)                               | Typed-error fidelity across read/write/delete/move/copy paths                                                                                                                | `pytest tests/backends/conformance/test_errors.py`                |
| [`test_check_health.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_check_health.py)                   | `check_health()` contract: error mapping never leaks native exceptions                                                                                                       | `pytest tests/backends/conformance/test_check_health.py`          |
| [`test_health_probe_declared.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_health_probe_declared.py) | Structural: every backend probes or declares an exemption; for a class on the kernel, its driver's `probe()` decides (presence only; probe behavior is verified per-backend) | `pytest tests/backends/conformance/test_health_probe_declared.py` |
| [`test_concurrency.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_concurrency.py)                     | Posture-gated concurrency lane: each fixture tested against its declared `concurrency` posture                                                                               | `pytest tests/backends/conformance/test_concurrency.py`           |
| [`test_close_posture.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_close_posture.py)                 | Posture-gated `close()` lane: reusable vs. terminal after close                                                                                                              | `pytest tests/backends/conformance/test_close_posture.py`         |

The directory also carries infrastructure lanes (sync-adapter conformance, large-payload guard, xfail guard, replayed examples) and the async suite under `aio/`; browse [the directory](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance) for the full inventory.

Run the whole suite at once with `pytest tests/backends/conformance/`.

**Extended (Dafny-derived) cases** (error fidelity, precondition ordering, depth filtering, move/copy edge semantics, resource cleanup) are not a separate file. They are individual tests marked [`@pytest.mark.extended_conformance`](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance) spread across the topic files above, so they run with the rest of the suite by default and can be selected on their own:

```
pytest -m extended_conformance
```

Async backends have their own extended sibling, [`test_async_extended.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_async_extended.py), which exercises the `AsyncBackend` contract.

The conformance suite itself is validated by running it against a mathematically verified oracle compiled from the formal Dafny specification (`sdd/formal/MemoryBackend.dfy`). If the oracle passes a test, the test is known-correct. Passing the conformance suite is therefore a strong guarantee of correctness, not just "matches what existing backends happen to do." See [`sdd/formal/README.md`](https://github.com/haalfi/remote-store/blob/master/sdd/formal/README.md) § Compiled Oracle for details.

______________________________________________________________________

### Registering in the conformance fixture (contributing backends)

If you are contributing a backend to remote-store, this is step 3 of [CONTRIBUTING.md § Adding a New Backend](https://docs.remotestore.dev/stable/explanation/contributing/#adding-a-new-backend). The test infrastructure is registry-driven. Four steps: declare facts in two TOML files, add one small factory module under [`tests/backends/fixtures/`](https://github.com/haalfi/remote-store/tree/master/tests/backends/fixtures), and classify your family in the by-name conformance lanes (step 4). The conformance suite then parametrizes every test over your fixture automatically. Registration itself needs no conftest edits, though a backend that needs an external service still adds a server fixture (see the end of this section).

The TOML and Python blocks below show test-infrastructure files, so they are hand-written fences rather than executable snippet regions (the CI drift gate validates the TOML values against the fixture loader instead).

**1. Declare the backend family in `tests/backends/fixtures/backends.toml`:**

```
# tests/backends/fixtures/backends.toml
[backend.redis]
sources           = ["src/remote_store/backends/_redis.py"]
transport         = "fs"
concurrency       = "thread_safe"
flat_namespace    = true          # the driver's namespace is "flat"
self_op_supported = true          # move(p, p) / copy(p, p) is a safe no-op
rejects_write_under_file_ancestor = true  # the kernel always refuses it
```

`transport`, `concurrency`, and the fixture's `stage` / `kind` / `container` fields below are closed vocabularies; their members and semantics are documented authoritatively in the two TOML files' header comments, and the loader rejects unknown values. Things to know here:

- `concurrency` is deliberately defaultless: a new family must state its thread-safety posture or the loader refuses to start.
- The values are declarations of fact, so establish them (is your client library actually thread-safe?) rather than copying the example's.
- Some backends have no exact member. Redis fits neither `transport` nor `container` precisely, so pick the nearest transport (`fs` here is that approximation, not a statement that Redis is a filesystem).
- **`flat_namespace` follows the driver's `namespace` declaration.**
- **`rejects_write_under_file_ancestor = true` on a flat driver.** A flat namespace defaults it to `false`, which skips the conformance cells for a write under a file. The kernel refuses that write on every flat driver, unconditionally, so turn the cells on. The `strict_only` fixture variants some flat backends register exist to run those cells against an opt-in check; a driver on the kernel has nothing to opt into and needs none.

**2. Declare the fixture in `tests/backends/fixtures/fixtures.toml`:**

```
# tests/backends/fixtures/fixtures.toml
[fixture.redis]
backend   = "redis"
stage     = 2
kind      = "real-local"
container = "none"
is_async  = false
```

Per-fixture overrides of `flat_namespace` / `self_op_supported` merge on top of the family defaults; that is how the Azurite emulator (flat) and live ADLS Gen2 (hierarchical) share one `azure` family yet disagree.

Three of these fields deserve extra care. `stage` and `kind` drive collection, `container` is about CI provisioning:

- **`stage` decides when your fixture participates.** Stage 1 fixtures run everywhere; stage 2–3 fixtures are dropped from parametrization unless the session's stage is high enough. The active stage is auto-detected (stage 2 when a Docker daemon is reachable, stage 1 otherwise) and can be forced with `--stage=N` or the `RS_TEST_STAGE` env var. A service-backed fixture like this one belongs in stage 2.
- **`kind = "real-live"`** (live cloud) fixtures must also carry `pytest.mark.live` via the registration's `marks=`; the registry rejects a live fixture without it.
- If CI cannot start your service via `container` (the enum has no member for it, as with Redis here), provision the service yourself and have the factory skip when it is absent; that is step 3's first obligation.

**3. Add a factory module `tests/backends/fixtures/redis.py`:**

The module name matches the fixture name by default (that is how it gets imported); a differently-named or shared module needs a `_MODULE_FOR` entry (see below). The factory is called fresh for **every test**, and the suite runs no cleanup unless you provide one. That gives it four obligations beyond constructing the backend:

- **Skip when infrastructure is absent**: the optional dependency AND the service itself. Factories run at test setup, so `pytest.skip` there is how a fixture self-excludes; a missing reachability check turns every test into a `BackendUnavailable` failure on machines without the daemon.
- **Provision the namespace it hands out**: create the bucket/database/ container the backend points at; the suite assumes writable storage.
- **Isolate per call**: a unique prefix or bucket per invocation, or earlier tests' leftovers show up as baffling `AlreadyExists` / orphan-artifact failures that look like backend bugs.
- **Provide `cleanup=`** to close the backend after each test.

Keep backend/SDK imports *inside* the factory functions: `_load_all()` imports every factory module at conftest import time, so a module-level `import` of an optional dependency would break collection for the whole `tests/backends/` tree on machines without it.

```
import uuid

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

_meta = load_fixture("redis")
_URL = "redis://localhost:6379/0"


def _factory():
    redis = pytest.importorskip("redis", reason="redis-py not installed")
    try:
        redis.Redis.from_url(_URL).ping()
    except redis.RedisError:
        pytest.skip("Redis server not reachable")

    from remote_store.backends._redis import RedisBackend

    # Unique prefix per call = per-test isolation. Redis needs no
    # provisioning (keys spring into existence); a bucket-based backend
    # would create its bucket here.
    return RedisBackend(url=_URL, prefix=f"test-{uuid.uuid4().hex[:8]}:")


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._redis import RedisBackend

        return frozenset(RedisBackend.CAPABILITIES)
    except ImportError:
        return frozenset()


def _cleanup(backend) -> None:
    backend.close()


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
```

`_load_all()` walks `fixtures.toml` and imports the factory module with the same name as each fixture, so a fixture whose module is named differently (or a second fixture sharing one module) needs an entry in the `_MODULE_FOR` map in `tests/backends/fixtures/__init__.py`, or collection dies with `ModuleNotFoundError`. The conformance conftest's `pytest_generate_tests` hook then parametrizes every test that takes a `backend` argument (or `async_backend` for async fixtures) over the registered fixtures:

```
pytest tests/backends/conformance/ -k redis --stage=2
```

Expect this first run to fail in the two `test_identity.py` classification lanes until step 4 below is done.

**4. Classify your family in the by-name conformance lanes.** Two `test_identity.py` declaration sets (atomic-move and seekable) fail loudly for any unclassified family; the failure message names the exact edit. `test_health_probe_declared.py` needs two edits of its own: add your backend module to its import list, since a module missing there is silently not checked, and map your backend class to its driver class in `_DRIVERS`, where an unmapped class on the kernel fails.

If your backend requires an external service (like S3, SFTP, or Azurite), add a session-scoped server fixture in `tests/conftest.py` (where `moto_server` / `sftp_server` / `azurite_server` live), publish its endpoint via `_populate_infra` in `tests/backends/conftest.py` plus a field on `InfraState` in `tests/backends/fixtures/_state.py`, and read `INFRA` from your factory at call time.

______________________________________________________________________

### Capability gating

Backends may declare a subset of capabilities, and the suite skips what a backend cannot do: a read-only backend cleanly skips all write, move, copy, and delete tests without failures. Two mechanisms, in order of preference:

**Class-level filtering** is the primary mechanism: test classes parametrize via `fixture_params(*caps)`, so a backend missing a capability never enters those tests at all.

**Runtime fallback** is the `_require()` helper, for a single test inside a coarsely-filtered class that needs a stricter capability than its siblings:

```
def _require(backend: Backend, *caps: Capability) -> None:
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")
```

Use the same runtime pattern in your own tests:

```
from remote_store import Capability
import pytest

def test_move_preserves_content(backend):
    _require(backend, Capability.MOVE)
    backend.write("src.txt", b"hello")
    backend.move("src.txt", "dst.txt")
    assert backend.read_bytes("dst.txt") == b"hello"
```

A backend declaring only `READ` and `LIST` never enters the `WRITE`, `MOVE`, `COPY`, and `DELETE` lanes at all (class-filtered tests are not generated for it), and any stricter test inside a coarser class self-skips. The suite still passes: absences and skips are not failures.

______________________________________________________________________

### Flat-namespace vs. hierarchical drivers

The `namespace` declaration decides who checks a key's shape, not what the caller sees. On a driver, both namespaces give the same answers:

| Call                                                   | Flat (`"flat"`)                                    | Hierarchical (`"hierarchical"`)                                |
| ------------------------------------------------------ | -------------------------------------------------- | -------------------------------------------------------------- |
| Write to a key that is a folder                        | `InvalidPath`: the kernel checks before the write  | `InvalidPath`: the storage system refuses, the kernel types it |
| Write under a key that is a file                       | `InvalidPath`: the kernel checks before the write  | `InvalidPath`: the storage system refuses, the kernel types it |
| Read, delete or move a folder                          | `InvalidPath`: the kernel probes after the refusal | `InvalidPath`: the kernel probes after the refusal             |
| `delete_folder` / `get_folder_info` on a file          | `InvalidPath`                                      | `InvalidPath`                                                  |
| `delete_folder(recursive=False)` on a non-empty folder | `DirectoryNotEmpty`                                | `DirectoryNotEmpty`                                            |
| `is_folder(path)` for a prefix with no keys            | `False`                                            | `False`                                                        |

What differs is the cost. A flat write pays one `stat` per ancestor and a one-item listing before it runs; a hierarchical write pays no extra check on success. Declare what your storage system really does: a hierarchical declaration on a storage system that lets a key shadow a prefix lets that write through.

The conformance suite reads the shape from the `flat_namespace` flag in `tests/backends/fixtures/backends.toml` (per-fixture overrides in `fixtures.toml` take precedence), and skips the few tests that rely on real directory entries for a flat fixture.

______________________________________________________________________

### Conformance checklist

Before a backend is considered conformant, verify:

| Level             | What                                                                                    | Command                                                                         |
| ----------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Conformance**   | All `tests/backends/conformance/` tests pass or self-skip (declared capability missing) | `pytest tests/backends/conformance/ -k <fixture-name>`                          |
| **Extended**      | All `@pytest.mark.extended_conformance` cases pass or self-skip                         | `pytest -m extended_conformance -k <fixture-name>`                              |
| **Error mapping** | Every native exception is classified, mid-stream ones included; nothing leaks           | [Step 8](#step-8-error-classification)                                          |
| **Repr safety**   | `repr(backend)` does not expose secrets                                                 | `pytest tests/backends/conformance/test_identity.py -k test_repr_masks_secrets` |

Three pitfalls in reading these results:

- **Check stage participation first.** A stage-2/3 fixture is silently dropped from parametrization when the session's stage is lower, and the default stage is 1 on machines without a reachable Docker daemon. Pass `--stage=2` (or set `RS_TEST_STAGE`) before suspecting your registration.
- **The `-k` token is the fixture/family name** (underscores, e.g. `s3_boto3`), not the backend's `name`. A hyphenated `name` like `"s3-boto3"` never matches any test id, so `-k` with it silently selects nothing.
- **Green is only meaningful if your fixture actually ran.** Confirm your fixture id appears in the parametrized test ids (`pytest --collect-only -q ... | grep <fixture-name>`). A handful of passes with thousands deselected, or exit code 5 ("no tests ran"), means the fixture never participated: stage gating or a failed registration, not universal self-skipping.

Skips are expected and acceptable when a backend doesn't declare the relevant capability. Failures (not skips) in either suite are blocking.

______________________________________________________________________

### Standalone backend testing

> **Not contributing to the repo?** Skip the fixture registration above and write focused tests directly. The categories below mirror what the conformance suite verifies.

If you are building a backend outside the remote-store repository, write focused tests covering the same categories the conformance suite verifies. The kernel already holds the path rules and the root, so concentrate on what your driver decides:

#### Happy paths

- Read/write round-trip
- Overwrite behavior (`overwrite=True` and `overwrite=False`)
- List files and folders (recursive and non-recursive), including a folder large enough to span pages if your driver pages
- Move and copy
- Metadata accuracy (`size`, `modified_at`)

#### Error paths

- `read()` on missing file raises `NotFound`
- `write()` on existing file with `overwrite=False` raises `AlreadyExists`
- `delete(missing_ok=False)` on missing file raises `NotFound`
- `delete_folder(recursive=False)` on non-empty folder raises `DirectoryNotEmpty`
- Path naming a wrong type (file path to `get_folder_info`, directory path to `read`) raises `InvalidPath`
- Each native exception your client raises maps to the error you intend, at call time and while a stream is read; an unreachable service raises `BackendUnavailable`

#### Edge cases

- Keys holding your storage system's special characters (wildcards, separators, percent signs) list and read as themselves
- `to_key(native_path(key)) == key`
- Deeply nested paths (`"a/b/c/d/e/file.txt"`)
- `repr(backend)` does not expose credentials or secrets
- Concurrent access (if thread-safety matters)

#### Example test structure

```
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
```

______________________________________________________________________

## Design decisions

### When to declare `SEEKABLE_READ`

Declare it only if `get()` **always** returns a seekable stream with zero overhead. `BytesIO` qualifies. Streams backed by network iterators don't.

`SEEKABLE_READ` is about `read()`, not `read_seekable()`. Every backend's `read_seekable()` returns a seekable stream: with `SupportsRangeRead` the kernel serves it with ranged requests, and without it the kernel passes a seekable stream through or spools a non-seekable one to a temporary file. A driver with ranged reads over a non-seekable `get()` stream implements `SupportsRangeRead` and does not declare `SEEKABLE_READ`.

### When to support `ATOMIC_WRITE`

Support it if your backend can guarantee that readers never see partial content. A single write call that replaces the whole value qualifies (`put_is_atomic = True`), as does a storage-side temporary promoted on commit (`SupportsOpenWrite`) or a rename that replaces atomically (the kernel writes a temporary and renames it). Be honest about the guarantee: the Redis driver's `HSET` is atomic for readers, but its no-overwrite check is a separate call, so two concurrent writers without `overwrite` can both succeed.

### Thread safety

Backends may be called from multiple threads (e.g., `batch_copy` with concurrency). The kernel's only mutable state is the closed flag, so thread safety is your driver's: use locking if its internal state is mutable, as the in-memory driver does. Redis clients are generally thread-safe, so the example needs no explicit locking.

______________________________________________________________________

## Quick reference

### Required driver members

| Member                                                      | Returns                                                                                                       | Notes                                                                         |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `stat(key, follow_links)`                                   | [`Entry`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Entry) or `None`    | `None`, `NotFound` or `InvalidPath` for a miss; flat may be blind to a prefix |
| `get(key)`                                                  | `BinaryIO`                                                                                                    | Refuses an absent key or a non-file in any shape                              |
| `put(key, content, overwrite, metadata)`                    | [`PutResult`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.PutResult)      | Refuses an existing file unless `overwrite`                                   |
| `delete(key)`                                               | `None`                                                                                                        | Refuses an absent key without removing anything                               |
| `list_page(prefix, delimiter, cursor, limit, follow_links)` | [`Page`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.Page)                | Flat: byte order; `NotFound`/`InvalidPath` only for nothing                   |
| `probe()`                                                   | `None`                                                                                                        | Cheapest call that touches the storage                                        |
| `close()`                                                   | `None`                                                                                                        | Release resources (`aclose()` on the async twin)                              |
| `classify(exc, op, key)`                                    | [`RemoteStoreError`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.RemoteStoreError) | Returns, never raises                                                         |
| `container_absent(exc, op)`                                 | `bool`                                                                                                        | Whether the bucket, container or table is gone                                |
| `connection_dead(exc)`                                      | `bool`                                                                                                        | Inspection only, no I/O                                                       |
| `unwrap(type_hint)`                                         | the native handle                                                                                             | `CapabilityNotSupported` for another type                                     |
| `native_path(key)`                                          | `str`                                                                                                         | Total                                                                         |
| `to_key(native_path)`                                       | `str`                                                                                                         | Total; inverts `native_path`                                                  |
| `resolve(key)`                                              | [`ResolutionPlan`](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.ResolutionPlan)     | Total; no I/O                                                                 |

Every member must be present, and every one but `probe()` implemented by your driver or a base class of yours, not inherited from the protocol; construction refuses either omission.

### Declared attributes

| Attribute           | Type                                                                                       | Meaning                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| `name`              | `str`                                                                                      | Unique backend name, carried on every error                                      |
| `namespace`         | `"flat"` or `"hierarchical"`                                                               | Who checks a write's key shape: the kernel, or the storage system                |
| `parents`           | `"none"`, `"implicit"` or `"explicit"`                                                     | Whether folders are objects, and who creates them                                |
| `capabilities`      | [`CapabilitySet`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md) | What the backend supports; each one backed (Step 2)                              |
| `put_is_atomic`     | `bool`                                                                                     | `put()` never exposes partial content                                            |
| `close_is_terminal` | `bool`                                                                                     | Use after `close()` raises `BackendUnavailable`; same value on the backend class |
| `stream_catch`      | tuple of exception types                                                                   | Optional: what a `get()` stream raises beyond `OSError` and `EOFError`           |
| `size_probe`        | callable                                                                                   | Optional: resolves `SEEK_END` for a `get()` stream                               |

### Optional protocols

| Protocol                                                                                                                         | Member                                         | Serves                                                                |
| -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | --------------------------------------------------------------------- |
| [`SupportsRangeRead`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsRangeRead)         | `get_range(key, offset, length)`               | `read_seekable()` by ranged requests                                  |
| [`SupportsOpenWrite`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsOpenWrite)         | `open_write(key, overwrite, metadata)`         | `write_atomic()` and `open_atomic()` through a storage-side temporary |
| [`SupportsAtomicMove`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsAtomicMove)       | `move(src, dst, overwrite)`                    | `MOVE` and `ATOMIC_MOVE`, forwarded whole                             |
| [`SupportsRename`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsRename)               | `rename(src, dst, replace)`, `rename_replaces` | `MOVE`; with `rename_replaces`, also `ATOMIC_MOVE` and `ATOMIC_WRITE` |
| [`SupportsCopy`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsCopy)                   | `copy(src, dst, overwrite)`                    | `COPY`, and `MOVE` as copy-then-delete                                |
| [`SupportsDeleteTree`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsDeleteTree)       | `delete_tree(key)`                             | Recursive `delete_folder()` in one call                               |
| [`SupportsRemoveFolder`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsRemoveFolder)   | `remove_folder(key)`                           | Removing an empty folder; required when `parents` is not `"none"`     |
| [`SupportsEnsureParents`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsEnsureParents) | `ensure_parents(key)`                          | Creating a write's parents; required when `parents == "explicit"`     |
| [`SupportsFolderStats`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsFolderStats)     | `folder_stats(prefix)`                         | `get_folder_info()` from a native aggregate                           |
| [`SupportsGlob`](https://docs.remotestore.dev/stable/reference/api/drivers/#remote_store.drivers.SupportsGlob)                   | `glob(pattern)`                                | `GLOB`                                                                |

______________________________________________________________________

## See also

- [Drivers API reference](https://docs.remotestore.dev/stable/reference/api/drivers/index.md): every protocol, record and kernel class
- [Backend API reference](https://docs.remotestore.dev/stable/reference/api/backend/index.md): the interface the kernel implements for you
- [Error types API reference](https://docs.remotestore.dev/stable/reference/api/errors/index.md): all error classes
- [Backend Adapter Contract](https://docs.remotestore.dev/stable/explanation/design/specs/003-backend-adapter-contract/index.md): formal spec
- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md): all backends and their capabilities
- [Choosing a Backend](https://docs.remotestore.dev/stable/guides/choosing-a-backend/index.md): decision guide for built-in backends
- [Architecture Overview](https://docs.remotestore.dev/stable/explanation/architecture/index.md): how Store, Backend, and extensions fit together
