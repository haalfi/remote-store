<p align="center">
  <img src="https://raw.githubusercontent.com/haalfi/remote-store/master/assets/logo.png" width="320" alt="remote-store logo">
</p>

<h1 align="center">remote-store</h1>

<p align="center">
  Write file storage code once. Run it against local files, S3, SFTP, or Azure.
</p>

<p align="center">
  <a href="https://pypi.org/project/remote-store/"><img src="https://img.shields.io/pypi/v/remote-store" alt="PyPI version"></a>
  <a href="https://pypi.org/project/remote-store/"><img src="https://img.shields.io/pypi/pyversions/remote-store" alt="Python versions"></a>
  <a href="https://github.com/haalfi/remote-store/actions/workflows/ci.yml"><img src="https://github.com/haalfi/remote-store/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/haalfi/remote-store"><img src="https://codecov.io/gh/haalfi/remote-store/branch/master/graph/badge.svg" alt="Coverage"></a>
  <a href="https://docs.remotestore.dev/"><img src="https://readthedocs.org/projects/remote-store/badge/?version=latest" alt="Documentation Status"></a>
  <a href="https://github.com/haalfi/remote-store/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/remote-store" alt="License"></a>
</p>

> **Beta software.** The core API is stable, but minor versions may still
> contain breaking changes before 1.0. See the [changelog](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
> for what's new, and [open an issue](https://github.com/haalfi/remote-store/issues) if something breaks.

Most Python projects that deal with files eventually grow storage glue:
small wrappers around local paths, S3 clients, SFTP connections, and cloud SDKs.
Those wrappers are usually duplicated across projects, slightly inconsistent,
and painful to replace later.

`remote-store` replaces them with one simple interface.

> **Write file storage code once. Run it against local files, S3, SFTP, or Azure.**

Where files live is configuration, not application code.
Under the hood, established Python libraries (`s3fs`, `paramiko`,
`azure-storage-file-datalake`) still do the work.

### Who this is for

- **Platform and internal tooling teams** -- provide one stable storage interface across environments
- **Data engineering teams** -- pipelines that run against local storage, S3, or SFTP depending on the environment
- **Teams that include citizen developers** -- analysts and domain experts who write Python shouldn't need to learn cloud SDKs just to read and write files
- **Anyone tired of rewriting storage wrappers**

## What you get

- **One interface, many backends:** local fs, S3, SFTP, Azure, in-memory
- **Folder-scoped stores:** each Store is rooted at a folder -- compose layouts with multiple stores or narrow scope with `child()`
- **Swap backends via config:** move between environments without changing code
- **Streaming by default:** large files just work without blowing up memory
- **Atomic writes where supported:** safer updates for file-producing workflows
- **Established libraries underneath:** `s3fs`, `paramiko`, etc. do the real work
- **Zero runtime dependencies:** backend extras pull in only what they need
- **Typed and tested:** strict mypy, spec-driven test suite
- **Optional integrations:** PyArrow filesystem adapter, OpenTelemetry tracing and metrics

### What it is not

- Not a query engine (no SQL, no predicate pushdown)
- Not a table format (no Delta Lake log, no Iceberg manifests)
- Not a filesystem reimplementation (delegates to `s3fs`, `paramiko`, `azure-storage-file-datalake`, `pyarrow` -- the libraries you'd pick anyway)

## Installation

Install from [PyPI](https://pypi.org/project/remote-store/):

```bash
pip install remote-store
```

Backends that need extra dependencies use extras:

```bash
pip install "remote-store[s3]"           # Amazon S3 / MinIO
pip install "remote-store[sftp]"         # SFTP / SSH
pip install "remote-store[azure]"        # Azure Blob / ADLS Gen2
```

Optional extras for tooling and config formats:

```bash
pip install "remote-store[arrow]"        # PyArrow filesystem adapter
pip install "remote-store[s3-pyarrow]"   # S3 with PyArrow (high-throughput)
pip install "remote-store[otel]"         # OpenTelemetry tracing and metrics
pip install "remote-store[toml]"         # TOML config (backport for Python 3.10)
pip install "remote-store[yaml]"         # YAML config (pyyaml)
pip install "remote-store[pydantic]"     # Pydantic config (pydantic-settings)
```

## Quick Start

The simplest way to use `remote-store` ([`examples/quickstart.py`](https://github.com/haalfi/remote-store/blob/master/examples/quickstart.py)):

```python
from remote_store import Store
from remote_store.backends import LocalBackend

store = Store(LocalBackend(root="/tmp/data"))
store.write_text("hello.txt", "Hello, world!")
print(store.read_text("hello.txt"))  # 'Hello, world!'
```

For applications that manage multiple backends or switch between environments,
use a Registry with declarative config:

```python
from remote_store import Registry, RegistryConfig

config = RegistryConfig.from_dict({
    "backends": {"main": {"type": "local", "options": {"root": "/tmp/data"}}},
    "stores": {"data": {"backend": "main", "root_path": ""}},
})

with Registry(config) as registry:
    store = registry.get_store("data")
    store.write_text("hello.txt", "Hello, world!")
    print(store.read_text("hello.txt"))  # 'Hello, world!'
```

Switch to S3 by changing the config. The application code stays the same:

**Dev config:**

```toml
[backends.main]
type = "local"
options = { root = "/tmp/data" }

[stores.data]
backend = "main"
root_path = "reports"
```

**Production -- just swap the backend:**

```toml
[backends.main]
type = "s3"
options = { bucket = "analytics-data" }

[stores.data]
backend = "main"
root_path = "reports"
```

```python
config = RegistryConfig.from_toml("remote-store.toml")
```

## Configuration

Configuration is declarative and immutable. Load from TOML, YAML, Pydantic, a dict, or build with Python objects:

```python
from remote_store import RegistryConfig

# From a TOML file (zero dependencies on Python 3.11+):
config = RegistryConfig.from_toml("remote-store.toml")

# From pyproject.toml:
config = RegistryConfig.from_toml("pyproject.toml", table=("tool", "remote-store"))

# From YAML (requires pyyaml or ruamel.yaml):
from remote_store.ext.yaml import from_yaml
config = from_yaml("remote-store.yaml")

# From Pydantic BaseSettings (requires pydantic-settings):
from remote_store.ext.pydantic import pydantic_to_registry_config
config = pydantic_to_registry_config(my_settings)

# From a dict (e.g. loaded from JSON):
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

### Credential hygiene

Credentials passed through `from_dict()` are automatically wrapped in `Secret`, which masks values in `repr()` and `str()` to prevent accidental leakage in logs or tracebacks. Sensitive keys: `key`, `secret`, `password`, `account_key`, `sas_token`, `connection_string`.

```python
from remote_store import RegistryConfig, Secret

# Auto-wrapped by from_dict():
config = RegistryConfig.from_dict({
    "backends": {"s3": {"type": "s3", "options": {
        "bucket": "my-bucket",
        "key": "AKIA...",
        "secret": "wJalr...",
    }}},
    "stores": {"data": {"backend": "s3", "root_path": "data"}},
})
print(config.backends["s3"].options["secret"])  # → ***

# Or wrap manually:
secret = Secret("my-secret-key")
secret.reveal()  # → 'my-secret-key'
```

## Store API

**Read & write**

|Method                       |Description                 |
|-----------------------------|----------------------------|
|`read(path)`                 |Streaming read (`BinaryIO`) |
|`read_bytes(path)`           |Full content as `bytes`     |
|`read_text(path, encoding=)` |Full content as `str`       |
|`write(path, content)`       |Write bytes or binary stream|
|`write_text(path, text)`     |Write string with encoding  |
|`write_atomic(path, content)`|Write via temp file + rename|
|`open_atomic(path)`          |Streaming write via temp + rename|

**Browse & inspect**

|Method                             |Description                     |
|-----------------------------------|--------------------------------|
|`list_files(path, pattern=…)`      |Iterate `FileInfo`, optional name filter|
|`list_folders(path)`               |Iterate subfolder names         |
|`iter_children(path)`              |Iterate files and folders in one pass|
|`glob(pattern)`                    |Native glob (capability-gated)  |
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
|`native_path(key)`   |Convert store-relative key to backend-native path |
|`unwrap(type_hint)`  |Get backend's native handle (e.g., `pyarrow.fs.FileSystem`)|
|`ping()`             |Verify backend connectivity (health check)    |
|`close()`            |Close the underlying backend                  |

All write/move/copy methods accept `overwrite=True` to replace existing files.

For full details, see the [API reference](https://docs.remotestore.dev/stable/api/store/).

## Supported Backends

|Backend              |Status    |Extra                       |
|---------------------|----------|----------------------------|
|Local filesystem     |Built-in  |                            |
|Memory (in-process)  |Built-in  |                            |
|Amazon S3 / MinIO    |Built-in  |`remote-store[s3]`          |
|S3 (PyArrow)         |Built-in  |`remote-store[s3-pyarrow]`  |
|SFTP / SSH           |Built-in  |`remote-store[sftp]`        |
|Azure Blob / ADLS    |Built-in  |`remote-store[azure]`       |

Detailed configuration guides for each backend are in [`guides/backends/`](https://docs.remotestore.dev/stable/backends/).

### Extensions

All extensions live in `remote_store.ext` and are optional -- import only what you need.

|Extension            |Extra                       |Description                 |
|---------------------|----------------------------|----------------------------|
|PyArrow adapter      |`remote-store[arrow]`       |Use any Store as a `pyarrow.fs.FileSystem` for Parquet, datasets, Pandas, Polars, DuckDB ([guide](https://docs.remotestore.dev/stable/pyarrow-adapter/), [example](https://github.com/haalfi/remote-store/blob/master/examples/pyarrow_adapter.py)) |
|Batch operations     |*(none)*                    |Bulk delete, copy, and exists with error aggregation ([guide](https://docs.remotestore.dev/stable/batch-operations/), [example](https://github.com/haalfi/remote-store/blob/master/examples/batch_operations.py)) |
|Transfer operations  |*(none)*                    |Upload, download, and cross-store transfer with streaming and progress ([guide](https://docs.remotestore.dev/stable/transfer-operations/), [example](https://github.com/haalfi/remote-store/blob/master/examples/transfer_operations.py)) |
|Observability hooks  |*(none)*                    |Callback-based instrumentation for logging, metrics, and tracing ([guide](https://docs.remotestore.dev/stable/observe/), [example](https://github.com/haalfi/remote-store/blob/master/examples/observe_hooks.py)) |
|OpenTelemetry bridge |`remote-store[otel]`        |Pre-built OTel spans and metrics for Store operations ([guide](https://docs.remotestore.dev/stable/observe/), [example](https://github.com/haalfi/remote-store/blob/master/examples/otel_tracing.py)) |
|Glob helpers         |*(none)*                    |Portable glob fallback for backends without native glob support ([guide](https://docs.remotestore.dev/stable/glob-pattern-matching/), [example](https://github.com/haalfi/remote-store/blob/master/examples/glob_pattern_matching.py)) |
|Caching middleware   |*(none)*                    |TTL-based read cache with automatic invalidation on mutations ([guide](https://docs.remotestore.dev/stable/cache/), [API](https://docs.remotestore.dev/stable/api/ext-cache/)) |
|Partition helpers    |*(none)*                    |Hive-style partition path builder and parser ([API](https://docs.remotestore.dev/stable/api/ext-partition/)) |
|YAML config loader   |`remote-store[yaml]`        |Load RegistryConfig from YAML files via PyYAML or ruamel.yaml ([API](https://docs.remotestore.dev/stable/api/ext-yaml/)) |
|Pydantic adapter     |`remote-store[pydantic]`    |Convert Pydantic BaseSettings to RegistryConfig ([API](https://docs.remotestore.dev/stable/api/ext-pydantic/)) |

## Examples

Runnable scripts in [`examples/`](https://github.com/haalfi/remote-store/tree/master/examples):

**Core** -- run locally, no external services needed:

| Script | What it shows |
|--------|---------------|
| [quickstart.py](https://github.com/haalfi/remote-store/blob/master/examples/quickstart.py) | Direct construction and Registry config |
| [file_operations.py](https://github.com/haalfi/remote-store/blob/master/examples/file_operations.py) | Full Store API: read, write, delete, move, copy, list, metadata, type checks, capabilities, to_key |
| [streaming_io.py](https://github.com/haalfi/remote-store/blob/master/examples/streaming_io.py) | Streaming writes and reads with `BytesIO` |
| [atomic_writes.py](https://github.com/haalfi/remote-store/blob/master/examples/atomic_writes.py) | Atomic writes and overwrite semantics |
| [configuration.py](https://github.com/haalfi/remote-store/blob/master/examples/configuration.py) | Config-as-code, `from_dict()`, multiple stores, S3/SFTP backend configs |
| [error_handling.py](https://github.com/haalfi/remote-store/blob/master/examples/error_handling.py) | Catching `NotFound`, `AlreadyExists`, etc. |
| [glob_pattern_matching.py](https://github.com/haalfi/remote-store/blob/master/examples/glob_pattern_matching.py) | Three-tier glob: name filter, native glob, portable fallback |
| [memory_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/memory_backend.py) | In-process memory backend for testing and caching |
| [store_child.py](https://github.com/haalfi/remote-store/blob/master/examples/store_child.py) | Runtime sub-scoping with `Store.child()` |
| [pyarrow_adapter.py](https://github.com/haalfi/remote-store/blob/master/examples/pyarrow_adapter.py) | PyArrow filesystem adapter: Parquet, datasets |
| [batch_operations.py](https://github.com/haalfi/remote-store/blob/master/examples/batch_operations.py) | Bulk delete, copy, exists with error aggregation |
| [transfer_operations.py](https://github.com/haalfi/remote-store/blob/master/examples/transfer_operations.py) | Upload, download, cross-store transfer with progress |
| [observe_hooks.py](https://github.com/haalfi/remote-store/blob/master/examples/observe_hooks.py) | Callback hooks, around spans, buffered observer |
| [otel_tracing.py](https://github.com/haalfi/remote-store/blob/master/examples/otel_tracing.py) | OpenTelemetry tracing and metrics bridge |
| [health_check.py](https://github.com/haalfi/remote-store/blob/master/examples/health_check.py) | Startup gate pattern with `Store.ping()` |
| [retry_policy.py](https://github.com/haalfi/remote-store/blob/master/examples/retry_policy.py) | Retry policy configuration for transient failures |
| [caching.py](https://github.com/haalfi/remote-store/blob/master/examples/caching.py) | TTL-based read caching with automatic invalidation |
| [config_loaders.py](https://github.com/haalfi/remote-store/blob/master/examples/config_loaders.py) | TOML, YAML, and Pydantic config loaders |
| [capabilities_and_errors.py](https://github.com/haalfi/remote-store/blob/master/examples/capabilities_and_errors.py) | Capability checks, error hierarchy, path round-trip |
| [path_model.py](https://github.com/haalfi/remote-store/blob/master/examples/path_model.py) | RemotePath normalization, operators, ROOT sentinel |

**Backend** -- require a running service and credentials ([`examples/backends/`](https://github.com/haalfi/remote-store/tree/master/examples/backends)):

| Script | What it shows |
|--------|---------------|
| [s3_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/s3_backend.py) | S3 / MinIO: config, two stores, virtual folders |
| [s3_pyarrow_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/s3_pyarrow_backend.py) | High-throughput S3 via PyArrow C++ + escape hatch |
| [sftp_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/sftp_backend.py) | SSH/SFTP: config, host key policies, `unwrap()` |
| [azure_backend.py](https://github.com/haalfi/remote-store/blob/master/examples/backends/azure_backend.py) | Azure Blob / ADLS Gen2: config, auth methods, `unwrap()` |

Interactive Jupyter notebooks are available in [`examples/notebooks/`](https://github.com/haalfi/remote-store/tree/master/examples/notebooks).

### Known Limitations

- **Sync only** -- all operations are synchronous. For async frameworks, wrap calls with `asyncio.to_thread()`.
- **Glob** -- `list_files(pattern=)` and `ext.glob.glob_files()` work on all backends. Native `Store.glob()` is supported by Local, S3, S3-PyArrow, and Azure backends.
- **PyArrow adapter** -- Tier 1 native fast-path reads, Tier 2/3 reads, and writes are complete. `native_path()` is implemented for all backends.

## How it compares

There are several excellent Python libraries for file I/O across backends. Here is where `remote-store` sits:

| | fsspec | smart_open | cloudpathlib | obstore | **remote-store** |
|---|---|---|---|---|---|
| API surface | ~56 methods | `open()` only | pathlib-style | ~10 methods | 26 methods |
| Backends | 30+ filesystems | S3, GCS, Az, SFTP | S3, GCS, Azure | S3, GCS, Azure | Local, S3, SFTP, Az, Memory |
| SFTP | via sshfs | Yes | No | No | Built-in |
| Streaming I/O | Yes | Yes | No (downloads) | Bytes-oriented | Yes (BinaryIO) |
| Atomic writes | No | No | No | No | Yes (capability-gated) |
| Async | Yes | No | No | Yes (first-class) | Sync-only (for now) |
| Observability | No | No | No | No | `ext.observe` + OTel |
| Config model | Per-filesystem | URI-based | Per-client | Per-store kwargs | Immutable Registry |
| Runtime deps | Yes | Minimal | SDK-based | Rust binary | Zero (core) |

*Comparison as of March 2026. Method counts and feature sets may change as these libraries evolve.*

**In short:** `remote-store` is for teams that need more than `open()` (smart_open) but less than a full filesystem abstraction (fsspec), with streaming, SFTP, atomic writes, observability, and immutable config. The closest comparison is cloudpathlib, but `remote-store` adds SFTP, streaming, atomic writes, and observability -- and doesn't use the pathlib metaphor for object stores. Under the hood, `remote-store` delegates to the same libraries you'd pick anyway (`s3fs`/`boto3`, `paramiko`, Azure SDK, PyArrow).

## Contributing

See [CONTRIBUTING.md](https://github.com/haalfi/remote-store/blob/master/CONTRIBUTING.md) for the spec-driven development workflow, code style, and how to add new backends.

## Security

To report a vulnerability, please use [GitHub Security Advisories](https://github.com/haalfi/remote-store/security/advisories/new) instead of opening a public issue. See [SECURITY.md](https://github.com/haalfi/remote-store/blob/master/SECURITY.md) for details.

## License

MIT
