<!-- doc: repo-only -->
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

> **Beta.** The API is settling, but until 1.0, minor releases may include breaking changes. See the [changelog](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md) for what's new, and [open an issue](https://github.com/haalfi/remote-store/issues) if something breaks.

Most Python projects that deal with files eventually grow storage glue:
small wrappers around local paths, S3 clients, SFTP connections, and cloud SDKs.
Those wrappers are usually duplicated across projects, slightly inconsistent,
and painful to replace later.

`remote-store` replaces them with one simple interface.
Where files live is configuration, not application code.
Under the hood, established Python libraries like `s3fs`, `paramiko`,
and `azure-storage-file-datalake` do the real work.

**Requires Python 3.10+.** The core API is synchronous; an async counterpart is available via `remote_store.aio`. See the [concurrency guide](https://docs.remotestore.dev/stable/explanation/concurrency/) for atomicity caveats and race conditions.

<!-- --8<-- [start:getting-started] -->
## Installation

Install from [PyPI](https://pypi.org/project/remote-store/):

```bash
pip install remote-store
```

Backends that need extra dependencies use extras:

```bash
pip install "remote-store[s3]"           # Amazon S3 / MinIO
pip install "remote-store[s3-pyarrow]"   # S3 via PyArrow (analytical workloads)
pip install "remote-store[sftp]"         # SFTP / SSH
pip install "remote-store[azure]"        # Azure Blob / ADLS Gen2
pip install "remote-store[sql]"          # SQL Blob (SQLite, PostgreSQL, ...)
pip install "remote-store[sql-query]"    # SQL Query (read-only, SQLAlchemy + PyArrow)
```

Optional extras for integrations:

```bash
pip install "remote-store[requests]"       # HTTP backend with requests (connection pooling)
pip install "remote-store[httpx]"          # HTTP backend with httpx (HTTP/2)
pip install "remote-store[arrow]"          # PyArrow filesystem adapter
pip install "remote-store[otel]"           # OpenTelemetry instrumentation
pip install "remote-store[yaml]"           # YAML config support
pip install "remote-store[pydantic]"       # Pydantic BaseSettings config
pip install "remote-store[toml]"           # TOML config on Python < 3.11
```

## Quick Start

The simplest way to use `remote-store` ([`examples/getting_started/quickstart.py`](https://github.com/haalfi/remote-store/blob/master/examples/getting_started/quickstart.py)):

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

### Same code, different environment

Switch from local to S3 by changing the config file. The application code stays the same:

**Dev (local filesystem):**

```toml
[backends.main]
type = "local"
options = { root = "/tmp/data" }

[stores.reports]
backend = "main"
root_path = "reports"
```

**Production (S3):**

```toml
[backends.main]
type = "s3"
options = { bucket = "analytics-data" }

[stores.reports]
backend = "main"
root_path = "reports"
```

```python
# Identical in both environments:
config = RegistryConfig.from_toml("remote-store.toml")
with Registry(config) as registry:
    store = registry.get_store("reports")
    store.write_text("monthly/2026-03.csv", report_csv)
```

Configuration supports TOML, YAML, Pydantic BaseSettings, and plain dicts. Credentials are automatically masked in `repr()`/`str()` to prevent leakage in logs.

## Who this is for

- **Platform and internal tooling teams:** provide one stable storage interface across environments
- **Data engineering teams:** pipelines that run against local storage, S3, or SFTP depending on the environment
- **Teams that include citizen developers:** analysts and domain experts who write Python shouldn't need to learn cloud SDKs just to read and write files
- **Anyone tired of writing storage wrappers in every project**

## What you get

- **One interface, many backends:** local filesystem, S3, SFTP, Azure, in-memory, and more
- **Folder-scoped stores:** each Store is rooted at a folder; compose layouts with multiple stores or narrow scope with `child()`
- **Swap backends via config:** move between environments without changing code
- **Streaming by default:** large files just work without blowing up memory
- **Atomic writes where supported:** safer updates for file-producing workflows
- **Async support:** `remote_store.aio` provides `AsyncStore` with coroutine methods; wrap any sync backend with `SyncBackendAdapter`
- **Established libraries underneath:** `s3fs`, `paramiko`, etc. do the real work

Zero runtime dependencies, strict mypy, spec-driven test suite. Optional integrations for PyArrow, OpenTelemetry, and more. See [features](https://github.com/haalfi/remote-store/blob/master/FEATURES.md) for the full list.

## What it is not

- Not a query engine (no SQL, no predicate pushdown)
- Not a table format (no Delta Lake log, no Iceberg manifests)
- Not a filesystem reimplementation (delegates to `s3fs`, `paramiko`, `pyarrow`, etc., the libraries you'd pick anyway)
- Not a file-transfer server (no SFTP/FTP/WebDAV service such as [SFTPGo](https://github.com/drakkan/sftpgo))

## Supported Backends

| Backend | Extra | Library | Atomic write | Native glob | `move()` atomic |
|---------|-------|---------|:------------:|:-----------:|:---------------:|
| Local filesystem | *(built-in)* | stdlib | Yes | Yes | Yes* |
| Memory (in-process) | *(built-in)* | — | Yes | — | Yes |
| HTTP/HTTPS (read-only) | *(built-in)* | stdlib | — | — | — |
| Amazon S3 / MinIO | `remote-store[s3]` | [`s3fs`](https://pypi.org/project/s3fs/) | Yes | Yes | — (copy+delete) |
| S3 (PyArrow) | `remote-store[s3-pyarrow]` | [`pyarrow`](https://pypi.org/project/pyarrow/) + [`s3fs`](https://pypi.org/project/s3fs/) | Yes | Yes | — (copy+delete) |
| SFTP / SSH | `remote-store[sftp]` | [`paramiko`](https://pypi.org/project/paramiko/) | Yes | — | —** |
| Azure Blob / ADLS | `remote-store[azure]` | [`azure-storage-file-datalake`](https://pypi.org/project/azure-storage-file-datalake/) | Yes | Yes | HNS: Yes / non-HNS: — |
| SQL Blob (SQLite, PostgreSQL, ...) | `remote-store[sql]` | [`sqlalchemy`](https://pypi.org/project/SQLAlchemy/) | Yes | Yes | Yes |
| SQL Query (read-only) | `remote-store[sql-query]` | [`sqlalchemy`](https://pypi.org/project/SQLAlchemy/) + [`pyarrow`](https://pypi.org/project/pyarrow/) | — | — | — |

\* Same-filesystem only; cross-filesystem falls back to copy+delete.
\** Attempts `posix_rename` (atomic on POSIX-compliant servers) but falls back to copy+delete; atomicity cannot be guaranteed, so `ATOMIC_MOVE` is not declared.

All backends except HTTP and SQL Query support read, write, delete, list, copy, move, and metadata. HTTP is read-only. SQL Query is read-only: it materializes SQL queries to Parquet/CSV/Arrow IPC on read. Glob is natively supported by most backends; for those that lack it, the portable fallback `ext.glob.glob_files()` works with any `LIST`-capable backend. Seekable reads are available on all backends via `Store.read_seekable()`. See [features](https://github.com/haalfi/remote-store/blob/master/FEATURES.md), the [capabilities matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/), and the [concurrency guide](https://docs.remotestore.dev/stable/explanation/concurrency/) for full details.

## Store API

The Store provides methods across read/write, browsing, management, and utility. Key highlights:

```python
store.read_text("path/to/file.txt")             # → str
store.write_text("path/to/file.txt", content)   # write string
store.read_bytes("path/to/file.csv")            # → bytes
store.write("path/to/data.bin", binary_stream)  # streaming write

store.list_files("reports/", pattern="*.csv")   # iterate FileInfo
store.glob("**/*.parquet")                      # native glob (capability-gated)
store.exists("path/to/file.txt")                # → bool
store.head("path/to/file.txt")                  # WriteResult snapshot (size, etag, …)

store.move("old.txt", "new.txt")                # move / rename
store.copy("src.txt", "dst.txt")                # copy
store.delete("path/to/file.txt")                # delete

store.child("subfolder")                        # scoped child store
store.supports(Capability.ATOMIC_WRITE)         # runtime capability check (gates a method)
store.supports(Capability.ATOMIC_MOVE)          # quality flag — move() atomicity guarantee
store.resolve("path/to/file.txt")               # resolution plan (introspection)
store.ping()                                    # health check
```

For the full method list, see the [API reference](https://docs.remotestore.dev/stable/reference/api/store/). All write, move, and copy methods accept `overwrite=True` to replace existing files.

## Performance

Per-operation overhead is small relative to network round-trip time for most workloads. S3 listing is significantly faster via s3fs connection caching. See the [performance guide](https://docs.remotestore.dev/stable/explanation/performance/) for full comparative benchmarks, methodology, and per-operation breakdowns.

## Extensions

The core library handles storage operations. Extensions add optional capabilities on top: PyArrow integration, observability, caching, or bulk operations. All live in `remote_store.ext`; import only what you need.

| Extension | Extra | What it does |
|-----------|-------|-------------|
| PyArrow adapter | `remote-store[arrow]` | Use any Store as a `pyarrow.fs.FileSystem`; works with Parquet, Pandas, Polars, DuckDB |
| Parquet datasets | `remote-store[arrow]` | Managed Parquet datasets with manifests, `_SUCCESS` markers, and multi-part layouts |
| Batch operations | *(none)* | Bulk delete, copy, and exists with error aggregation |
| Transfer operations | *(none)* | Upload, download, and cross-store transfer with progress |
| Observability hooks | *(none)* | Callback-based instrumentation for logging, metrics, and tracing |
| OpenTelemetry bridge | `remote-store[otel]` | Pre-built OTel spans and metrics for Store operations |
| Caching middleware | *(none)* | TTL-based read cache with automatic invalidation on mutations |
| Stream wrappers | *(none)* | Composable BinaryIO wrappers for progress tracking and checksums |
| Integrity helpers | *(none)* | Checksum computation and verification over Store's public API |
| Write helpers | *(none)* | Client-side content hashing for write operations, compatible with any backend |
| Dagster integration | `remote-store[dagster]` | IOManager adapter, config-driven Store resource, and compute log manager for Dagster pipelines |

Plus glob helpers, partition helpers, YAML and Pydantic config adapters. See the [extensions guide](https://docs.remotestore.dev/stable/guides/extensions/) for details.

## Quality & Testing

Storage behavior must be predictable and correct. We verify this across multiple dimensions:

- **Spec-driven development:** behavior specifications are the source of truth; tests link directly to them. *Prevents feature drift.*
- **Extensive unit tests:** high coverage across all backends, focused on behavior. *Catches integration issues early.*
- **Design by Contract:** pre/post conditions and invariants catch incorrect usage early. *Fails fast on misuse.*
- **Property-based testing:** randomized input generation via [Hypothesis](https://hypothesis.readthedocs.io/) surfaces edge cases no hand-written test would find. *Finds blind spots.*
- **Formal verification:** critical paths are proven correct in [Dafny](https://dafny.org/) before implementation. *Eliminates logic errors.*
- **Mutation testing:** [gremlins](https://pypi.org/project/pytest-gremlins/) modify the code; if they survive the tests, the tests have gaps. *Exposes weak test coverage.*
- **Benchmarks:** performance tracked per operation and backend. *Provides baseline for optimization.*
- **Examples and snippets:** runnable code in [`examples/`](https://github.com/haalfi/remote-store/tree/master/examples) and [notebooks](https://github.com/haalfi/remote-store/tree/master/examples/notebooks); docs are tested against actual behavior. *Keeps examples real.*

## Learn more

To explore `remote-store` beyond the Quick Start:

- **Examples:** self-contained scripts in [`examples/`](https://github.com/haalfi/remote-store/tree/master/examples) covering core operations (file I/O, streaming, atomic writes, error handling, etc.) and backend-specific setups for S3, SFTP, and Azure.
- **Notebooks:** interactive [Jupyter notebooks](https://github.com/haalfi/remote-store/tree/master/examples/notebooks) that walk through common workflows step by step.
- **Guides:** topic-focused walkthroughs in the [documentation](https://docs.remotestore.dev/stable/) covering backends, extensions, configuration, and patterns like data lake layouts or health checks.

## How it compares

There are several excellent Python libraries for file I/O across backends. Here is where `remote-store` sits:

| | [fsspec](https://pypi.org/project/fsspec/) | [smart_open](https://pypi.org/project/smart-open/) | [cloudpathlib](https://pypi.org/project/cloudpathlib/) | [obstore](https://pypi.org/project/obstore/) | **remote-store** |
|---|---|---|---|---|---|
| API surface | many methods | `open()` only | pathlib-style | ~10 methods | full Store API |
| Backends | many filesystems | S3, GCS, Az, SFTP | S3, GCS, Azure | S3, GCS, Azure | Local, S3, SFTP, Az, Memory |
| SFTP | via sshfs | Yes | — | — | Built-in |
| Streaming I/O | Yes | Yes | — (downloads) | Bytes-oriented | Yes (BinaryIO) |
| Atomic writes | — | — | — | — | Yes (capability-gated) |
| Async | Yes | — | — | Yes (first-class) | Yes (`remote_store.aio`) |
| Observability | — | — | — | — | `ext.observe` + OTel |
| Config model | Per-filesystem | URI-based | Per-client | Per-store kwargs | Immutable Registry |
| Runtime deps | Yes | Minimal | SDK-based | Rust binary | Zero (core) |

*Feature sets may change as these libraries evolve. Check each project's documentation for the current state.*

**In short:** `remote-store` is for teams that need more than `open()` (smart_open) but less than a full filesystem abstraction (fsspec), with streaming, SFTP, atomic writes, observability, and immutable config. Under the hood, it delegates to the same libraries you'd pick anyway (`s3fs`/`boto3`, `paramiko`, Azure SDK, PyArrow).
<!-- --8<-- [end:getting-started] -->

## Contributing

See [contributing](https://github.com/haalfi/remote-store/blob/master/CONTRIBUTING.md) for the spec-driven development workflow, code style, and how to add new backends.

## Security

To report a vulnerability, please use [GitHub Security Advisories](https://github.com/haalfi/remote-store/security/advisories/new) instead of opening a public issue. See [security](https://github.com/haalfi/remote-store/blob/master/SECURITY.md) for details.

## License

MIT
