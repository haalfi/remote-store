# Build Your Own Backend

Write file storage code once. Run it against local files, S3, SFTP, Azure —
or your own custom storage system.

This guide walks you through implementing a custom [`Backend`](api/backend.md) for remote-store.
By the end, you'll have a working backend that plugs into [`Store`](api/store.md),
[`Registry`](api/registry.md), and every extension in the ecosystem.

---

## What you'll build

A **Redis backend** that stores files as Redis keys. It's simple enough to fit
in one module, yet exercises every part of the Backend contract: reads, writes,
listing, metadata, error mapping, and capability declarations.

**Prerequisites:** `pip install remote-store redis`

---

## The Backend contract

Every backend is a subclass of [`Backend`](api/backend.md). The contract is
straightforward:

1. **Declare capabilities** — which operations does your backend support?
2. **Implement abstract members** — 16 methods and 2 properties covering CRUD, listing, and metadata.
3. **Map all exceptions** — native errors must become `remote_store` errors. No leaks.

The [`Store`](api/store.md) class wraps your backend, adds path validation, capability gating,
and scoping. You implement the raw operations; `Store` handles the policy.

---

## Step 1: Scaffold the class

```python
--8<-- "examples/snippets/custom_backend_guide.py:step1-imports"
```

Every backend starts with these imports. The key types:

| Import | Purpose |
|---|---|
| [`Backend`](api/backend.md) | Abstract base class you subclass |
| [`Capability`](api/capabilities.md), [`CapabilitySet`](api/capabilities.md) | Declare supported operations |
| [`NotFound`](api/errors.md), [`AlreadyExists`](api/errors.md), ... | Normalized error types |
| [`FileInfo`](api/models.md), [`FolderEntry`](api/models.md), [`FolderInfo`](api/models.md) | Return types for listing and metadata |
| [`RemotePath`](api/path.md) | Immutable, validated path type |
| `WritableContent` | Type alias: `bytes \| BinaryIO` |

---

## Step 2: Declare capabilities

```python
--8<-- "examples/snippets/custom_backend_guide.py:step2-capabilities"
```

**Capabilities gate Store methods.** If you don't declare `ATOMIC_WRITE`, calls
to `store.write_atomic()` raise `CapabilityNotSupported` automatically — you
don't need to handle it.

The 10 capabilities and what they gate:

| Capability | Store methods |
|---|---|
| `READ` | `read()`, `read_bytes()`, `read_seekable()` |
| `WRITE` | `write()` |
| `DELETE` | `delete()`, `delete_folder()` |
| `LIST` | `list_files()`, `list_folders()`, `iter_children()` |
| `MOVE` | `move()` |
| `COPY` | `copy()` |
| `ATOMIC_WRITE` | `write_atomic()`, `open_atomic()` |
| `METADATA` | `get_file_info()`, `get_folder_info()` |
| `GLOB` | `glob()` |
| `SEEKABLE_READ` | `read()` always returns seekable streams |

---

## Step 3: Constructor and properties

```python
--8<-- "examples/snippets/custom_backend_guide.py:step3-constructor"
```

**Rules:**

- `name` must be a unique string. Used in error messages and the registry.
- `capabilities` returns a [`CapabilitySet`](api/capabilities.md) — immutable, created once.
- Constructor parameters become `options:` in YAML config (more on this later).

---

## Step 4: Internal helpers

Before implementing the abstract methods, add helpers for key management
and error mapping.

```python
--8<-- "examples/snippets/custom_backend_guide.py:step4-helpers"
```

Redis has no concept of folders, so we use key prefixes to simulate a
hierarchical namespace. Files live under `rs:file:<path>`, and folder markers
(optional) under `rs:dir:<path>`.

```python
--8<-- "examples/snippets/custom_backend_guide.py:step4-error-mapping"
```

**The cardinal rule:** backend-native exceptions must never leak. Every Redis
error becomes a `remote_store` error. The `from exc` preserves the original
traceback for debugging.

