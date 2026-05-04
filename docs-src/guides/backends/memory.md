# Memory Backend

The memory backend stores files in an in-process tree data structure. Zero dependencies, no filesystem access, no network. Always available — no optional extra needed.

**Primary use cases:** unit testing (no temp-dir setup/teardown), interactive exploration, documentation examples, CI speed.

## Installation

Built-in — no extra dependencies. Available with any `remote-store` install.

## Usage

```python
from remote_store import Store
from remote_store.backends import MemoryBackend

backend = MemoryBackend()
store = Store(backend=backend, root_path="data")

store.write_text("hello.txt", "Hello, world!")
print(store.read_text("hello.txt"))  # 'Hello, world!'
```

### Via Registry

```python
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={"mem": BackendConfig(type="memory")},
    stores={"data": StoreProfile(backend="mem", root_path="data")},
)

with Registry(config) as registry:
    store = registry.get_store("data")
    store.write_text("readme.txt", "Hello!")
```

## Options

`MemoryBackend()` takes no constructor arguments. The backend starts empty.

## Capabilities

Supports all capabilities except `GLOB` (no native pattern matching — use `ext.glob.glob_files()` as a portable fallback) and `LAZY_READ` (all data lives in process memory; streams wrap pre-loaded bytes).
See the [capabilities matrix](../../reference/capabilities-matrix.md) for full details.

`write_atomic()` behaves identically to `write()` — in-memory writes are inherently atomic.

## Folder Semantics

Folders are explicit tree nodes, not virtual prefixes:

- `write("a/b/c.txt", data)` creates intermediate directory nodes for `a` and `a/b`.
- Deleting the last file in a directory does **not** auto-prune the parent. The empty folder persists until explicitly removed via `delete_folder()`.
- `delete_folder(path, recursive=False)` on a non-empty folder raises `DirectoryNotEmpty`.

This matches `LocalBackend` semantics exactly.

## Thread Safety

All operations are thread-safe. Mutations are serialized under a lock.
The lock is never held while you iterate results — listing operations
(`list_files`, `list_folders`, `iter_children`) snapshot state under the
lock and build results lazily outside it, reducing lock contention for
concurrent workloads.

## Testing with MemoryBackend

Replace `LocalBackend` + `tempfile.TemporaryDirectory` in your tests:

```python
import pytest
from remote_store import Store
from remote_store.backends import MemoryBackend

@pytest.fixture
def store():
    return Store(backend=MemoryBackend(), root_path="test")

def test_write_and_read(store):
    store.write("file.txt", b"content")
    assert store.read_bytes("file.txt") == b"content"
```

## See also

- [Capabilities matrix](../../reference/capabilities-matrix.md)
- [API reference](../../reference/api/store.md)
- [Example script](../../../examples/advanced/memory_backend.py)

## API Reference

::: remote_store.backends.MemoryBackend
