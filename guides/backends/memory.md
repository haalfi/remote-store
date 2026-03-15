# Memory Backend

The memory backend stores files in an in-process tree data structure. Zero dependencies, no filesystem access, no network. Always available — no optional extra needed.

**Primary use cases:** unit testing (no temp-dir setup/teardown), interactive exploration, documentation examples, CI speed.

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

All 8 capabilities are supported: `READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`.

`write_atomic()` behaves identically to `write()` — in-memory writes are inherently atomic.

## Folder Semantics

Folders are explicit tree nodes, not virtual prefixes:

- `write("a/b/c.txt", data)` creates intermediate directory nodes for `a` and `a/b`.
- Deleting the last file in a directory does **not** auto-prune the parent. The empty folder persists until explicitly removed via `delete_folder()`.
- `delete_folder(path, recursive=False)` on a non-empty folder raises `DirectoryNotEmpty`.

This matches `LocalBackend` semantics exactly.

## Thread Safety

All operations are serialized under a single lock. The lock is never held during caller consumption of returned data (streams, iterators).

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

- [Capabilities matrix](../capabilities-matrix.md)
- [API reference](../api/store.md)
- [Example script](https://github.com/haalfi/remote-store/blob/master/examples/memory_backend.py)