---

## Step 5: Existence checks

```python
--8<-- "examples/snippets/custom_backend_guide.py:step5-existence"
```

**Key invariants:**

- `exists()` **never raises `NotFound`** — always returns `bool`.
- `""` and `"."` are root aliases. Root always exists and is always a folder.
- `is_file("")` is always `False`. `is_folder("")` is always `True`.

---

## Step 6: Reading

```python
--8<-- "examples/snippets/custom_backend_guide.py:step6-reading"
```

**Notes:**

- `read()` returns a `BinaryIO`. Since we return `BytesIO`, streams are
  seekable — that's why we declared `SEEKABLE_READ`.
- `read_bytes()` can be more efficient than `read().read()` because it avoids
  wrapping in a stream object.
- Both raise `NotFound` for missing files.

Since our `read()` returns seekable streams, we don't need to override
`read_seekable()` — the default implementation detects seekability and
returns the stream as-is.

---

## Step 7: Writing

```python
--8<-- "examples/snippets/custom_backend_guide.py:step7-writing"
```

**Key patterns:**

- `content` is `bytes | BinaryIO`. Normalize with `content if isinstance(content, bytes) else content.read()`.
- **Write creates parent folders implicitly** — in Redis, there's nothing to create, but filesystem-based backends must `mkdir -p`.
- Re-raise your own errors (`AlreadyExists`, `InvalidPath`) before the catch-all `RedisError` handler.
- Even though Store gates `write_atomic()` via capabilities, implement the methods anyway (they're abstract). Raise `CapabilityNotSupported` as a safety net.

---

## Step 8: Deletion

```python
--8<-- "examples/snippets/custom_backend_guide.py:step8-deletion"
```

**Invariants:**

- `delete()` targets files. `delete_folder()` targets folders.
- `missing_ok=True` suppresses `NotFound`.
- `delete_folder(recursive=False)` raises `DirectoryNotEmpty` if the folder has contents.
- You cannot delete root (`""` or `"."`).

---

## Step 9: Listing

```python
--8<-- "examples/snippets/custom_backend_guide.py:step9-listing"
```

**Key rules:**

- `list_files(path="")` lists from root.
- `recursive=False` (default) yields only immediate children.
- `list_folders()` is always non-recursive — only immediate subfolders.
- Non-existent paths yield nothing (no exception).
- [`FileInfo`](api/models.md)`.path` must be a [`RemotePath`](api/path.md).

---

## Step 10: Metadata

```python
--8<-- "examples/snippets/custom_backend_guide.py:step10-metadata"
```

**Contrast with existence checks:**

- `get_file_info()` raises `NotFound` if missing.
- `get_folder_info()` raises `NotFound` if the folder doesn't exist.
- `exists()` never raises — returns `bool`.

---

## Step 11: Move and copy

```python
--8<-- "examples/snippets/custom_backend_guide.py:step11-move-copy"
```

---

## Step 12: Lifecycle methods

```python
--8<-- "examples/snippets/custom_backend_guide.py:step12-lifecycle"
```

`check_health()` should be the **cheapest possible read-only operation**.
Redis `PING` is ideal. For S3 it's a `HEAD` on the bucket. For a database
it's `SELECT 1`.

---

## Step 13: Register and use

### Direct instantiation

```python
--8<-- "examples/snippets/custom_backend_guide.py:step13-direct"
```

### Via Registry (YAML config)

Register your backend type before creating a [`Registry`](api/registry.md):

```python
--8<-- "examples/snippets/custom_backend_guide.py:step13-registry"
```

```yaml
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

The `options` dict is unpacked as `**kwargs` to your constructor. Parameter
names in YAML must match your `__init__` signature exactly.

---

## Step 14: Extensions work automatically

Because your backend implements the `Backend` contract, every remote-store
extension works out of the box:

```python
--8<-- "examples/snippets/custom_backend_guide.py:step14-extensions"
```

Extensions that require specific capabilities will check at runtime. For
example, `ext.glob.glob_files()` works with any `LIST`-capable backend —
it doesn't need the `GLOB` capability.

---

## Partial-capability backends

Not every backend supports every operation. The HTTP backend, for example,
is read-only:

```python
--8<-- "examples/snippets/custom_backend_guide.py:partial-capabilities"
```

When a user calls `store.write()` on an HTTP-backed store, the `Store` layer
raises `CapabilityNotSupported` before your backend code runs. You still need
to implement the abstract methods (Python requires it), but they can raise
`CapabilityNotSupported`:

```python
--8<-- "examples/snippets/custom_backend_guide.py:partial-write"
```

---

## Error mapping checklist

Every backend-native exception must map to one of these:

| remote-store error | When to raise |
|---|---|
| [`NotFound`](api/errors.md) | File/folder doesn't exist (for operations that require it) |
| [`AlreadyExists`](api/errors.md) | Target exists and `overwrite=False` |
| [`PermissionDenied`](api/errors.md) | Auth failure, insufficient permissions |
| [`InvalidPath`](api/errors.md) | Malformed path, null bytes, `..` traversal |
| [`DirectoryNotEmpty`](api/errors.md) | Non-empty folder and `recursive=False` |
| [`BackendUnavailable`](api/errors.md) | Network error, service down |
| [`CapabilityNotSupported`](api/errors.md) | Operation not supported by this backend |

**Pattern:** catch the SDK's base exception class, classify by error
code/type, and raise the appropriate remote-store error with `from exc`.

---

## Testing your backend

remote-store ships two conformance test files that validate any backend against
the formal `BackendContract` specification. Backends contributed to the repo
plug into this infrastructure and run ~50 test scenarios per backend
automatically. Standalone backends can either reuse this suite or write focused
tests against the same categories.

---

### Conformance suite overview

| File | Coverage | Run with |
|---|---|---|
| [`test_conformance.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/test_conformance.py) | BE-001–BE-025 + SAW, ITER, SIO, GLOB, NPR, RES specs: identity, capabilities, `exists`, `is_file`/`is_folder`, read, write, delete, list, streaming, glob, native path, resolution | `pytest tests/backends/test_conformance.py` |
| [`test_conformance_extended.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/test_conformance_extended.py) | 50 Dafny-derived tests: error fidelity, precondition ordering, depth filtering, move/copy semantics, resource cleanup | `pytest -m extended_conformance` |

Both files share the same parameterized `backend` fixture — every registered
backend runs the full suite automatically.

---

### Registering in the conformance fixture (contributing backends)

If you are contributing a backend to remote-store, this is step 3 of
[CONTRIBUTING.md § Adding a New Backend](https://github.com/haalfi/remote-store/blob/master/CONTRIBUTING.md#adding-a-new-backend).
Add your backend to
[`tests/backends/conftest.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conftest.py);
the entire conformance suite then runs against it automatically.

