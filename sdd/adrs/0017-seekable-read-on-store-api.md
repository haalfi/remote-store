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
method alongside `read()`, superseding ADR-0016's `ext.seekable` approach.

- **A first-class method, not an extension.** Consuming abstractions that control
  the read path (PyArrow's `FileSystem`, Dagster's `IOManager`) will not call an
  extension function, so seekability has to live on the Store/Backend surface to
  reach them at all. *Reverse if* those abstractions gain a way to consume an
  extension helper directly, removing the need for a built-in method.
- **The default spools; backends may override for true random access.** The
  default delegates to `read()` and spools a non-seekable stream into a
  `SpooledTemporaryFile`; a backend like Azure overrides to return a range reader
  that maps each seek+read to a single HTTP Range request. This is the tension
  `ext.seekable` could not resolve: whole-file spooling defeats the byte-saving
  that random access exists for. *Reverse if* one read path can serve both
  sequential and sparse-random access without a per-backend override.
- **`ext.seekable` is removed (never released) and `SEEKABLE_READ` shifts
  meaning.** Its whole-file-spool behaviour is subsumed by the default; the
  capability now signals that `read_seekable()` is zero-overhead (the backend
  natively returns seekable streams), still useful for branching at setup time.
  *Reverse if* the original "`read()` returns seekable" meaning is needed again.

Exact signatures, the spool mechanic, the `_AzureRangeReader` override, Store
delegation, the Arrow call site, and the `ProxyStore` cascade are spec-rate and
live in [spec 036](../specs/036-seekable-read.md) (SEEK-002, SEEK-003, SEEK-005,
SEEK-006, SEEK-008, SEEK-009). A future `HttpBackend` Range implementation is
noted in Consequences.

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
