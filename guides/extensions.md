# Extensions

The `remote_store.ext` package provides higher-level operations built
on top of the core Store API.

## Available Extensions

| Module | Extra | Description |
|--------|-------|-------------|
| `ext.batch` | -- | Bulk delete, copy, and exists operations |
| `ext.transfer` | -- | Upload, download, and cross-store transfer |
| `ext.arrow` | `arrow` | PyArrow FileSystem adapter |

## Using Extensions

### Always-available extensions (pure Python)

`ext.batch` and `ext.transfer` have no extra dependencies.  They are
re-exported from the top-level package:

```python
from remote_store import batch_delete, upload, download
```

Or import from the extension module directly:

```python
from remote_store.ext.batch import batch_delete
from remote_store.ext.transfer import upload
```

### Optional-dependency extensions

`ext.arrow` requires PyArrow.  Install the extra first:

```bash
pip install "remote-store[arrow]"
```

Then import from the extension module:

```python
from remote_store.ext.arrow import pyarrow_fs
```

If PyArrow is not installed, importing `ext.arrow` raises a
`ModuleNotFoundError` with installation instructions.

## Extension Guarantees

All extensions follow the same contract (ADR-0008):

- **Public API only** -- extensions use only the public Store / Backend
  API.  They never access private internals.
- **No lifecycle ownership** -- extensions never close the Store.  The
  caller owns the Store's lifecycle.
- **CapabilityNotSupported propagates** -- if a backend lacks a required
  capability, the error reaches the caller immediately.
- **Streaming** -- transfer and arrow extensions stream data; they never
  load entire files into memory.

## Individual Guides

- [PyArrow Adapter](pyarrow-adapter.md)
- [Batch Operations](batch-operations.md)
- [Transfer Operations](transfer-operations.md)

## Writing Your Own Extension

See the "Adding an Extension" checklist in CONTRIBUTING.md.
