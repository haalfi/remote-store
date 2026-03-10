# Extensions

The `remote_store.ext` package provides higher-level operations built
on top of the core Store API.

## Available Extensions

| Module | Extra | Description | Guide | Example |
|--------|-------|-------------|-------|---------|
| `ext.batch` | -- | Bulk delete, copy, and exists operations | [Guide](batch-operations.md) | [Example](../examples/batch_operations.py) |
| `ext.cache` | -- | Store-level caching with TTL and auto-invalidation | [Guide](cache.md) | [Example](../examples/caching.py) |
| `ext.glob` | -- | Portable glob pattern matching for file listing | [Guide](glob-pattern-matching.md) | [Example](../examples/glob_pattern_matching.py) |
| `ext.observe` | -- | Callback-based observability hooks for Store operations | [Guide](observe.md) | [Example](../examples/observe_hooks.py) |
| `ext.partition` | -- | Hive-style partition path helpers | -- | -- |
| `ext.transfer` | -- | Upload, download, and cross-store transfer | [Guide](transfer-operations.md) | [Example](../examples/transfer_operations.py) |
| `ext.arrow` | `arrow` | PyArrow FileSystem adapter | [Guide](pyarrow-adapter.md) | [Example](../examples/pyarrow_adapter.py) |
| `ext.otel` | `otel` | OpenTelemetry tracing and metrics bridge | [Guide](observe.md) | [Example](../examples/otel_tracing.py) |
| `ext.pydantic` | `pydantic` | Pydantic BaseModel/BaseSettings adapter | -- | [Example](../examples/config_loaders.py) |
| `ext.yaml` | `yaml` | YAML config file loader | -- | [Example](../examples/config_loaders.py) |

## Using Extensions

### Always-available extensions (pure Python)

`ext.batch`, `ext.cache`, `ext.glob`, `ext.observe`, `ext.partition`,
and `ext.transfer` have no extra dependencies. They are re-exported from
the top-level package:

```python
from remote_store import batch_delete, glob_files, observe, upload, download
from remote_store import cached_store           # ext.cache
from remote_store import partition_path, parse_partition  # ext.partition
```

Or import from the extension module directly:

```python
from remote_store.ext.batch import batch_delete
from remote_store.ext.cache import cached_store
from remote_store.ext.glob import glob_files
from remote_store.ext.observe import observe
from remote_store.ext.partition import partition_path, parse_partition
from remote_store.ext.transfer import upload
```

### Optional-dependency extensions

`ext.arrow` requires PyArrow, `ext.otel` requires the OpenTelemetry
API, and `ext.pydantic` requires Pydantic v2.  Install the relevant
extra first:

```bash
pip install "remote-store[arrow]"     # PyArrow filesystem adapter
pip install "remote-store[otel]"      # OpenTelemetry tracing and metrics
pip install "remote-store[pydantic]"  # Pydantic BaseSettings adapter
pip install "remote-store[yaml]"      # YAML config file loader
```

Then import from the top-level package or the extension module directly:

```python
from remote_store import pyarrow_fs                  # ext.arrow
from remote_store import otel_hooks                  # ext.otel
from remote_store import pydantic_to_registry_config # ext.pydantic
from remote_store import from_yaml                   # ext.yaml
# or
from remote_store.ext.arrow import pyarrow_fs
from remote_store.ext.otel import otel_hooks
from remote_store.ext.pydantic import pydantic_to_registry_config
from remote_store.ext.yaml import from_yaml
```

If the required dependency is not installed, the top-level import
silently omits the symbols, and importing the extension module directly
raises a `ModuleNotFoundError` with installation instructions.

## Extension Guarantees

All extensions follow the same contract (ADR-0008):

- **Public API only** -- extensions use only the public Store / Backend
  API.  They never access private internals.
- **No lifecycle ownership** -- extensions never close the Store.  The
  caller owns the Store's lifecycle.
- **CapabilityNotSupported propagates** -- if a backend lacks a required
  capability, the error reaches the caller immediately.

## Writing Your Own Extension

See the "Adding an Extension" checklist in CONTRIBUTING.md.
