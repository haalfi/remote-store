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

All capabilities are supported except `USER_METADATA` — passing non-empty `metadata=` to a Local-backed store raises `CapabilityNotSupported`. The local backend is otherwise the reference implementation.
See the [capabilities matrix](../../reference/capabilities-matrix.md) for full details.

## Caveats

- **`overwrite=False` has a TOCTOU race.** The exists-check and write are separate operations. Concurrent writers can both pass the check and overwrite each other.
- **`move()` uses `shutil.move()`**, which delegates to `os.rename()` on the same filesystem (atomic) but falls back to copy+delete across filesystems. `write_atomic()` uses `os.replace()` and is truly atomic.

See the [Concurrency and Atomicity Guarantees](../../explanation/concurrency.md) guide for details.

## See also

- [Capabilities matrix](../../reference/capabilities-matrix.md)
- [API reference](../../reference/api/store.md)
- [Example script](../../../examples/getting_started/quickstart.py)

## API Reference

::: remote_store.backends.LocalBackend
