# Drivers

`remote_store.drivers` holds the contract kernel and the protocols a backend is written against. A driver implements the wire primitives of one storage system; [`DriverBackend`](#remote_store.drivers.DriverBackend) (sync) or [`AsyncDriverBackend`](#remote_store.drivers.AsyncDriverBackend) (async) wraps it into a complete [`Backend`](https://docs.remotestore.dev/stable/reference/api/backend/index.md) or [`AsyncBackend`](https://docs.remotestore.dev/stable/reference/api/aio/backend/index.md). Each protocol method's docstring states what the kernel relies on that method to do. The [Build Your Own Backend](https://docs.remotestore.dev/stable/guides/custom-backend-guide/index.md) guide walks through writing one.

Construction checks the declarations

Building a `DriverBackend` or `AsyncDriverBackend` raises `ValueError` when a declared `COPY`, `MOVE`, `ATOMIC_MOVE`, `ATOMIC_WRITE` or `GLOB` has no protocol to back it (the [guide's table](https://docs.remotestore.dev/stable/guides/custom-backend-guide/#step-2-declare-capabilities) names what backs each; the other capabilities are taken as declared), when a flat driver has folder objects, when folder objects come without `remove_folder` or explicit parents without `ensure_parents`, or when the class's `close_is_terminal` differs from the driver's.

______________________________________________________________________

## Kernel

### DriverBackend

```
DriverBackend(driver: Driver)
```

Bases: `_KernelCore`, `Backend`

`Backend` implemented once, over a sync driver.

Construct it with a built driver, usually from the `__init__` of a subclass that builds its own.

Parameters:

- **`driver`** (`Driver`) – The built driver.

Raises:

- `ValueError` – If the driver's declarations are not backed by its protocols, it is flat and has folder objects, it has explicit parents and no ensure_parents, it has folder objects and no remove_folder, or the class's own close_is_terminal differs from the driver's.

### AsyncDriverBackend

```
AsyncDriverBackend(driver: AsyncDriver)
```

Bases: `_AsyncKernelCore`, `AsyncBackend`

`AsyncBackend` implemented once, over an async driver.

Construct it with a built driver, usually from the `__init__` of a subclass that builds its own.

Parameters:

- **`driver`** (`AsyncDriver`) – The built driver.

Raises:

- `ValueError` – If the driver's declarations are not backed by its protocols, it is flat and has folder objects, it has explicit parents and no ensure_parents, it has folder objects and no remove_folder, or the class's own close_is_terminal differs from the driver's.

______________________________________________________________________

## Driver protocols

### Driver

Bases: `Protocol`

The fourteen required primitives and the six declared attributes.

Two more attributes are optional and read with defaults: `stream_catch`, the exception types a stream from `get` raises beyond `OSError` and `EOFError`, and `size_probe`, a `SEEK_END` resolver for that stream, which only the sync runtime reads, since only its stream seeks.

`namespace` says what the wire can hold and `stat` can see: on `"flat"` the wire would let a key shadow a prefix or sit under a file, so the kernel checks before every write that it does neither, and `stat` is blind to a prefix; on `"hierarchical"` neither can happen, so every write primitive refuses a folder at its key, or a file above it, without changing anything, in whatever shape the wire has; the kernel types the refusal. `parents` says whether folders are objects. A flat driver with folder objects is refused at construction, since its `stat` could not see them, and so is an explicit one without `ensure_parents`, which could not create a write's parents.

#### stat

```
stat(
    key: str, *, follow_links: bool = True
) -> Entry | None
```

The node at *key*, file or folder, or `None` when absent.

On a flat wire it may be a lookup of the key alone, blind to a prefix and to whatever lies above the key: where a folder matters the kernel finds one there with one `list_page(limit=1)`. With folder objects it returns the folder object at *key*. A miss may also be raised, as `NotFound` or `InvalidPath` (a POSIX `stat` below a file raises ENOTDIR).

`follow_links=False` is the view of the calls that name the entry at their key (`delete`, a `move` source, `delete_folder`): a link is then a non-folder entry, whatever it points to.

#### get

```
get(key: str) -> ReadStream
```

Open the file at *key* for reading.

Refuses an absent key, or one that is no file, in whatever shape the wire has; the kernel types the refusal.

#### put

```
put(
    key: str,
    content: Content,
    *,
    overwrite: bool,
    metadata: Mapping[str, str] | None,
) -> PutResult
```

Write the file at *key*; refuse an existing one unless *overwrite*.

#### delete

```
delete(key: str) -> None
```

Remove the file at *key*; a link there is removed itself, never its target.

Refuses an absent key, or one that is no file, without removing anything, in whatever shape the wire has; the kernel types the refusal. A wire whose delete succeeds for a missing key checks first.

#### list_page

```
list_page(
    prefix: str,
    *,
    delimiter: str | None,
    cursor: object | None = None,
    limit: int | None = None,
    follow_links: bool = True,
) -> Page
```

One page of what lies under folder *prefix* (`""` is the root).

With `delimiter="/"` the page holds the immediate files and the immediate subfolders as `prefixes`; with `None` it holds every file under *prefix*, and the next page is reached through `cursor`.

A *prefix* that is a file, or lies under one, is refused in whatever shape the wire has, or lists nothing; the kernel reads a first-page refusal its probes confirm as no folder as an empty listing. A flat driver owes two more: its keys come in byte-lexicographic order, a prefix `p` ordered as `p/`, so an item arrives before every key below it; and it answers `NotFound` or `InvalidPath` only when nothing lies under *prefix*, an absent container included, since no other call can tell a flat folder from nothing.

`follow_links=False` is `delete_folder`'s view: a link is a non-folder entry, listed as one and never descended into, and a link at *prefix* itself is no folder, so the call refuses it or lists nothing, never its target's entries. `delete_folder` deletes what this view lists, with no `stat` before the listing.

#### probe

```
probe() -> None
```

Health check; must touch the container.

The protocol's own body does nothing, and a driver that subclasses the protocol without declaring `probe` inherits it: that is an exemption from probing, which only a store that is always healthy may take.

#### close

```
close() -> None
```

Release the driver's resources.

#### classify

```
classify(
    exc: Exception, *, op: Op, key: str
) -> RemoteStoreError
```

Map a native exception raised in scope *op* to a typed error.

#### container_absent

```
container_absent(exc: BaseException, *, op: Op) -> bool
```

Whether *exc* says the bucket, container or table is absent.

#### connection_dead

```
connection_dead(exc: BaseException) -> bool
```

Whether *exc* says the connection is dead.

Pure inspection of *exc*, no I/O: the sync `read` stream passes it as `is_fatal` and skips the close of a stream it condemned.

#### unwrap

```
unwrap(type_hint: type[T]) -> T
```

The native handle, when it is of *type_hint*.

#### native_path

```
native_path(key: str) -> str
```

The native address of *key*; total.

#### to_key

```
to_key(native_path: str) -> str
```

The key a native address names; total.

#### resolve

```
resolve(key: str) -> ResolutionPlan
```

How *key* maps to storage; no I/O.

### AsyncDriver

Bases: `Protocol`

The fourteen required primitives and the six declared attributes.

Two more attributes are optional and read with defaults: `stream_catch`, the exception types a stream from `get` raises beyond `OSError` and `EOFError`, and `size_probe`, a `SEEK_END` resolver for that stream, which only the sync runtime reads, since only its stream seeks.

`namespace` says what the wire can hold and `stat` can see: on `"flat"` the wire would let a key shadow a prefix or sit under a file, so the kernel checks before every write that it does neither, and `stat` is blind to a prefix; on `"hierarchical"` neither can happen, so every write primitive refuses a folder at its key, or a file above it, without changing anything, in whatever shape the wire has; the kernel types the refusal. `parents` says whether folders are objects. A flat driver with folder objects is refused at construction, since its `stat` could not see them, and so is an explicit one without `ensure_parents`, which could not create a write's parents.

#### stat

```
stat(
    key: str, *, follow_links: bool = True
) -> Entry | None
```

The node at *key*, file or folder, or `None` when absent.

On a flat wire it may be a lookup of the key alone, blind to a prefix and to whatever lies above the key: where a folder matters the kernel finds one there with one `list_page(limit=1)`. With folder objects it returns the folder object at *key*. A miss may also be raised, as `NotFound` or `InvalidPath` (a POSIX `stat` below a file raises ENOTDIR).

`follow_links=False` is the view of the calls that name the entry at their key (`delete`, a `move` source, `delete_folder`): a link is then a non-folder entry, whatever it points to.

#### get

```
get(key: str) -> ReadStream
```

Open the file at *key* for reading.

Refuses an absent key, or one that is no file, in whatever shape the wire has; the kernel types the refusal.

#### put

```
put(
    key: str,
    content: Content,
    *,
    overwrite: bool,
    metadata: Mapping[str, str] | None,
) -> PutResult
```

Write the file at *key*; refuse an existing one unless *overwrite*.

#### delete

```
delete(key: str) -> None
```

Remove the file at *key*; a link there is removed itself, never its target.

Refuses an absent key, or one that is no file, without removing anything, in whatever shape the wire has; the kernel types the refusal. A wire whose delete succeeds for a missing key checks first.

#### list_page

```
list_page(
    prefix: str,
    *,
    delimiter: str | None,
    cursor: object | None = None,
    limit: int | None = None,
    follow_links: bool = True,
) -> Page
```

One page of what lies under folder *prefix* (`""` is the root).

With `delimiter="/"` the page holds the immediate files and the immediate subfolders as `prefixes`; with `None` it holds every file under *prefix*, and the next page is reached through `cursor`.

A *prefix* that is a file, or lies under one, is refused in whatever shape the wire has, or lists nothing; the kernel reads a first-page refusal its probes confirm as no folder as an empty listing. A flat driver owes two more: its keys come in byte-lexicographic order, a prefix `p` ordered as `p/`, so an item arrives before every key below it; and it answers `NotFound` or `InvalidPath` only when nothing lies under *prefix*, an absent container included, since no other call can tell a flat folder from nothing.

`follow_links=False` is `delete_folder`'s view: a link is a non-folder entry, listed as one and never descended into, and a link at *prefix* itself is no folder, so the call refuses it or lists nothing, never its target's entries. `delete_folder` deletes what this view lists, with no `stat` before the listing.

#### probe

```
probe() -> None
```

Health check; must touch the container.

The protocol's own body does nothing, and a driver that subclasses the protocol without declaring `probe` inherits it: that is an exemption from probing, which only a store that is always healthy may take.

#### aclose

```
aclose() -> None
```

Release the driver's resources.

#### classify

```
classify(
    exc: Exception, *, op: Op, key: str
) -> RemoteStoreError
```

Map a native exception raised in scope *op* to a typed error.

#### container_absent

```
container_absent(exc: BaseException, *, op: Op) -> bool
```

Whether *exc* says the bucket, container or table is absent.

#### connection_dead

```
connection_dead(exc: BaseException) -> bool
```

Whether *exc* says the connection is dead.

Pure inspection of *exc*, no I/O: the sync `read` stream passes it as `is_fatal` and skips the close of a stream it condemned.

#### unwrap

```
unwrap(type_hint: type[T]) -> T
```

The native handle, when it is of *type_hint*.

#### native_path

```
native_path(key: str) -> str
```

The native address of *key*; total.

#### to_key

```
to_key(native_path: str) -> str
```

The key a native address names; total.

#### resolve

```
resolve(key: str) -> ResolutionPlan
```

How *key* maps to storage; no I/O.

______________________________________________________________________

## Records

### Entry

```
Entry(
    key: str,
    kind: Literal["file", "folder"],
    size: int = 0,
    modified_at: datetime = _UNKNOWN_MODIFIED_AT,
    digest: ContentDigest | None = None,
    etag: str | None = None,
    content_type: str | None = None,
    metadata: Mapping[str, str] | None = None,
    extra: dict[str, object] = dict(),
)
```

One node as the driver's wire reports it.

`key` is canonical when the driver reports what the kernel gave it; a key stored by another tool may not be, and the kernel omits such an entry from every listing.

### Page

```
Page(
    entries: tuple[Entry, ...] = (),
    prefixes: tuple[str, ...] = (),
    cursor: object | None = None,
)
```

Whatever one `list_page` call returns.

`prefixes` are folder keys without a trailing `/`. `cursor` is `None` on the last page.

### PutResult

```
PutResult(
    size: int,
    source: Literal["native", "basic"] = "basic",
    digest: ContentDigest | None = None,
    etag: str | None = None,
    version_id: str | None = None,
    last_modified: datetime | None = None,
    metadata: Mapping[str, str] | None = None,
)
```

What a write reports, without its path: the kernel builds the path.

The kernel builds `WriteResult.path` from the canonical key before the driver commits, so a driver never constructs a path that could fail after the bytes land.

### Op

Bases: `Enum`

What asked: the public operation, or one of the kernel's internal scopes.

`classify(exc, op=..., key=...)` receives it so a driver can type the same wire error differently by scope, and the kernel's absent-container answers are decided per value.

______________________________________________________________________

## Optional protocols

Each is detected on the driver instance when the kernel is constructed.

### SupportsRangeRead

Bases: `Protocol`

Ranged reads, which serve `read_seekable`; only the sync runtime has one.

#### get_range

```
get_range(key: str, offset: int, length: int) -> bytes
```

Up to *length* bytes of *key* from *offset*.

### SupportsOpenWrite

Bases: `Protocol`

A wire-side temporary for `write_atomic`, and for `open_atomic` in the sync runtime, the only one with it.

#### open_write

```
open_write(
    key: str,
    *,
    overwrite: bool,
    metadata: Mapping[str, str] | None,
) -> WriteHandle
```

Open a temporary that `commit` promotes to *key*.

### WriteHandle

Bases: `Protocol`

A wire-side temporary that becomes the file on `commit`.

#### write

```
write(data: bytes) -> None
```

Append *data*.

#### commit

```
commit() -> PutResult
```

Promote the temporary to its key.

#### abort

```
abort() -> None
```

Discard the temporary; the key is untouched.

### SupportsAtomicMove

Bases: `Protocol`

A move the wire performs whole; the kernel never sequences its checks.

#### move

```
move(src: str, dst: str, *, overwrite: bool) -> None
```

Move the file *src* to *dst*.

Refuses an absent *src*, or one that is no file, without changing anything, in whatever shape the wire has; the kernel types the refusal. On a hierarchical namespace, refuses a folder at *dst*, *overwrite* or not, without changing anything. On a flat one the kernel has already checked that *dst* is no folder and lies below no file.

### SupportsRename

Bases: `Protocol`

A rename; `rename_replaces` says whether it may replace *dst* atomically.

#### rename

```
rename(src: str, dst: str, *, replace: bool) -> None
```

Rename *src* to *dst*, replacing a file there only when *replace*.

Refuses an absent *src*, or one that is no file, without changing anything, in whatever shape the wire has; the kernel types the refusal. On a hierarchical namespace, refuses a folder at *dst*, *replace* or not, without changing anything, as `rename(2)` and `os.replace` do: the kernel's temp-and-rename write relies on it rather than probing first. On a flat one the kernel has already checked that *dst* is no folder and lies below no file.

### SupportsCopy

Bases: `Protocol`

A copy on the wire.

#### copy

```
copy(src: str, dst: str, *, overwrite: bool) -> None
```

Copy the file *src* to *dst*.

Refuses an absent *src*, or one that is no file, without changing anything, in whatever shape the wire has; the kernel types the refusal. On a hierarchical namespace, refuses a folder at *dst*, *overwrite* or not, without changing anything. On a flat one the kernel has already checked that *dst* is no folder and lies below no file.

### SupportsDeleteTree

Bases: `Protocol`

A tree delete in one call.

#### delete_tree

```
delete_tree(key: str) -> None
```

Remove the folder at *key* and everything under it.

Where folder objects exist (`parents` is not `"none"`), refuses a file, a link (a non-folder entry, never traversed) or an absent key without removing anything, and removes a link below *key* as an entry without following it. With `parents == "none"` it removes what lies under the prefix `key/` and leaves a file named by *key* itself.

### SupportsRemoveFolder

Bases: `Protocol`

Removal of one empty folder; required with folder objects.

#### remove_folder

```
remove_folder(key: str) -> None
```

Remove the empty folder at *key*.

Refuses a non-empty folder, a file or an absent key without removing it, in one step where the wire has one.

### SupportsEnsureParents

Bases: `Protocol`

Parent creation, called before a write; required when `parents == "explicit"`.

#### ensure_parents

```
ensure_parents(key: str) -> None
```

Create every missing folder above *key*.

Refuses a file above *key* without creating anything past it, in whatever shape the wire has (`os.makedirs` raises EEXIST); the kernel types the refusal. *key* itself is the write's to refuse.

### SupportsFolderStats

Bases: `Protocol`

A native aggregate for `get_folder_info`, the value the kernel would compute.

#### folder_stats

```
folder_stats(
    prefix: str,
) -> tuple[int, int, datetime | None]
```

File count, total size and latest known time under *prefix*.

### SupportsGlob

Bases: `Protocol`

Native `glob`; without it a driver must not declare `GLOB`.

#### glob

```
glob(pattern: str) -> Iterator[Entry]
```

The files matching the canonical *pattern*.

______________________________________________________________________

## Async optional protocols

The async mirrors of the protocols above: the same members, as coroutines (`glob` returns an async iterator). `AsyncBackend` has no `read_seekable` and no `open_atomic`, so the async kernel never calls `get_range`, and calls `open_write` only from `write_atomic`.

### AsyncSupportsRangeRead

Bases: `Protocol`

Ranged reads, which serve `read_seekable`; only the sync runtime has one.

#### get_range

```
get_range(key: str, offset: int, length: int) -> bytes
```

Up to *length* bytes of *key* from *offset*.

### AsyncSupportsOpenWrite

Bases: `Protocol`

A wire-side temporary for `write_atomic`, and for `open_atomic` in the sync runtime, the only one with it.

#### open_write

```
open_write(
    key: str,
    *,
    overwrite: bool,
    metadata: Mapping[str, str] | None,
) -> AsyncWriteHandle
```

Open a temporary that `commit` promotes to *key*.

### AsyncWriteHandle

Bases: `Protocol`

A wire-side temporary that becomes the file on `commit`.

#### write

```
write(data: bytes) -> None
```

Append *data*.

#### commit

```
commit() -> PutResult
```

Promote the temporary to its key.

#### abort

```
abort() -> None
```

Discard the temporary; the key is untouched.

### AsyncSupportsAtomicMove

Bases: `Protocol`

A move the wire performs whole; the kernel never sequences its checks.

#### move

```
move(src: str, dst: str, *, overwrite: bool) -> None
```

Move the file *src* to *dst*.

Refuses an absent *src*, or one that is no file, without changing anything, in whatever shape the wire has; the kernel types the refusal. On a hierarchical namespace, refuses a folder at *dst*, *overwrite* or not, without changing anything. On a flat one the kernel has already checked that *dst* is no folder and lies below no file.

### AsyncSupportsRename

Bases: `Protocol`

A rename; `rename_replaces` says whether it may replace *dst* atomically.

#### rename

```
rename(src: str, dst: str, *, replace: bool) -> None
```

Rename *src* to *dst*, replacing a file there only when *replace*.

Refuses an absent *src*, or one that is no file, without changing anything, in whatever shape the wire has; the kernel types the refusal. On a hierarchical namespace, refuses a folder at *dst*, *replace* or not, without changing anything, as `rename(2)` and `os.replace` do: the kernel's temp-and-rename write relies on it rather than probing first. On a flat one the kernel has already checked that *dst* is no folder and lies below no file.

### AsyncSupportsCopy

Bases: `Protocol`

A copy on the wire.

#### copy

```
copy(src: str, dst: str, *, overwrite: bool) -> None
```

Copy the file *src* to *dst*.

Refuses an absent *src*, or one that is no file, without changing anything, in whatever shape the wire has; the kernel types the refusal. On a hierarchical namespace, refuses a folder at *dst*, *overwrite* or not, without changing anything. On a flat one the kernel has already checked that *dst* is no folder and lies below no file.

### AsyncSupportsDeleteTree

Bases: `Protocol`

A tree delete in one call.

#### delete_tree

```
delete_tree(key: str) -> None
```

Remove the folder at *key* and everything under it.

Where folder objects exist (`parents` is not `"none"`), refuses a file, a link (a non-folder entry, never traversed) or an absent key without removing anything, and removes a link below *key* as an entry without following it. With `parents == "none"` it removes what lies under the prefix `key/` and leaves a file named by *key* itself.

### AsyncSupportsRemoveFolder

Bases: `Protocol`

Removal of one empty folder; required with folder objects.

#### remove_folder

```
remove_folder(key: str) -> None
```

Remove the empty folder at *key*.

Refuses a non-empty folder, a file or an absent key without removing it, in one step where the wire has one.

### AsyncSupportsEnsureParents

Bases: `Protocol`

Parent creation, called before a write; required when `parents == "explicit"`.

#### ensure_parents

```
ensure_parents(key: str) -> None
```

Create every missing folder above *key*.

Refuses a file above *key* without creating anything past it, in whatever shape the wire has (`os.makedirs` raises EEXIST); the kernel types the refusal. *key* itself is the write's to refuse.

### AsyncSupportsFolderStats

Bases: `Protocol`

A native aggregate for `get_folder_info`, the value the kernel would compute.

#### folder_stats

```
folder_stats(
    prefix: str,
) -> tuple[int, int, datetime | None]
```

File count, total size and latest known time under *prefix*.

### AsyncSupportsGlob

Bases: `Protocol`

Native `glob`; without it a driver must not declare `GLOB`.

#### glob

```
glob(pattern: str) -> AsyncIterator[Entry]
```

The files matching the canonical *pattern*.

**Related types:** [`Capability`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md), [`CapabilitySet`](https://docs.remotestore.dev/stable/reference/api/capabilities/index.md), [`ResolutionPlan`](https://docs.remotestore.dev/stable/reference/api/models/#remote_store.ResolutionPlan), [`RemoteStoreError`](https://docs.remotestore.dev/stable/reference/api/errors/#remote_store.RemoteStoreError).

## See also

- [Build Your Own Backend](https://docs.remotestore.dev/stable/guides/custom-backend-guide/index.md) — writing a driver, step by step
- [MemoryBackend](https://docs.remotestore.dev/stable/reference/api/backends/memory/index.md) — a shipped backend built on a driver (`MemoryDriver`)
- [AsyncMemoryBackend](https://docs.remotestore.dev/stable/reference/api/aio/backends/memory/index.md) — its async twin (`AsyncMemoryDriver`)
- [Backend](https://docs.remotestore.dev/stable/reference/api/backend/index.md) — the interface the kernel implements
