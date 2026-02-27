<p align="center">
  <img src="https://raw.githubusercontent.com/haalfi/remote-store/master/assets/logo.png" width="320" alt="remote-store logo">
</p>

<h1 align="center">remote-store</h1>

<p align="center">
  One simple API for file storage. Local, S3, SFTP, Azure. Same methods, swappable backends, zero reinvention.
</p>

<p align="center">
  <a href="https://pypi.org/project/remote-store/"><img src="https://img.shields.io/pypi/v/remote-store" alt="PyPI version"></a>
  <a href="https://pypi.org/project/remote-store/"><img src="https://img.shields.io/pypi/pyversions/remote-store" alt="Python versions"></a>
  <a href="https://github.com/haalfi/remote-store/actions/workflows/ci.yml"><img src="https://github.com/haalfi/remote-store/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://remote-store.readthedocs.io/"><img src="https://readthedocs.org/projects/remote-store/badge/?version=latest" alt="Documentation Status"></a>
  <a href="https://github.com/haalfi/remote-store/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/remote-store" alt="License"></a>
</p>

> **Alpha software.** The API may change between minor versions. Not recommended
> for production use yet. See the [changelog](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
> for what's new, and [open an issue](https://github.com/haalfi/remote-store/issues) if something breaks.

`remote-store` gives you one simple API to read, write, list, and delete files.
The same methods work whether your files live on disk, in S3, on an SFTP server,
or anywhere else. You just swap the backend config.

That's the whole trick.

### Who is this for?

- **Citizen developers** -- analysts, scientists, and domain experts who write Python but shouldn't need to learn `boto3`, `paramiko`, or cloud-specific SDKs just to read and write files.
- **Platform teams** -- engineers who set up the infrastructure and want to hand their colleagues a simple, safe API that can't be misused.
- **Anyone tired of rewriting storage glue** -- if you've wrapped S3 or SFTP access more than once, this is that wrapper, tested and maintained.

The library was born from enabling citizen-developer teams: the config is immutable so non-experts can't accidentally break state, errors are clear instead of raw SDK tracebacks, and streaming just works without tuning buffer sizes.

Reads and writes stream by default, so large files just work.
Under the hood, each backend delegates to the library you'd pick anyway
(`boto3`, `paramiko`, `azure-storage-file-datalake`, …). This package doesn't
reinvent file I/O. It just gives every backend the same simple front door.

## What you get

- **One `Store`, many backends:** local fs, S3, SFTP, Azure Blob, more to come
- **Just the basics:** read, write, list, delete, exists. No magic, no surprises
- **Battle-tested I/O under the hood:** backends wrap `boto3`, `paramiko`, etc.
- **Swappable via config:** switch backends without touching application code
- **Streaming by default:** reads and writes handle large files without blowing up memory
- **Atomic writes** where the backend supports it
- **Zero runtime dependencies:** the core package installs nothing; backend extras pull in only what they need
- **Typed & tested:** strict mypy, spec-driven test suite

## Installation

Install from [PyPI](https://pypi.org/project/remote-store/):

```bash
pip install remote-store
```

Backends that need extra dependencies use extras:

```bash
pip install "remote-store[s3]"           # Amazon S3 / MinIO
pip install "remote-store[s3-pyarrow]"   # S3 with PyArrow (high-throughput)
pip install "remote-store[sftp]"         # SFTP / SSH
pip install "remote-store[azure]"        # Azure Blob / ADLS Gen2
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

|Method               |Description                                   |
|---------------------|----------------------------------------------|
|`delete(path)`       |Delete a file                                 |
|`delete_folder(path)`|Delete a folder                               |
|`move(src, dst)`     |Move or rename                                |
|`copy(src, dst)`     |Copy a file                                   |

**Utility**

|Method               |Description                                   |
|---------------------|----------------------------------------------|
|`child(subpath)`     |Return a child store scoped to a subfolder    |
|`supports(capability)`|Check if the backend supports a capability   |
|`to_key(path)`       |Convert native/absolute path to store-relative key|
|`close()`            |Close the underlying backend                  |

All write/move/copy methods accept `overwrite=True` to replace existing files.

For full details, see the [API reference](https://remote-store.readthedocs.io/en/latest/api/store/).

## Supported Backends

|Backend              |Status    |Extra                       |
|---------------------|----------|----------------------------|
|Local filesystem     |Built-in  |                            |
|Memory (in-process)  |Built-in  |                            |
|Amazon S3 / MinIO    |Built-in  |`remote-store[s3]`          |
|S3 (PyArrow)         |Built-in  |`remote-store[s3-pyarrow]`  |
|SFTP / SSH           |Built-in  |`remote-store[sftp]`        |
|Azure Blob / ADLS    |Built-in  |`remote-store[azure]`       |

Detailed configuration guides for each backend are in [`guides/backends/`](https://remote-store.readthedocs.io/en/latest/backends/).

## Examples

Runnable scripts in [`examples/`](https://github.com/haalfi/remote-store/tree/master/examples):

**Core** -- run locally, no external services needed:

| Script | What it shows |
|--------|---------------|
| [quickstart.py](https://github.com/haalfi/remote-store/blob/master/examples/quickstart.py) | Minimal config, write, read |
| [file_operations.py](https://github.com/haalfi/remote-store/blob/master/examples/file_operations.py) | Full Store API: read, write, delete, move, copy, list, metadata, type checks, capabilities, to_key |
| [streaming_io.py](https://github.com/haalfi/remote-store/blob/master/examples/streaming_io.py) | Streaming writes and reads with `BytesIO` |
| [atomic_writes.py](https://github.com/haalfi/remote-store/blob/master/examples/atomic_writes.py) | Atomic writes and overwrite semantics |
| [configuration.py](https://github.com/haalfi/remote-store/blob/master/examples/configuration.py) | Config-as-code, `from_dict()`, multiple stores, S3/SFTP backend configs |
| [error_handling.py](https://github.com/haalfi/remote-store/blob/master/examples/error_handling.py) | Catching `NotFound`, `AlreadyExists`, etc. |
| [memory_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/memory_backend.py) | In-process memory backend for testing and caching |
| [store_child.py](https://github.com/haalfi/remote-store/blob/master/examples/store_child.py) | Runtime sub-scoping with `Store.child()` |

**Backend** -- require a running service and credentials ([`examples/backends/`](https://github.com/haalfi/remote-store/tree/master/examples/backends)):

| Script | What it shows |
|--------|---------------|
| [s3_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/s3_backend.py) | S3 / MinIO: config, two stores, virtual folders |
| [s3_pyarrow_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/s3_pyarrow_backend.py) | High-throughput S3 via PyArrow C++ + escape hatch |
| [sftp_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/sftp_backend.py) | SSH/SFTP: config, host key policies, `unwrap()` |
| [azure_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/azure_backend.py) | Azure Blob / ADLS Gen2: config, auth methods, `unwrap()` |

Interactive Jupyter notebooks are available in [`examples/notebooks/`](https://github.com/haalfi/remote-store/tree/master/examples/notebooks).

## Contributing

See [CONTRIBUTING.md](https://github.com/haalfi/remote-store/blob/master/CONTRIBUTING.md) for the spec-driven development workflow, code style, and how to add new backends.

## Security

To report a vulnerability, please use [GitHub Security Advisories](https://github.com/haalfi/remote-store/security/advisories/new) instead of opening a public issue. See [SECURITY.md](https://github.com/haalfi/remote-store/blob/master/SECURITY.md) for details.

## License

MIT
