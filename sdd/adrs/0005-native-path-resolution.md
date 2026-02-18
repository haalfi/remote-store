# ADR-0005: Native Path Resolution Hook on Backend ABC

## Status

Proposed

## Context

`RemotePath` applies a uniform set of normalization rules (backslash conversion,
slash collapsing, dot removal, leading/trailing slash stripping) that work well
for most backends. However, different storage systems have distinct path
conventions:

- **S3** keys are never slash-prefixed and may need character encoding.
- **SFTP** paths must be absolute POSIX paths relative to a chroot or base path.
- **Azure Blob** separates container names from blob paths with different rules
  for each segment.
- **Case-insensitive** filesystems (Windows local, some SFTP servers) may need
  case-folding for consistent cache keys or deduplication.

Today these differences are handled ad-hoc inside each backend's I/O methods
(e.g. `SFTPBackend` joins `base_path` internally, `S3Backend` strips leading
slashes). This scatters path logic across read/write/delete/list methods and
makes it easy to miss edge cases when adding new operations.

The DESIGN.md already states that "normalization [is] delegated to backend"
(section 3.2), but the current implementation centralizes all normalization in
`RemotePath` with no backend participation.

## Decision

Add a `resolve_path(self, path: str) -> str` method to the Backend ABC with an
identity default. The Store calls it after `RemotePath` validation and
root-path joining, before every backend I/O call.

### Key design choices

1. **Concrete method, not abstract** — existing backends inherit the identity
   default and require no changes. Only backends with custom path needs override.

2. **Post-validation, not pre-validation** — `RemotePath` safety checks
   (double-dot rejection, null byte rejection) always run first. `resolve_path`
   cannot relax these.

3. **Pure and total** — the method must be deterministic, side-effect-free, and
   must return a value for every input. This keeps it testable and predictable.

4. **Single call site** — `Store._full_path()` is the sole caller. Backend I/O
   methods no longer need to re-normalize paths internally.

## Consequences

- **Path logic is centralized per-backend** — each backend defines its canonical
  form in one place instead of scattering it across every method.
- **RemotePath is untouched** — all PATH-* spec invariants remain in force.
- **Backward compatible** — identity default means zero behavioral change for
  backends that don't opt in.
- **New backends benefit immediately** — Azure, GCS, and other future backends
  have a clear extension point for their path conventions.
- **Testing is straightforward** — `resolve_path` is a pure function, testable
  in isolation without I/O.
- **Slight overhead** — one extra function call per Store operation. Negligible
  compared to I/O latency.
