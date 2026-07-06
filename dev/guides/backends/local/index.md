# Local Backend

The local backend stores files on the local filesystem. It is built-in and requires no extra dependencies.

## Installation

Built-in — no extra dependencies. Available with any `remote-store` install.

## Usage

```
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

| Option | Type  | Description                                |
| ------ | ----- | ------------------------------------------ |
| `root` | `str` | Root directory for file storage (required) |

## Capabilities

All capabilities are supported except `USER_METADATA` — passing non-empty `metadata=` to a Local-backed store raises `CapabilityNotSupported`. The local backend is otherwise the reference implementation. See the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) for full details.

## Caveats

- **`overwrite=False` has a TOCTOU race.** The exists-check and write are separate operations. Concurrent writers can both pass the check and overwrite each other.
- **`move()` uses `shutil.move()`**, which delegates to `os.rename()` on the same filesystem (atomic) but falls back to copy+delete across filesystems. `write_atomic()` uses `os.replace()` and is truly atomic.

See the [Concurrency and Atomicity Guarantees](https://docs.remotestore.dev/stable/explanation/concurrency/index.md) guide for details.

## See also

- [Capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md)
- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md)
- [Example script](https://docs.remotestore.dev/stable/tutorial/examples/quickstart/index.md)

## API Reference

## LocalBackend

```
LocalBackend(root: str)
```

Bases: `Backend`

Local filesystem backend using only the Python standard library.

`move()` uses `shutil.move`, which calls `os.rename` for same-filesystem moves (atomic) but falls back to copy-then-delete for cross-filesystem moves (not atomic). `ATOMIC_MOVE` is declared because within-root moves are always same-filesystem.

Parameters:

- **`root`** (`str`) – Absolute path to the root directory on the local filesystem.

### resolve

```
resolve(path: str) -> ResolutionPlan
```

Return a `ResolutionPlan` with local filesystem details.

Parameters:

- **`path`** (`str`) – Backend-relative key.

Returns:

- `ResolutionPlan` – Plan with kind="local" and details containing
- `ResolutionPlan` – root and absolute_path.
