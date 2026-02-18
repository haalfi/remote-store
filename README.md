<p align="center">
  <img src="assets/logo.png" width="320">
</p>

<h1 align="center">remote-store</h1>

<p align="center">
  One simple API for file storage: swappable backends, zero reinvention.
</p>

`remote-store` gives you one simple API to read, write, list, and delete files.
The same methods work whether your files live on disk, in S3, on an SFTP server,
or anywhere else. You just swap the backend config.

That's the whole trick.

Reads and writes stream by default, so large files just work.
Under the hood, each backend delegates to the library you'd pick anyway
(`boto3`, `paramiko`, `azure-storage-blob`, …). This package doesn't
reinvent file I/O. It just gives every backend the same simple front door.

## What you get

- **One `Store`, many backends:** local fs, S3, SFTP, Azure Blob, more to come
- **Just the basics:** read, write, list, delete, exists. No magic, no surprises
- **Battle-tested I/O under the hood:** backends wrap `boto3`, `paramiko`, etc.
- **Swappable via config:** switch backends without touching application code
- **Streaming by default:** reads and writes handle large files without blowing up memory
- **Atomic writes** where the backend supports it
- **Typed & tested:** strict mypy, spec-driven test suite

## Installation

```bash
pip install remote-store
```

Backends that need extra dependencies use extras:

```bash
pip install remote-store[s3]      # Amazon S3 / MinIO
pip install remote-store[sftp]    # SFTP / SSH
pip install remote-store[azure]   # Azure Blob / ADLS (planned)
```

## Quick Start

```python
import tempfile
from remote_store import BackendConfig, RegistryConfig, Registry, StoreProfile

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

Switch to S3 by changing the config. The rest of the code stays the same:

```python
config = RegistryConfig(
    backends={"s3": BackendConfig(type="s3", options={"bucket": "my-bucket"})},
    stores={"data": StoreProfile(backend="s3", root_path="data")},
)
```

## Configuration

Configuration is declarative and immutable. Build it from Python objects or parse it from a dict (e.g. loaded from TOML/JSON):

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

## Store API

**Read & write**

|Method                       |Description                 |
|-----------------------------|----------------------------|
|`read(path)`                 |Streaming read (`BinaryIO`) |
|`read_bytes(path)`           |Full content as `bytes`     |
|`write(path, content)`       |Write bytes or binary stream|
|`write_atomic(path, content)`|Write via temp file + rename|

**Browse & inspect**

|Method                             |Description                     |
|-----------------------------------|--------------------------------|
|`list_files(path)`                 |Iterate `FileInfo` objects      |
|`list_folders(path)`               |Iterate subfolder names         |
|`exists(path)`                     |Check if a file or folder exists|
|`is_file(path)` / `is_folder(path)`|Type checks                     |
|`get_file_info(path)`              |File metadata (`FileInfo`)      |
|`get_folder_info(path)`            |Folder metadata (`FolderInfo`)  |

**Manage**

|Method               |Description    |
|---------------------|---------------|
|`delete(path)`       |Delete a file  |
|`delete_folder(path)`|Delete a folder|
|`move(src, dst)`     |Move or rename |
|`copy(src, dst)`     |Copy a file    |

All write/move/copy methods accept `overwrite=True` to replace existing files.

## Supported Backends

|Backend          |Status    |Extra                |
|-----------------|----------|---------------------|
|Local filesystem |Built-in  |                     |
|Amazon S3 / MinIO|Built-in  |`remote-store[s3]`   |
|SFTP / SSH       |Built-in  |`remote-store[sftp]` |
|Azure Blob / ADLS|Planned   |`remote-store[azure]`|

## Examples

Runnable scripts in [`examples/`](examples/):

|Script                                           |What it shows                                  |
|-------------------------------------------------|-----------------------------------------------|
|[quickstart.py](examples/quickstart.py)          |Minimal config, write, read                    |
|[file_operations.py](examples/file_operations.py)|Read, write, delete, move, copy, list, metadata|
|[streaming_io.py](examples/streaming_io.py)      |Streaming writes and reads with `BytesIO`      |
|[atomic_writes.py](examples/atomic_writes.py)    |Atomic writes and overwrite semantics          |
|[configuration.py](examples/configuration.py)    |Config-as-code, `from_dict()`, multiple stores |
|[error_handling.py](examples/error_handling.py)   |Catching `NotFound`, `AlreadyExists`, etc.     |

Interactive Jupyter notebooks are available in [`examples/notebooks/`](examples/notebooks/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the spec-driven development workflow, code style, and how to add new backends.

## License

MIT