**1. Add an availability guard near the top of `conftest.py`:**

```python
def _redis_available() -> bool:
    try:
        import redis  # noqa: F401
        return True
    except ImportError:
        return False
```

**2. Add a `pytest.param` constant:**

```python
_redis_param = pytest.param(
    "redis",
    marks=pytest.mark.skipif(not _redis_available(), reason="redis-py not installed"),
)
```

If your backend requires an external service (like S3, SFTP, or Azurite), add
a reachability check and a session-scoped server fixture following the existing
`moto_server` / `sftp_server` / `azurite_server` pattern.

**3. Add it to the `backend` fixture's `params` list and `elif` branch:**

```python
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

`conftest.py` already imports `uuid` at the top — ensure yours does too if
you are starting from scratch. Use a unique prefix per test so isolation is
guaranteed even without a full teardown.

---

### Capability gating with `_require()`

Backends may declare a subset of capabilities. The `_require()` helper skips a
test when the backend lacks the needed capability — so a read-only backend
cleanly skips all write, move, copy, and delete tests without failures:

```python
def _require(backend: Backend, *caps: Capability) -> None:
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")
```

Use the same pattern in your own tests:

```python
from remote_store import Capability
import pytest

def test_move_preserves_content(backend):
    _require(backend, Capability.MOVE)
    backend.write("src.txt", b"hello")
    backend.move("src.txt", "dst.txt")
    assert backend.read_bytes("dst.txt") == b"hello"
