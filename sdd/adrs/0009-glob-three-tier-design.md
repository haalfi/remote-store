# ADR-0009: Glob — Three-Tier Design

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

An initial two-tier design (core capability + extension fallback) was
considered but rejected in review for three reasons: `store.glob()` throws
on most backends (discoverability pit), simple name filtering requires an
extension, and two entry points create confusion about which to use.

## Decision

Three tiers of pattern matching, with clear escalation:

### Tier 1: `list_files(pattern=…)` — simple name filtering

```python
store.list_files("logs", pattern="*.log")
```

- `pattern` is an `fnmatch` pattern matched against each file's **name**.
- Applied at the `Store` level — works with every backend that has `LIST`.
- No new capability required.
- Covers the most common use case: "give me the CSVs in this folder."

### Tier 2: `store.glob(pattern)` — native backend access

```python
store.glob("**/*.csv")  # only if backend supports GLOB
```

- Capability-gated on `Capability.GLOB`.
- Like `unwrap()`: opt-in direct access to a backend-specific feature.
- Only `LocalBackend` implements it (via `pathlib.Path.glob()`).
- Users who call this **know** their backend and want native semantics.

### Tier 3: `ext.glob.glob_files(store, pattern)` — portable full glob

```python
from remote_store.ext.glob import glob_files
glob_files(store, "data/**/*.csv")
```

- Full recursive glob patterns (`**`, wildcards in directory segments).
- Delegates to `store.glob()` when GLOB is available, otherwise falls
  back to `list_files` + client-side regex matching.
- The recommended API when `list_files(pattern=)` isn't enough and
  you want code that works across all backends.

### Pattern syntax

- `*` — any characters except `/`
- `**` — zero or more path segments (recursive)
- `?` — single non-separator character
- `[abc]` — character class
- `[!abc]` — negated character class

`list_files(pattern=…)` uses stdlib `fnmatch` (complete, well-tested).
`ext.glob` uses a regex converter that supports the full syntax above.

### Non-Local backends

S3, S3-PyArrow, SFTP, Azure, and Memory do not declare
`Capability.GLOB` in this iteration. They can add native
glob implementations in future releases (S3 and Azure have
prefix-optimized listing that could be leveraged).

## Consequences

- **Pit of success.** The easiest API (`list_files(pattern=)`) works
  everywhere. Users only escalate when they need more power.
- **`unwrap` analogy holds.** `store.glob()` is for users who know their
  backend, same as `store.unwrap()`.
- **Extension has a clear role.** `ext.glob.glob_files()` is for when
  `list_files(pattern=)` isn't enough (recursive patterns, directory
  wildcards) but you want portable code.
- **AF-002 reconciled.** `Capability.GLOB` is back, but justified:
  it gates native access, not the only way to filter. `list_files(pattern=)`
  needs only `LIST`.
- **Additive change.** `pattern` parameter on `list_files` is optional
  and backward-compatible. No existing API is modified.
- **Future work.** S3/Azure can implement prefix-optimized `glob()` and
  declare GLOB without changing the contract.
