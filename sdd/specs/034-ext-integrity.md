# ext.integrity — Checksum Verification Helpers

## Overview

`remote_store.ext.integrity` provides pure functions for computing and
verifying file checksums over Store's public API. These are convenience
functions that compose `store.read()` with `ext.streams.ChecksumReader`
internally, so users don't need to manage stream lifecycle.

## INT-001: checksum

**Invariant:** `checksum(store, path, algorithm="sha256")` reads the
file at *path* and returns its hex digest as a `ContentDigest`.

**Postconditions:**
- The file is read in chunks (not fully materialized in memory).
- The returned `ContentDigest` has `.algorithm` (lowercase) and `.value`
  (lowercase hex).
- Raises `NotFound` if the file does not exist.

## INT-002: verify

**Invariant:** `verify(store, path, expected, algorithm="sha256")` reads
the file at *path*, computes its checksum, and returns `True` iff the
computed digest matches *expected*.

**Postconditions:**
- *expected* is compared case-insensitively (both normalized to lowercase hex).
- Returns `bool`, does not raise on mismatch.
- Raises `NotFound` if the file does not exist.

## INT-003: verify_digest

**Invariant:** `verify_digest(store, path, expected)` reads the file at
*path* and returns `True` iff the computed digest matches the given
`ContentDigest`.

**Postconditions:**
- Uses `expected.algorithm` to select the hash algorithm.
- Compares `expected.value` against the computed hex digest.
- Returns `bool`, does not raise on mismatch.

## INT-004: Module Exports

**Invariant:** `ext.integrity.__all__` contains:
`checksum`, `verify`, `verify_digest`.

`ContentDigest` is exported from `remote_store._models`, not from
`ext.integrity`.