```

A backend declaring only `READ` and `LIST` will skip every `WRITE`, `MOVE`,
`COPY`, and `DELETE` test. The suite still passes — skips are not failures.

---

### Flat-namespace vs. hierarchical backends

Backends fall into two models that affect a handful of conformance tests.

**Hierarchical** backends (Local, SFTP, Memory) have real directory objects.
Writing a file creates its parent directories; a path can be either a file
*or* a directory, never both.

**Flat-namespace** backends (S3, Azure, HTTP) have no real directory entries.
Folders are virtual — inferred from key prefixes. A path `a/b/c` implies a
prefix `a/b/` but no actual directory object exists.

The extended conformance suite tracks this in a frozenset:

```python
# tests/backends/test_conformance_extended.py
_FLAT_NAMESPACE_BACKENDS = frozenset({"s3", "s3-pyarrow", "azure", "http"})
```

Tests that rely on real directory semantics call `_skip_flat_namespace()` and
self-skip for flat backends. If your new backend is flat-namespace, add its
`backend.name` string to this set.

Key behavioral differences that the conformance tests check:

| Behavior | Hierarchical (Local, SFTP, Memory) | Flat-namespace (S3, Azure, HTTP) |
|---|---|---|
| Write to a path that is an existing directory | Raises `InvalidPath` | Typically allowed (no real directory) |
| `delete_folder(recursive=False)` on non-empty folder | Raises `DirectoryNotEmpty` | Behaviour varies; some tests are skipped |
| Explicit directory creation | Required (mkdir semantics) | Not needed; folders emerge from key prefixes |
| `is_folder(path)` for a prefix with no keys | `False` | `False` |

If your backend is hierarchical (the common case), no action is needed — the
full extended suite applies.

---

### Conformance checklist

Before a backend is considered conformant, verify:

| Level | What | Command |
|---|---|---|
| **Basic** | All `test_conformance.py` tests pass or self-skip (declared capability missing) | `pytest tests/backends/test_conformance.py -k <backend-name>` |
| **Extended** | All `test_conformance_extended.py` tests pass or self-skip | `pytest -m extended_conformance -k <backend-name>` |
| **Error mapping** | Every native exception maps to a `remote_store` error — nothing leaks | Error mapping checklist above |
| **Repr safety** | `repr(backend)` does not expose secrets | `test_repr_masks_secrets` in basic suite |

Skips are expected and acceptable when a backend doesn't declare the relevant
capability. Failures (not skips) in either suite are blocking.

---

### Standalone backend testing

> **Not contributing to the repo?** Skip the fixture registration above and
> write focused tests directly. The categories below mirror what the
> conformance suite verifies.

If you are building a backend outside the remote-store repository, write
focused tests covering the same categories the conformance suite verifies:

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
- Path naming a wrong type (file path to `get_folder_info`, directory path to
  `read`) raises `InvalidPath`
- Backend unavailable raises `BackendUnavailable`

#### Edge cases

- Empty path (`""`) and root alias (`"."`) — root always exists and is always a folder
- `is_file("")` always returns `False`; `exists("")` never raises
- Deeply nested paths (`"a/b/c/d/e/file.txt"`)
- Non-existent paths to `list_files` / `list_folders` yield nothing (no exception)
- `repr(backend)` does not expose credentials or secrets
- Concurrent access (if thread-safety matters)

#### Example test structure

```python
--8<-- "examples/snippets/custom_backend_guide.py:test-examples"
```

---

## Design decisions

### When to declare `SEEKABLE_READ`

Declare it only if `read()` **always** returns a seekable stream with zero
overhead. `BytesIO` qualifies. Streams backed by network iterators don't.

If your `read()` returns a non-seekable stream, don't worry — `Store` handles
it. `read_seekable()` will spool to a temp file automatically. You can also
override `read_seekable()` for an optimized path (like Azure's HTTP Range
reader).

### When to support `ATOMIC_WRITE`

Support it if your backend can guarantee that readers never see partial content.
Filesystem backends use temp-file-and-rename. Databases can use transactions.
If your backend's writes are inherently atomic (single Redis `HSET`), you could
declare it — but be honest about the guarantee. "Atomic at the key level"
isn't the same as "atomic rename of a visible path."

### Thread safety

Backends may be called from multiple threads (e.g., `batch_copy` with
concurrency). Use locking if your internal state is mutable. Redis clients
are generally thread-safe, so our example doesn't need explicit locking.

---

## Quick reference

### Abstract methods (must implement)

| Method | Returns | Raises on error |
|---|---|---|
| `name` (property) | `str` | -- |
| `capabilities` (property) | [`CapabilitySet`](api/capabilities.md) | -- |
| `exists(path)` | `bool` | Never raises [`NotFound`](api/errors.md) |
| `is_file(path)` | `bool` | -- |
| `is_folder(path)` | `bool` | -- |
| `read(path)` | `BinaryIO` | [`NotFound`](api/errors.md) |
| `read_bytes(path)` | `bytes` | [`NotFound`](api/errors.md) |
| `write(path, content, overwrite)` | `None` | [`AlreadyExists`](api/errors.md) |
| `write_atomic(path, content, overwrite)` | `None` | [`AlreadyExists`](api/errors.md), [`CapabilityNotSupported`](api/errors.md) |
| `open_atomic(path, overwrite)` | `ContextManager[BinaryIO]` | [`AlreadyExists`](api/errors.md), [`CapabilityNotSupported`](api/errors.md) |
| `delete(path, missing_ok)` | `None` | [`NotFound`](api/errors.md) |
| `delete_folder(path, recursive, missing_ok)` | `None` | [`NotFound`](api/errors.md), [`DirectoryNotEmpty`](api/errors.md) |
| `list_files(path, recursive)` | `Iterator[`[`FileInfo`](api/models.md)`]` | -- |
| `list_folders(path)` | `Iterator[`[`FolderEntry`](api/models.md)`]` | -- |
| `get_file_info(path)` | [`FileInfo`](api/models.md) | [`NotFound`](api/errors.md) |
| `get_folder_info(path)` | [`FolderInfo`](api/models.md) | [`NotFound`](api/errors.md) |
| `move(src, dst, overwrite)` | `None` | [`NotFound`](api/errors.md), [`AlreadyExists`](api/errors.md) |
| `copy(src, dst, overwrite)` | `None` | [`NotFound`](api/errors.md), [`AlreadyExists`](api/errors.md) |

### Optional overrides

| Method | Default behavior |
|---|---|
| `read_seekable(path)` | Spools non-seekable streams to temp file |
| `iter_children(path)` | Chains `list_files()` + `list_folders()` |
| `glob(pattern)` | Raises `CapabilityNotSupported` |
| `to_key(native_path)` | Identity function |
| `native_path(path)` | Identity function |
| `check_health()` | No-op |
| `close()` | No-op |
| `unwrap(type_hint)` | Raises `CapabilityNotSupported` |

---

## See also

- [Backend API reference](api/backend.md) — full method documentation
- [Error types API reference](api/errors.md) — all error classes
- [Backend Adapter Contract](design/specs/003-backend-adapter-contract.md) — formal spec
- [Capabilities Matrix](capabilities-matrix.md) — all backends and their capabilities
- [Choosing a Backend](choosing-a-backend.md) — decision guide for built-in backends
- [Architecture Overview](architecture.md) — how Store, Backend, and extensions fit together
