# ADR-0009: Glob - Three-Tier Design

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

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

Three tiers of pattern matching, each covering a case the tier below cannot.
A single lowest-common-denominator API and a two-tier design were both
rejected: a bare `store.glob()` throws on most backends (a discoverability
pit), and simple name filtering should not require an extension.

- **Tier 1 (`list_files(pattern=…)`): `fnmatch` name filtering at the Store
  level.** Works on every backend with `LIST`, no new capability; covers the
  common "give me the CSVs in this folder" case. *Reverse if* every backend
  gains cheap recursive matching, collapsing the need for higher tiers.
- **Tier 2 (`store.glob(pattern)`): native backend glob, gated on
  `Capability.GLOB`.** Like `unwrap()`, opt-in direct access to a
  backend-specific feature for users who know their backend and want native
  semantics. The gate exists because native glob support is **unequal** across
  backends; only backends with a genuine native implementation declare `GLOB`
  (the current roster is spec-rate; see spec 018 § GLOB-005/018/019/020).
  *Reverse if* native glob becomes universal, making the gate meaningless.
- **Tier 3 (`ext.glob.glob_files(store, pattern)`): portable full recursive
  glob.** Delegates to `store.glob()` when `GLOB` is available, else falls back
  to `list_files` + client-side matching. This fallback is why the design is
  three tiers, not two: portable recursive glob cannot be guaranteed at the
  Store level. *Reverse if* a portable recursive glob can be guaranteed for
  every backend, letting Tier 3 fold into the Store API.

Pattern grammar, exact signatures, and the `fnmatch`/regex-converter mechanics
are spec-rate and live in spec 018 (Overview, GLOB-001, GLOB-005, GLOB-006,
GLOB-009, GLOB-014).

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
