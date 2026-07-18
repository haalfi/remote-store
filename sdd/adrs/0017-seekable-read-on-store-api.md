# ADR-0017: Seekable Read on Store API

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | ADR-0016 |
| Superseded by | —        |
| Amends        | —        |

## Context

ADR-0016 placed seekable read handling in `ext.seekable.seekable_read()`,
following the three-tier pattern (capability + passthrough + extension
fallback). This worked for the initial use case: user code that needs a
seekable stream and doesn't care how it gets one.

However, the Azure PyArrow optimization work (ID-102) revealed a gap.
Azure's `read()` returns a forward-only chunk iterator — efficient for
sequential reads but unusable for PyArrow's `PythonFile.read_at()` which
needs `seek()` + `read()` for Parquet column pruning. The range-reader
approach (`download_blob(offset=, length=)`) is ideal for random access
but catastrophic for sequential reads (~1,280 HTTP requests for a 10 MB
file vs ~1-2 with chunked streaming).

This creates a tension that `ext.seekable` cannot resolve:

- **Sequential callers** need the current chunked `read()` — efficient,
  forward-only, minimal HTTP requests.
- **Analytical callers** (PyArrow, Dagster IO) need a seekable handle
  optimized for sparse random access — each seek + read maps to one
  HTTP Range request.

`ext.seekable.seekable_read()` handles non-seekable backends by spooling
the *entire* file into a `SpooledTemporaryFile`. This gives seekability
but defeats the main benefit of range reads: downloading only the bytes
you need.

The extension approach also cannot serve consuming abstractions like
`pyarrow.fs.FileSystem` or Dagster `IOManager`, which control the read
path and won't call an extension function.

## Decision

Add `read_seekable()` to `Backend` and `Store` as a concrete (non-abstract)
method alongside the existing `read()`.

### `Backend.read_seekable(path) -> BinaryIO`

Default implementation: delegates to `read()`. If the returned stream is
already seekable, returns it directly. Otherwise, spools into a
`SpooledTemporaryFile` (same logic as the removed `ext.seekable`).

Backends MAY override to provide an optimized implementation:

- **AzureBackend**: returns `_AzureRangeReader` — a seekable
  `io.RawIOBase` where each `readinto()` issues a single HTTP Range
  request via `download_blob(offset=, length=)`.
- **HttpBackend**: could implement HTTP Range in the future (not in
  this change).

### `Store.read_seekable(path) -> BinaryIO`

Delegates to `backend.read_seekable()` with path resolution, capability
checks, and logging — same pattern as `Store.read()`.

### Arrow integration

`StoreFileSystemHandler.open_input_file()` calls `store.read_seekable()`
instead of `store.read()` for the Tier 3 path. This gives PyArrow a
seekable, random-access-optimized handle on all backends without
materializing the full file.

### Removal of `ext.seekable`

`ext.seekable.seekable_read()` is removed (never released — introduced
after v0.19.0 in ID-100). Its functionality is subsumed by
`Store.read_seekable()`. The `SEEKABLE_READ` capability shifts meaning:
it now indicates that `read_seekable()` is zero-overhead (no spooling
needed, the backend natively returns seekable streams).

### `ProxyStore` cascade

`ProxyStore.read_seekable()` delegates to `self._inner.read_seekable()`.
`ObservedStore` hooks around it. `CachedStore` inherits the default.

## Consequences

- **Store API grows by one method.** This is the main trade-off. The
  method is justified because "sequential streaming" and "random-access
  seekable" are fundamentally different I/O patterns that backends serve
  differently. Compare `open_input_file` vs `open_input_stream` in
  PyArrow's own `FileSystem` API.
- **Enables backend-specific optimization.** Azure can return a range
  reader; HTTP could follow. No backend is forced to implement anything
  new — the default spooling fallback handles it.
- **Consuming abstractions benefit automatically.** PyArrow and Dagster
  get optimal seekable streams without needing to call extension
  functions or know about backend internals.
- **`SEEKABLE_READ` capability preserved.** Meaning shifts from "read()
  returns seekable" to "read_seekable() is zero-overhead" — still
  useful for callers who want to branch at setup time.
- **One extension removed** (`ext.seekable`). Net surface area change is
  roughly neutral: one Store method added, one extension module removed.
