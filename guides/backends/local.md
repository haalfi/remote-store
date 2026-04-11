# Local Backend

The local backend stores files on the local filesystem. It is built-in and requires no extra dependencies.

## Installation

Built-in — no extra dependencies. Available with any `remote-store` install.

## Usage

```python
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

config = RegistryConfig(
    backends={"local": BackendConfig(type="local", options={"root": "/data"})},
    stores={"files": StoreProfile(backend="local", root_path="files")},
)

with Registry(config) as registry:
    store = registry.get_store("files")
    store.write_text("readme.txt", "Hello!")
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `root` | `str` | Root directory for file storage (required) |

## Capabilities

All 12 capabilities are supported. The local backend is the reference implementation.

| Capability | Supported | Notes |
|------------|-----------|-------|
| `READ` | Yes | |
| `WRITE` | Yes | Creates intermediate directories automatically |
| `DELETE` | Yes | |
| `LIST` | Yes | |
| `MOVE` | Yes | `shutil.move()` -- atomic on same filesystem, copy+delete across filesystems |
| `COPY` | Yes | |
| `ATOMIC_WRITE` | Yes | `os.replace()` -- truly atomic |
| `ATOMIC_MOVE` | Yes | `os.replace()` on same filesystem |
| `METADATA` | Yes | |
| `GLOB` | Yes | Native `pathlib.glob()` |
| `SEEKABLE_READ` | Yes | OS file descriptors are natively seekable |
| `LAZY_READ` | Yes | Data is read from the filesystem on demand |

## Caveats

- **`overwrite=False` has a TOCTOU race.** The exists-check and write are separate operations. Concurrent writers can both pass the check and overwrite each other.
- **`move()` uses `shutil.move()`**, which delegates to `os.rename()` on the same filesystem (atomic) but falls back to copy+delete across filesystems. `write_atomic()` uses `os.replace()` and is truly atomic.

See the [Concurrency and Atomicity Guarantees](../concurrency.md) guide for details.

## See also

- [Capabilities matrix](../capabilities-matrix.md)
- [API reference](../api/store.md)
- [Example script](../examples/quickstart.md)
