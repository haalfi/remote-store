# Store API Reference

!!! info "Pre-v1 target API"
    This page describes the **target** v1 Store API surface. It is hand-written
    to capture behavioral guarantees, parameter contracts, and cross-backend
    differences that the auto-generated [Store](store.md) page does not yet
    reflect. As docstrings are corrected, sections will migrate to `:::`
    directives.

---

## `class Store`

A logical remote folder scoped to a root path.

All path arguments are validated and prefixed with `root_path` before being
delegated to the backend. Supports the context-manager protocol
(`with Store(...) as s:`) which calls [`close()`](#close-none) on exit.

### Constructor

```python
Store(backend: Backend, root_path: str = "")
```

Create a store bound to a backend, optionally scoped to *root_path*.

**Parameters:**

- **backend** ([`Backend`](backend.md))
    Backend instance (Local, S3, SFTP, Azure, Memory).
- **root_path** (`str`, default `""`)
    Prefix prepended to every path. `""` means the backend root.

!!! note "Thread safety"
    `Store` is immutable after construction and can be shared across threads.
    Backend thread safety depends on the backend implementation.

---

## Reading

### `read(path) -> BinaryIO`

Return a readable binary stream positioned at the start of *path*.
The caller is responsible for closing the stream (or using a `with` block).

**Parameters:**

- **path** (`str`)
    Store-relative file path.

**Returns:** `BinaryIO` -- readable binary stream positioned at byte 0.

**Raises:** [`NotFound`](errors.md), [`InvalidPath`](errors.md).

---

### `read_bytes(path) -> bytes`

Read the entire file into memory and return `bytes`.

**Parameters:**

- **path** (`str`)
    Store-relative file path.

**Returns:** `bytes`

**Raises:** [`NotFound`](errors.md), [`InvalidPath`](errors.md).

Equivalent to `read(path).read()`.

---

### `read_text(path, *, encoding, errors) -> str`

Read the entire file and decode it as text.

**Parameters:**

- **path** (`str`)
    Store-relative file path.
- **encoding** (`str`, default `"utf-8"`)
    Text encoding, any name accepted by `codecs`.
- **errors** (`str`, default `"strict"`)
    Error handler: `"strict"`, `"ignore"`, `"replace"`, `"backslashreplace"`.
    See `codecs.register_error` for custom handlers.

**Returns:** `str`

**Raises:** [`NotFound`](errors.md), [`InvalidPath`](errors.md),
`UnicodeDecodeError` (when `errors="strict"`).

Equivalent to `read_bytes(path).decode(encoding, errors)`.

---

## Writing

### `write(path, content, *, overwrite) -> None`

Write binary content to *path*. Creates parent folders implicitly.

**Parameters:**

- **path** (`str`)
    Store-relative file path.
- **content** ([`WritableContent`](models.md))
    `bytes` or readable binary stream (`BinaryIO`).
- **overwrite** (`bool`, default `False`)
    If `False`, raises [`AlreadyExists`](errors.md) when *path* exists.

**Raises:** [`AlreadyExists`](errors.md) (when `overwrite=False` and file
exists), [`InvalidPath`](errors.md).

---

### `write_text(path, text, *, encoding, overwrite) -> None`

Write a string to *path*, encoded with the given encoding.

**Parameters:**

- **path** (`str`)
    Store-relative file path.
- **text** (`str`)
    The string to write.
- **encoding** (`str`, default `"utf-8"`)
    Text encoding.
- **overwrite** (`bool`, default `False`)
    If `False`, raises [`AlreadyExists`](errors.md) when *path* exists.

**Raises:** [`AlreadyExists`](errors.md), [`InvalidPath`](errors.md).

Equivalent to `write(path, text.encode(encoding), overwrite=overwrite)`.

---

### `write_atomic(path, content, *, overwrite) -> None`

Write binary content to *path* atomically. If the write fails or is
interrupted, *path* is not left in a partial state.

**Parameters:**

- **path** (`str`)
    Store-relative file path.
- **content** ([`WritableContent`](models.md))
    `bytes` or readable binary stream (`BinaryIO`).
- **overwrite** (`bool`, default `False`)
    If `False`, raises [`AlreadyExists`](errors.md) when *path* exists.

**Raises:** [`CapabilityNotSupported`](errors.md) (if backend lacks
`ATOMIC_WRITE`), [`AlreadyExists`](errors.md), [`InvalidPath`](errors.md).

!!! note
    Most backends implement this as temp-file + rename. See the
    [Backend Behavior Matrix](#backend-behavior-matrix) for details.

---

### `open_atomic(path, *, overwrite) -> Iterator[BinaryIO]`

Context manager that yields a writable binary stream. The file is committed
atomically on successful exit; on exception the partial write is discarded.

**Parameters:**

- **path** (`str`)
    Store-relative file path.
- **overwrite** (`bool`, default `False`)
    If `False`, raises [`AlreadyExists`](errors.md) when *path* exists.

**Returns:** `BinaryIO` -- writable binary stream.

**Raises:** [`CapabilityNotSupported`](errors.md),
[`AlreadyExists`](errors.md), [`InvalidPath`](errors.md).

**Usage:**

```python
with store.open_atomic("data/output.bin", overwrite=True) as f:
    f.write(b"chunk 1")
    f.write(b"chunk 2")
# file is now visible at data/output.bin
```

---

## Deleting

### `delete(path, *, missing_ok) -> None`

Delete a single file.

**Parameters:**

- **path** (`str`)
    Store-relative file path.
- **missing_ok** (`bool`, default `False`)
    If `True`, silently succeeds when *path* does not exist.

**Raises:** [`NotFound`](errors.md) (when `missing_ok=False`),
[`InvalidPath`](errors.md).

---

### `delete_folder(path, *, recursive, missing_ok) -> None`

Delete a folder.

**Parameters:**

- **path** (`str`)
    Store-relative folder path. Must not be `""` (root).
- **recursive** (`bool`, default `False`)
    If `True`, delete all contents first. If `False`, raises
    [`DirectoryNotEmpty`](errors.md) when folder is non-empty.
- **missing_ok** (`bool`, default `False`)
    If `True`, silently succeeds when *path* does not exist.

**Raises:** [`NotFound`](errors.md) (when `missing_ok=False`),
[`DirectoryNotEmpty`](errors.md) (when `recursive=False`),
[`InvalidPath`](errors.md).

---

## Listing and Iteration

### `list_files(path, *, recursive, pattern) -> Iterator[FileInfo]`

Yield [`FileInfo`](models.md) objects for files under *path*.

**Parameters:**

- **path** (`str`)
    Store-relative folder path.
- **recursive** (`bool`, default `False`)
    Descend into subfolders.
- **pattern** (`str | None`, default `None`)
    Glob pattern to filter filenames (e.g. `"*.csv"`).

**Returns:** Iterator of [`FileInfo`](models.md).

---

### `list_folders(path) -> Iterator[FolderEntry]`

Yield immediate subfolders of *path*.

**Parameters:**

- **path** (`str`)
    Store-relative folder path.

**Returns:** Iterator of [`FolderEntry`](#target-types-for-listing-normalization).

**Current behavior:** yields bare folder names (`str`).
**Target behavior:** yields [`FolderEntry`](#target-types-for-listing-normalization) objects with `.name` and `.path`.

---

### `iter_children(path) -> Iterator[PathEntry]`

Yield all immediate children (files and folders) of *path* in a single pass.

**Parameters:**

- **path** (`str`)
    Store-relative folder path.

**Returns:** Iterator of [`PathEntry`](#target-types-for-listing-normalization).

**Current behavior:** yields [`FileInfo`](models.md) for files, bare `str` for folders.
**Target behavior:** yields [`PathEntry`](#target-types-for-listing-normalization) objects -- both [`FileInfo`](models.md) and
[`FolderEntry`](#target-types-for-listing-normalization) satisfy [`PathEntry`](#target-types-for-listing-normalization), so callers get `.name` and `.path` on
every entry without `isinstance` branching.

---

### `glob(pattern) -> Iterator[FileInfo]`

Yield files matching a glob *pattern*, using the backend's native glob
implementation. Requires `Capability.GLOB`.

**Parameters:**

- **pattern** (`str`)
    Glob pattern (e.g. `"data/**/*.parquet"`).

**Returns:** Iterator of [`FileInfo`](models.md).

**Raises:** [`CapabilityNotSupported`](errors.md) (when backend lacks
`GLOB`).

---

### Target types for listing normalization

These types capture the v1 target for uniform listing return types
(see [research](https://github.com/haalfi/remote-store/blob/master/sdd/research/research-store-api-refinement.md) -- Option D).

**`PathEntry`** (Protocol) -- structural type shared by all listing results:

```python
@typing.runtime_checkable
class PathEntry(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def path(self) -> RemotePath: ...
```

**`FolderEntry`** (frozen dataclass):

```python
@dataclasses.dataclass(frozen=True)
class FolderEntry:
    name: str
    path: RemotePath
```

[`FileInfo`](models.md) already satisfies `PathEntry` structurally (has
`.name: str` and `.path: RemotePath`).

!!! note "Ordering and laziness"
    **Ordering is backend-defined** and may vary between backends (e.g.
    lexicographic on S3, OS-dependent on local filesystems). Callers must
    not depend on any particular order.

    **Results are yielded lazily.** Backends may use pagination internally.
    Memory usage stays bounded for large directories.

---

## File Operations

### `move(src, dst, *, overwrite) -> None`

Move (rename) a file from *src* to *dst*. File-only -- to move a folder,
iterate its contents.

**Parameters:**

- **src** (`str`)
    Source file path.
- **dst** (`str`)
    Destination file path.
- **overwrite** (`bool`, default `False`)
    If `False`, raises [`AlreadyExists`](errors.md) when *dst* exists.

**Raises:** [`NotFound`](errors.md),
[`AlreadyExists`](errors.md) (when `overwrite=False`),
[`InvalidPath`](errors.md).

!!! note "Atomicity"
    Atomicity is backend-dependent. Local uses `os.replace` (atomic on same
    filesystem). S3 and Azure use copy-then-delete (not atomic). SFTP
    atomicity depends on the server.

---

### `copy(src, dst, *, overwrite) -> None`

Copy a file from *src* to *dst*. File-only -- to copy a folder, iterate its
contents.

**Parameters:**

- **src** (`str`)
    Source file path.
- **dst** (`str`)
    Destination file path.
- **overwrite** (`bool`, default `False`)
    If `False`, raises [`AlreadyExists`](errors.md) when *dst* exists.

**Raises:** [`NotFound`](errors.md),
[`AlreadyExists`](errors.md) (when `overwrite=False`),
[`InvalidPath`](errors.md).

!!! note "Metadata preservation"
    Metadata preservation is backend-dependent. S3 copies metadata; local
    and SFTP may not preserve modification time or content type.

---

## Metadata

### `exists(path) -> bool`

Return `True` if *path* exists (file or folder).

**Parameters:**

- **path** (`str`)
    Store-relative path.

**Returns:** `bool`

---

### `is_file(path) -> bool`

Return `True` if *path* exists and is a file.

**Parameters:**

- **path** (`str`)
    Store-relative path.

**Returns:** `bool`

---

### `is_folder(path) -> bool`

Return `True` if *path* exists and is a folder.

**Parameters:**

- **path** (`str`)
    Store-relative path.

**Returns:** `bool`

---

### `get_file_info(path) -> FileInfo`

Return a [`FileInfo`](models.md) with size, modification time, and content
type for a single file.

**Parameters:**

- **path** (`str`)
    Store-relative file path.

**Returns:** [`FileInfo`](models.md)

**Raises:** [`NotFound`](errors.md), [`InvalidPath`](errors.md).

---

### `get_folder_info(path) -> FolderInfo`

Return a [`FolderInfo`](models.md) with aggregated size and file count for a
folder.

**Parameters:**

- **path** (`str`)
    Store-relative folder path.

**Returns:** [`FolderInfo`](models.md)

**Raises:** [`NotFound`](errors.md).

---

## Lifecycle

### `ping() -> None`

Verify that the backend is reachable.

**Raises:** [`BackendUnavailable`](errors.md).

---

### `close() -> None`

Release backend resources. Called automatically when used as a context
manager.

---

### `child(subpath) -> Store`

Return a new `Store` scoped to *subpath* under the current root. The child
shares the same backend instance.

**Parameters:**

- **subpath** (`str`)
    Path segment to append to the current root.

**Returns:** [`Store`](store.md)

**Usage:**

```python
data = store.child("data/2024")
data.list_files("")  # lists files under <root>/data/2024/
```

---

## Interop (Backend-Specific)

!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, use the methods
    above.

### `unwrap(type_hint) -> T`

Return the backend's native client object, cast to *type_hint*.

**Parameters:**

- **type_hint** (`type[T]`)
    The expected type of the native client (e.g. `pyarrow.fs.FileSystem`).

**Returns:** `T`

**Raises:** [`CapabilityNotSupported`](errors.md) (when backend cannot
provide the requested type).

**Usage:**

```python
arrow_fs = store.unwrap(pyarrow.fs.FileSystem)
```

---

### `native_path(key) -> str`

Convert a store-relative *key* to the backend's native path representation
(e.g. S3 object key, local filesystem path). Inverse of `to_key()`.

**Parameters:**

- **key** (`str`)
    Store-relative path.

**Returns:** `str`

---

### `to_key(path) -> str`

Convert a backend-native *path* to a store-relative key. Inverse of
`native_path()`.

**Parameters:**

- **path** (`str`)
    Backend-native path string.

**Returns:** `str`

---

### `supports(capability) -> bool`

Check whether the backend supports a given [`Capability`](capabilities.md).

**Parameters:**

- **capability** ([`Capability`](capabilities.md))
    A [`Capability`](capabilities.md) enum member.

**Returns:** `bool`

!!! note
    `supports()` itself is portable -- it works on all backends. Only the
    *capability-gated methods* it guards are backend-specific.

**Usage:**

```python
if store.supports(Capability.GLOB):
    results = store.glob("**/*.csv")
```

---

## Backend Behavior Matrix

How key operations behave across backends. Verify against actual code before
relying on these in production.

| Behavior | Local | S3 | S3-PyArrow | SFTP | Azure | Memory |
|----------|-------|----|------------|------|-------|--------|
| `move()` atomicity | Atomic (same FS) | Copy+delete | Copy+delete | Server-dependent | Copy+delete | Atomic |
| `copy()` preserves metadata | No (new mtime) | Yes | Yes | No | Yes | No |
| `write_atomic()` mechanism | temp+rename | temp+rename | temp+rename | temp+rename | temp+rename | Direct (atomic) |
| Native `glob()` | Yes | Yes | Yes | No | Yes | No |
| `list_files()` ordering | OS-dependent | Lexicographic | Lexicographic | OS-dependent | Lexicographic | Insertion order |

**Related types:** `WritableContent = BinaryIO | bytes`,
[`FileInfo`](models.md), [`FolderInfo`](models.md),
[`RemotePath`](path.md), [`Capability`](capabilities.md).
