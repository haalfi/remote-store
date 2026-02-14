# remote-store

Backend-agnostic remote storage abstraction for Python. One API for local files, S3, Azure Blob, SFTP, and more.

## Features

- **Backend-agnostic** file operations through a single `Store` API
- **Streaming-first** I/O for memory-efficient large file handling
- **Atomic writes** with capability-driven backend support
- **Config-as-code** with `RegistryConfig` and `from_dict()` for easy setup
- **Type-safe** with full mypy strict mode compliance
- **Zero framework dependencies** — works with any sync codebase

## Installation

```bash
pip install remote-store
```

## Quick Start

```python
import tempfile
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

# Create a config pointing to a local directory
with tempfile.TemporaryDirectory() as tmp:
    config = RegistryConfig(
        backends={"local": BackendConfig(type="local", options={"root": tmp})},
        stores={"data": StoreProfile(backend="local", root_path="data")},
    )

    with Registry(config) as registry:
        store = registry.get_store("data")

        store.write("hello.txt", b"Hello, world!")
        content = store.read_bytes("hello.txt")
        print(content)  # b'Hello, world!'
```

## Configuration

Configuration is declarative and immutable. You can build it from Python objects or parse it from a dict (e.g. loaded from TOML/JSON):

```python
from remote_store import RegistryConfig

config = RegistryConfig.from_dict({
    "backends": {
        "local": {"type": "local", "options": {"root": "/data"}},
    },
    "stores": {
        "uploads": {"backend": "local", "root_path": "uploads"},
        "reports": {"backend": "local", "root_path": "reports"},
    },
})
```

## API Overview

The `Store` class provides all file operations:

| Method | Description |
|--------|-------------|
| `write(path, content)` | Write bytes or a binary stream to a file |
| `write_atomic(path, content)` | Write atomically (temp file + rename) |
| `read(path)` | Open a file for streaming reads (`BinaryIO`) |
| `read_bytes(path)` | Read full file content as `bytes` |
| `exists(path)` | Check if a file or folder exists |
| `is_file(path)` / `is_folder(path)` | Type checks |
| `delete(path)` | Delete a file |
| `delete_folder(path)` | Delete a folder |
| `move(src, dst)` | Move or rename a file |
| `copy(src, dst)` | Copy a file |
| `list_files(path)` | Iterate over `FileInfo` objects |
| `list_folders(path)` | Iterate over subfolder names |
| `get_file_info(path)` | Get file metadata (`FileInfo`) |
| `get_folder_info(path)` | Get folder metadata (`FolderInfo`) |

All write/move/copy methods accept `overwrite=True` to replace existing files.

## Examples

See the [`examples/`](examples/) directory for runnable scripts:

- **[quickstart.py](examples/quickstart.py)** — Minimal config, write, and read
- **[file_operations.py](examples/file_operations.py)** — Read, write, delete, move, copy, list, metadata
- **[streaming_io.py](examples/streaming_io.py)** — Streaming writes and reads with `BytesIO`
- **[atomic_writes.py](examples/atomic_writes.py)** — Atomic writes and overwrite semantics
- **[configuration.py](examples/configuration.py)** — Config-as-code, `from_dict()`, multiple stores
- **[error_handling.py](examples/error_handling.py)** — Catching `NotFound`, `AlreadyExists`, etc.

Interactive Jupyter notebooks are available in [`examples/notebooks/`](examples/notebooks/).

## Supported Backends

| Backend | Status | Install |
|---------|--------|---------|
| Local filesystem | Built-in | `pip install remote-store` |
| Amazon S3 / MinIO | Planned | `pip install remote-store[s3]` |
| Azure Blob / ADLS | Planned | `pip install remote-store[azure]` |
| SFTP / SSH | Planned | `pip install remote-store[sftp]` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the spec-driven development workflow, code style, and how to add new backends.

## License

MIT
