# Extensions

The `remote_store.ext` package provides higher-level operations built
on top of the core Store API.

## Available Extensions

| Module | Extra | Description | Guide | Example |
|--------|-------|-------------|-------|---------|
| [`ext.batch`](api/extensions/batch.md) | *(none)* | Bulk delete, copy, and exists operations | [Guide](batch-operations.md) | [Example](examples/batch-operations.md) |
| [`ext.cache`](api/extensions/cache.md) | *(none)* | Store-level caching with TTL and auto-invalidation | [Guide](cache.md) | [Example](examples/caching.md) |
| [`ext.glob`](api/extensions/glob.md) | *(none)* | Portable glob pattern matching for file listing | [Guide](glob-pattern-matching.md) | [Example](examples/glob-pattern-matching.md) |
| [`ext.integrity`](api/extensions/integrity.md) | *(none)* | Checksum computation and verification helpers | — | — |
| [`ext.observe`](api/extensions/observe.md) | *(none)* | Callback-based observability hooks for Store operations | [Guide](observe.md) | [Example](examples/observe-hooks.md) |
| [`ext.partition`](api/extensions/partition.md) | *(none)* | Hive-style partition path helpers | — | — |
| [`ext.streams`](api/extensions/streams.md) | *(none)* | Composable BinaryIO wrappers for progress and checksums | — | — |
| [`ext.transfer`](api/extensions/transfer.md) | *(none)* | Upload, download, and cross-store transfer | [Guide](transfer-operations.md) | [Example](examples/transfer-operations.md) |
| [`ext.write`](api/extensions/write.md) | *(none)* | Write helpers with guaranteed client-side content hashing | [Guide](write-integrity.md) | — |
| [`ext.arrow`](api/extensions/arrow.md) | `arrow` | PyArrow FileSystem adapter | [Guide](pyarrow-adapter.md) | [Example](examples/pyarrow-adapter.md) |
| [`ext.parquet`](api/extensions/parquet.md) | `arrow` | Managed Parquet datasets with manifests and completion markers | [Guide](parquet-datasets.md) | [Example](examples/parquet-dataset.md) |
| [`ext.otel`](api/extensions/otel.md) | `otel` | OpenTelemetry tracing and metrics bridge | [Guide](observe.md) | [Example](examples/otel-tracing.md) |
| [`ext.pydantic`](api/extensions/pydantic.md) | `pydantic` | Pydantic BaseModel/BaseSettings adapter | — | [Example](examples/config-loaders.md) |
| [`ext.yaml`](api/extensions/yaml.md) | `yaml` | YAML config file loader | — | [Example](examples/config-loaders.md) |
| [`ext.dagster`](api/extensions/dagster.md) | `dagster` | Dagster IO Manager adapter | [Guide](dagster.md) | [Example](examples/dagster-io-manager.md) |

## Using Extensions

### Always-available extensions (pure Python)

Extensions with no extra dependencies (marked `*(none)*` in the table above)
are re-exported from the top-level package for convenience:

```python
from remote_store import batch_delete, glob_files, observe, upload, download
from remote_store import cache                   # ext.cache
from remote_store import checksum, verify       # ext.integrity
from remote_store import partition_path, parse_partition  # ext.partition
from remote_store import ProgressReader, ChecksumReader   # ext.streams
```

Or import from the extension module directly:

```python
from remote_store.ext.batch import batch_delete
from remote_store.ext.cache import cache
from remote_store.ext.glob import glob_files
from remote_store.ext.integrity import checksum, verify
from remote_store.ext.observe import observe
from remote_store.ext.partition import partition_path, parse_partition
from remote_store.ext.streams import ProgressReader, ChecksumReader
from remote_store.ext.transfer import upload
```

Seekable reads are built into the core API via `Store.read_seekable()` —
no extension import needed.

### Optional-dependency extensions

`ext.arrow` and `ext.parquet` require PyArrow, `ext.otel` requires the
OpenTelemetry API, `ext.pydantic` requires Pydantic v2, and `ext.dagster`
requires Dagster.  Install the relevant extra first:

```bash
pip install "remote-store[arrow]"     # PyArrow filesystem adapter + parquet datasets
pip install "remote-store[otel]"      # OpenTelemetry tracing and metrics
pip install "remote-store[pydantic]"  # Pydantic BaseSettings adapter
pip install "remote-store[yaml]"      # YAML config file loader
pip install "remote-store[dagster]"   # Dagster IO Manager adapter
```

Then import from the extension module directly:

```python
from remote_store.ext.arrow import pyarrow_fs
from remote_store.ext.parquet import ParquetDatasetStore
from remote_store.ext.otel import otel_hooks
from remote_store.ext.pydantic import from_pydantic
from remote_store.ext.yaml import from_yaml
from remote_store.ext.dagster import dagster_io_manager
```

If the required dependency is not installed, importing the extension
module raises a `ModuleNotFoundError` with installation instructions.

## Extension Guarantees

All extensions follow the same contract (ADR-0008, ADR-0013):

- **Public API only** — extensions use only the public Store / Backend
  API.  They never access private internals.
- **No lifecycle ownership** — extensions never close the Store.  The
  caller owns the Store's lifecycle.
- **CapabilityNotSupported propagates** — if a backend lacks a required
  capability, the error reaches the caller immediately.

## Writing Your Own Extension

See the "Adding an Extension" checklist in CONTRIBUTING.md.

## See also

- [API reference](api/store.md) — core Store interface that extensions build on
- [Architecture](architecture.md) — extension design principles
