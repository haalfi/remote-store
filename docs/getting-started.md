# Getting Started

This guide walks you through installing `remote-store`, setting up a backend, and performing your first file operations.

## Installation

Install the core package:

```bash
pip install remote-store
```

Backends that need extra dependencies use extras:

```bash
pip install remote-store[s3]           # Amazon S3 / MinIO
pip install remote-store[s3-pyarrow]  # S3 with PyArrow (high-throughput)
pip install remote-store[sftp]        # SFTP / SSH
```

## Your First Store

Every `remote-store` workflow follows three steps: **configure**, **create a registry**, and **get a store**.

```python
import tempfile
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

# 1. Configure: describe your backends and stores as data
with tempfile.TemporaryDirectory() as tmp:
    config = RegistryConfig(
        backends={"local": BackendConfig(type="local", options={"root": tmp})},
        stores={"data": StoreProfile(backend="local", root_path="data")},
    )

    # 2. Create a registry (use as context manager)
    with Registry(config) as registry:
        # 3. Get a store and use it
        store = registry.get_store("data")

        store.write("hello.txt", b"Hello, world!")
        content = store.read_bytes("hello.txt")
        print(content)  # b'Hello, world!'
```

## Configuration from a Dict

You can also build configuration from a plain dict, making it easy to load from TOML, JSON, or YAML files:

```python
from remote_store import RegistryConfig, Registry

config = RegistryConfig.from_dict({
    "backends": {
        "local": {"type": "local", "options": {"root": "/data"}},
    },
    "stores": {
        "uploads": {"backend": "local", "root_path": "uploads"},
        "reports": {"backend": "local", "root_path": "reports"},
    },
})

with Registry(config) as registry:
    uploads = registry.get_store("uploads")
    reports = registry.get_store("reports")
```

## Core Operations

The `Store` provides a full set of file operations:

| Method | Description |
|--------|-------------|
| `write(path, content)` | Write bytes or a binary stream |
| `write_atomic(path, content)` | Atomic write (temp file + rename) |
| `read(path)` | Open a file for streaming reads |
| `read_bytes(path)` | Read full file content as bytes |
| `exists(path)` | Check if a file or folder exists |
| `is_file(path)` / `is_folder(path)` | Type checks |
| `delete(path)` | Delete a file |
| `delete_folder(path)` | Delete a folder |
| `move(src, dst)` | Move or rename a file |
| `copy(src, dst)` | Copy a file |
| `list_files(path)` | Iterate over files |
| `list_folders(path)` | Iterate over subfolders |
| `get_file_info(path)` | File metadata (`FileInfo`) |
| `get_folder_info(path)` | Folder metadata (`FolderInfo`) |
| `supports(capability)` | Check if the backend supports a capability |
| `to_key(path)` | Convert native/absolute path to store-relative key |
| `close()` | Close the underlying backend |

For the full method signatures and parameters, see the [Store API reference](api/store.md).

## Next Steps

- Browse the [Examples](examples/index.md) for runnable scripts covering each feature
- Read the [API Reference](api/index.md) for full details on every class and method
- Learn about [Backends](backends/index.md) to connect to S3, SFTP, and more
