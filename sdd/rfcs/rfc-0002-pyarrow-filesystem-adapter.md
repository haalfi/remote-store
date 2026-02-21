# RFC-0002: PyArrow FileSystemHandler Adapter

## Status

Draft

## Summary

Implement a `StoreFileSystemHandler` in `ext/arrow.py` that wraps any `Store`
into a `pyarrow.fs.PyFileSystem` via `pyarrow.fs.FileSystemHandler`. This is
the inverse of `unwrap()`: instead of reaching *into* a backend's native handle,
this wraps any Store *into* a PyArrow filesystem.

## Motivation

PyArrow's `FileSystem` interface is the de facto standard for pluggable storage
in the Python data ecosystem. A single adapter unlocks seamless interop with:

- **PyArrow / Pandas:** `pq.write_table(table, path, filesystem=pa_fs)`,
  `pd.read_parquet(path, filesystem=pa_fs)`, `ds.dataset(path, filesystem=pa_fs)`
- **PyIceberg:** Ships `PyArrowFileIO` which wraps any `pyarrow.fs.FileSystem` —
  the chain `Store → StoreFileSystemHandler → PyFileSystem → PyArrowFileIO →
  PyIceberg` works without Iceberg knowing about remote-store.
- **Delta Lake:** delta-rs Python bindings accept a `filesystem` parameter
  (PyArrow filesystem) for read/write operations.
- **DuckDB / Polars:** Both accept PyArrow filesystems for I/O.

One adapter, entire ecosystem.

## Proposal

### API mapping

The Store API maps nearly 1:1 to `FileSystemHandler`:

| Store method | FileSystemHandler method |
|---|---|
| `read()` | `open_input_stream()` |
| `write()` | `open_output_stream()` |
| `list_files()` | `get_file_info_selector()` |
| `delete()` | `delete_file()` |
| `exists()` | `get_file_info()` |
| `file_info()` | `get_file_info()` |

### Design challenge: `open_output_stream`

`open_output_stream` must return a writable `NativeFile` synchronously while
Store's `write()` takes content as input. This requires a buffer adapter —
likely a custom writable that accumulates data and calls `Store.write()` on
`close()`.

### Module location

`ext/arrow.py`, following the existing extension pattern. Optional `pyarrow`
dependency, zero impact on core.

### New spec sections

- Extends `003-backend-adapter-contract.md` (FileSystemHandler surface)
- New spec `013-pyarrow-filesystem-adapter.md` (proposed)

## Data Lake Integration Considerations

### Delta Lake atomic rename

Delta Lake relies on atomic rename for commit. Store already has `move()` and
`write_atomic()`, though S3's lack of true rename (copy+delete) is a known
limitation that Delta handles via its own log protocol.

### Listing performance

Data lakes list heavily during query planning. `get_file_info_selector`
performance matters and should be benchmarked (see ID-012).

### Catalog management

Iceberg REST/Hive/Glue catalogs and Delta transaction logs live above the
storage layer and are out of scope — correctly so. Remote-store's job is to be
the filesystem they write to.

## Alternatives Considered

- **Per-framework adapters** (one for Iceberg, one for Delta, etc.): Rejected
  because PyArrow filesystem is the common abstraction they all use. One adapter
  covers all of them.
- **Relying on `unwrap()`**: Only works for backends that already have a PyArrow
  filesystem (S3-PyArrow). This adapter works for *any* backend, including Local
  and SFTP.

## Impact

- **Public API:** Adds `StoreFileSystemHandler` to the `ext` module.
- **Backwards compatibility:** Non-breaking. New optional feature.
- **Performance:** Listing performance should be benchmarked (see ID-012).
- **Testing:** Needs conformance tests for the FileSystemHandler contract plus
  integration tests with at least PyArrow read/write operations.

## Open Questions

1. Should `open_output_stream` buffer in memory or use a temp file for large
   writes?
2. Should the adapter expose `open_input_file` (random access) in addition to
   `open_input_stream` (sequential)?
3. Version constraints on `pyarrow` — minimum version that supports
   `FileSystemHandler`?

## References

- Related specs: `sdd/specs/003-backend-adapter-contract.md`,
  `sdd/specs/011-s3-pyarrow-backend.md`
- Related ADRs: `sdd/adrs/0003-*.md` (ADR-0003)
- Related backlog: ID-016, ID-012
- PyArrow FileSystemHandler API: https://arrow.apache.org/docs/python/generated/pyarrow.fs.FileSystemHandler.html
