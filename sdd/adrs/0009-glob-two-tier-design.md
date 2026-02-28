# ADR-0009: Glob — Two-Tier Design (Core Capability + Extension Fallback)

## Status

Accepted

## Context

Glob/pattern matching for file listing has been an open design question
since v0.6.0 (BK-002, ID-007). The original `Capability.GLOB` was removed
in AF-002 because four backends claimed GLOB support with no `glob()`
method — a ghost capability.

The core tension: some backends have efficient native pattern matching
(Local via pathlib, S3 via prefix filtering) while others have no
server-side glob at all (SFTP, Memory). A single design must serve
both cases without forcing a lowest-common-denominator approach.

### Options considered

**A. Extension only (no core change).**
`ext.glob.glob_files()` always uses `list_files` + client-side
`fnmatch`. Simple, but forgoes native optimization and doesn't let
backends declare glob support.

**B. Core only (abstract method on Backend).**
Add `glob()` as an abstract method. Every backend must implement it,
even if just `list_files` + `fnmatch`. Violates the principle of
capabilities — backends shouldn't claim operations they can't do
natively.

**C. Core only (non-abstract with fallback in Backend).**
`Backend.glob()` has a default implementation using `list_files`.
Every backend appears to support glob. Hides the performance
difference between native and emulated glob.

**D. Core capability + abstract method.**
Add `Capability.GLOB` and make `glob()` abstract. Only backends that
declare GLOB implement it. Others raise. Breaks existing backends
(they'd need to implement a stub).

**E. Core capability + extension fallback (chosen).**
Add `Capability.GLOB` and a non-abstract `Backend.glob()` that raises
by default. Backends with native support (Local) override it and declare
GLOB. `Store.glob()` is capability-gated. `ext.glob.glob_files()` is
the universal entry point: delegates to `Store.glob()` when available,
otherwise does `list_files` + pattern matching.

## Decision

**Option E: Two-tier design.**

### Core tier

1. `Capability.GLOB` added to the enum (value: `"glob"`).
2. `Backend.glob(pattern)` — non-abstract, default raises
   `CapabilityNotSupported`. Backends override this and add GLOB to
   their capabilities.
3. `Store.glob(pattern)` — capability-gated, prepends `root_path` to
   pattern, rebases results to store-relative paths.
4. `LocalBackend` implements native glob via `pathlib.Path.glob()` and
   declares `Capability.GLOB`.

### Extension tier

5. `ext.glob.glob_files(store, pattern)` — the recommended API for
   callers who want pattern matching regardless of backend:
   - If `store.supports(Capability.GLOB)`: delegates to `store.glob()`.
   - Otherwise: extracts the non-wildcard prefix from the pattern,
     calls `store.list_files(prefix, recursive=...)`, filters
     client-side with a regex compiled from the glob pattern.

### Pattern syntax

Unix glob conventions:
- `*` matches any characters except `/`
- `**` matches zero or more path segments (recursive)
- `?` matches a single non-separator character

### Non-Local backends

S3, S3-PyArrow, SFTP, Azure, and Memory do not declare
`Capability.GLOB` in this iteration. They can add native
glob implementations in future releases (S3 and Azure have
prefix-optimized listing that could be leveraged).

## Consequences

- **Additive change.** No existing API is modified — new capability,
  new optional method, new extension. Non-breaking.
- **Progressive optimization.** Backends gain native glob at their own
  pace. The extension ensures every backend works today.
- **Clear capability signal.** `store.supports(Capability.GLOB)` tells
  callers whether native glob is available, enabling informed choices
  about performance.
- **Extension is the safe default.** Documentation should recommend
  `glob_files()` for portable code, `store.glob()` only when the
  caller knows the backend supports it.
- **Future work.** S3 and Azure can implement prefix-optimized `glob()`
  and declare GLOB without changing the extension contract.
