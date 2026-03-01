# Extensions

The `remote_store.ext` package provides higher-level operations built
on top of the core Store API.

## Available Extensions

| Module | Extra | Description |
|--------|-------|-------------|
| `ext.batch` | -- | Bulk delete, copy, and exists operations |
| `ext.glob` | -- | Portable glob pattern matching for file listing |
| `ext.transfer` | -- | Upload, download, and cross-store transfer |
| `ext.arrow` | `arrow` | PyArrow FileSystem adapter |

## Using Extensions

### Always-available extensions (pure Python)

`ext.batch`, `ext.glob`, and `ext.transfer` have no extra dependencies.
They are re-exported from the top-level package:

```python
from remote_store import batch_delete, glob_files, upload, download
```

Or import from the extension module directly:

```python
from remote_store.ext.batch import batch_delete
from remote_store.ext.glob import glob_files
from remote_store.ext.transfer import upload
```

### Optional-dependency extensions

`ext.arrow` requires PyArrow.  Install the extra first:

```bash
pip install "remote-store[arrow]"
```

Then import from the top-level package or the extension module directly:

```python
from remote_store import pyarrow_fs
# or
from remote_store.ext.arrow import pyarrow_fs
```

If PyArrow is not installed, the top-level import silently omits the
symbols, and importing `ext.arrow` directly raises a
`ModuleNotFoundError` with installation instructions.

## Extension Guarantees

All extensions follow the same contract (ADR-0008):

- **Public API only** -- extensions use only the public Store / Backend
  API.  They never access private internals.
- **No lifecycle ownership** -- extensions never close the Store.  The
  caller owns the Store's lifecycle.
- **CapabilityNotSupported propagates** -- if a backend lacks a required
  capability, the error reaches the caller immediately.

## Individual Guides

- [PyArrow Adapter](pyarrow-adapter.md)
- [Batch Operations](batch-operations.md)
- [Glob Pattern Matching](glob-pattern-matching.md)
- [Transfer Operations](transfer-operations.md)

## Writing Your Own Extension

See the "Adding an Extension" checklist in CONTRIBUTING.md.
