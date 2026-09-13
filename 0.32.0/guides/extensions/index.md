# Extensions

The `remote_store.ext` package provides higher-level operations built on top of the core Store API.

## Available Extensions

| Module                                                                                             | Extra      | Description                                                     | Guide                                                                              | Example                                                                                         |
| -------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| [`ext.batch`](https://docs.remotestore.dev/stable/reference/api/extensions/batch/index.md)         | *(none)*   | Bulk delete, copy, and exists operations                        | [Guide](https://docs.remotestore.dev/stable/guides/batch-operations/index.md)      | [Example](https://docs.remotestore.dev/stable/tutorial/examples/batch-operations/index.md)      |
| [`ext.cache`](https://docs.remotestore.dev/stable/reference/api/extensions/cache/index.md)         | *(none)*   | Store-level caching with TTL and auto-invalidation              | [Guide](https://docs.remotestore.dev/stable/guides/cache/index.md)                 | [Example](https://docs.remotestore.dev/stable/tutorial/examples/caching/index.md)               |
| [`ext.glob`](https://docs.remotestore.dev/stable/reference/api/extensions/glob/index.md)           | *(none)*   | Portable glob pattern matching for file listing                 | [Guide](https://docs.remotestore.dev/stable/guides/glob-pattern-matching/index.md) | [Example](https://docs.remotestore.dev/stable/tutorial/examples/glob-pattern-matching/index.md) |
| [`ext.integrity`](https://docs.remotestore.dev/stable/reference/api/extensions/integrity/index.md) | *(none)*   | Checksum computation and verification helpers                   | —                                                                                  | —                                                                                               |
| [`ext.observe`](https://docs.remotestore.dev/stable/reference/api/extensions/observe/index.md)     | *(none)*   | Callback-based observability hooks for Store operations         | [Guide](https://docs.remotestore.dev/stable/guides/observe/index.md)               | [Example](https://docs.remotestore.dev/stable/tutorial/examples/observe-hooks/index.md)         |
| [`ext.partition`](https://docs.remotestore.dev/stable/reference/api/extensions/partition/index.md) | *(none)*   | Hive-style partition path helpers                               | —                                                                                  | —                                                                                               |
| [`ext.streams`](https://docs.remotestore.dev/stable/reference/api/extensions/streams/index.md)     | *(none)*   | Composable BinaryIO wrappers for progress and checksums         | —                                                                                  | —                                                                                               |
| [`ext.transfer`](https://docs.remotestore.dev/stable/reference/api/extensions/transfer/index.md)   | *(none)*   | Upload, download, and cross-store transfer                      | [Guide](https://docs.remotestore.dev/stable/guides/transfer-operations/index.md)   | [Example](https://docs.remotestore.dev/stable/tutorial/examples/transfer-operations/index.md)   |
| [`ext.write`](https://docs.remotestore.dev/stable/reference/api/extensions/write/index.md)         | *(none)*   | Write helpers with guaranteed client-side content hashing       | [Guide](https://docs.remotestore.dev/stable/guides/write-integrity/index.md)       | —                                                                                               |
| [`aio.ext.write`](https://docs.remotestore.dev/stable/reference/api/aio/extensions/write/index.md) | *(none)*   | Async write helpers with guaranteed client-side content hashing | [Guide](https://docs.remotestore.dev/stable/guides/write-integrity/index.md)       | —                                                                                               |
| [`ext.arrow`](https://docs.remotestore.dev/stable/reference/api/extensions/arrow/index.md)         | `arrow`    | PyArrow FileSystem adapter                                      | [Guide](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md)       | [Example](https://docs.remotestore.dev/stable/tutorial/examples/pyarrow-adapter/index.md)       |
| [`ext.parquet`](https://docs.remotestore.dev/stable/reference/api/extensions/parquet/index.md)     | `arrow`    | Managed Parquet datasets with manifests and completion markers  | [Guide](https://docs.remotestore.dev/stable/guides/parquet-datasets/index.md)      | [Example](https://docs.remotestore.dev/stable/tutorial/examples/parquet-dataset/index.md)       |
| [`ext.otel`](https://docs.remotestore.dev/stable/reference/api/extensions/otel/index.md)           | `otel`     | OpenTelemetry tracing and metrics bridge                        | [Guide](https://docs.remotestore.dev/stable/guides/observe/index.md)               | [Example](https://docs.remotestore.dev/stable/tutorial/examples/otel-tracing/index.md)          |
| [`ext.pydantic`](https://docs.remotestore.dev/stable/reference/api/extensions/pydantic/index.md)   | `pydantic` | Pydantic BaseModel/BaseSettings adapter                         | —                                                                                  | [Example](https://docs.remotestore.dev/stable/tutorial/examples/config-loaders/index.md)        |
| [`ext.yaml`](https://docs.remotestore.dev/stable/reference/api/extensions/yaml/index.md)           | `yaml`     | YAML config file loader                                         | —                                                                                  | [Example](https://docs.remotestore.dev/stable/tutorial/examples/config-loaders/index.md)        |
| [`ext.dagster`](https://docs.remotestore.dev/stable/reference/api/extensions/dagster/index.md)     | `dagster`  | Dagster IO Manager adapter                                      | [Guide](https://docs.remotestore.dev/stable/guides/dagster/index.md)               | [Example](https://docs.remotestore.dev/stable/tutorial/examples/dagster-io-manager/index.md)    |

## Using Extensions

### Always-available extensions (pure Python)

Extensions with no extra dependencies (marked `*(none)*` in the table above) are re-exported from the top-level package for convenience:

```
from remote_store import batch_delete, glob_files, observe, upload, download
from remote_store import cache                   # ext.cache
from remote_store import checksum, verify       # ext.integrity
from remote_store import partition_path, parse_partition  # ext.partition
from remote_store import ProgressReader, ChecksumReader   # ext.streams
from remote_store import write_with_hash, open_atomic_with_hash, HashingAtomicWriter  # ext.write
```

Or import from the extension module directly:

```
from remote_store.ext.batch import batch_delete
from remote_store.ext.cache import cache
from remote_store.ext.glob import glob_files
from remote_store.ext.integrity import checksum, verify
from remote_store.ext.observe import observe
from remote_store.ext.partition import partition_path, parse_partition
from remote_store.ext.streams import ProgressReader, ChecksumReader
from remote_store.ext.transfer import upload
from remote_store.ext.write import write_with_hash, open_atomic_with_hash, HashingAtomicWriter
```

`aio.ext.write` has no extra dependency but is **not** re-exported from `remote_store` — import it from its module directly:

```
from remote_store.aio.ext.write import write_with_hash  # async counterpart to ext.write
```

Seekable reads are built into the core API via `Store.read_seekable()` — no extension import needed.

### Optional-dependency extensions

`ext.arrow` and `ext.parquet` require PyArrow, `ext.otel` requires the OpenTelemetry API, `ext.pydantic` requires Pydantic v2, and `ext.dagster` requires Dagster. Install the relevant extra first:

```
pip install "remote-store[arrow]"     # PyArrow filesystem adapter + parquet datasets
pip install "remote-store[otel]"      # OpenTelemetry tracing and metrics
pip install "remote-store[pydantic]"  # Pydantic BaseSettings adapter
pip install "remote-store[yaml]"      # YAML config file loader
pip install "remote-store[dagster]"   # Dagster IO Manager adapter
```

Then import from the extension module directly:

```
from remote_store.ext.arrow import pyarrow_fs
from remote_store.ext.parquet import ParquetDatasetStore
from remote_store.ext.otel import otel_hooks
from remote_store.ext.pydantic import from_pydantic
from remote_store.ext.yaml import from_yaml
from remote_store.ext.dagster import dagster_io_manager
```

If the required dependency is not installed, importing the extension module raises a `ModuleNotFoundError` with installation instructions.

## Extension Guarantees

All extensions follow the same contract — see the [extension architecture](https://docs.remotestore.dev/stable/explanation/design/adrs/0008-extension-architecture/index.md) and [optional-extension export rules](https://docs.remotestore.dev/stable/explanation/design/adrs/0013-drop-optional-extension-reexports/index.md) ADRs for the rationale:

- **Public API only** — extensions use only the public Store / Backend API. They never access private internals.
- **No lifecycle ownership** — extensions never close the Store. The caller owns the Store's lifecycle.
- **CapabilityNotSupported propagates** — if a backend lacks a required capability, the error reaches the caller immediately.

## Writing Your Own Extension

See the "Adding an Extension" checklist in CONTRIBUTING.md.

## See also

- [API reference](https://docs.remotestore.dev/stable/reference/api/store/index.md) — core Store interface that extensions build on
- [Architecture](https://docs.remotestore.dev/stable/explanation/architecture/index.md) — extension design principles
