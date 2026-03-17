# ext.integrity — Checksum Verification Helpers

## Overview

`remote_store.ext.integrity` provides pure functions for computing and
verifying file checksums over Store's public API. These are convenience
functions that compose `store.read()` with `ext.streams.ChecksumReader`
internally, so users don't need to manage stream lifecycle.

## INT-001: checksum

**Invariant:** `checksum(store, path, algorithm="sha256")` reads the
file at *path* and returns a `tuple[str, str]` of `(algorithm, hex_digest)`.

**Postconditions:**
- The file is read in chunks (not fully materialized in memory).
- The algorithm name is lowercase.
- The hex digest is lowercase.
- Raises `NotFound` if the file does not exist.
- Raises `ValueError` if the algorithm is not supported by `hashlib`
  (the `hashlib` error propagates unchanged).

## INT-002: verify

**Invariant:** `verify(store, path, expected, algorithm="sha256")` reads
the file at *path*, computes its checksum, and returns `True` iff the
computed hex digest matches *expected*.

**Postconditions:**
- *expected* is compared case-insensitively (both normalized to lowercase hex).
- Returns `bool`, does not raise on mismatch.
- Raises `NotFound` if the file does not exist.
- Raises `ValueError` if the algorithm is not supported by `hashlib`
  (the `hashlib` error propagates unchanged).

## INT-003: verify_hex

**Invariant:** `verify_hex(store, path, algorithm, expected_hex)` reads
the file at *path*, computes its checksum using *algorithm*, and returns
`True` iff the computed hex digest matches *expected_hex*.

**Postconditions:**
- *expected_hex* is compared case-insensitively (both normalized to lowercase).
- Returns `bool`, does not raise on mismatch.
- Raises `NotFound` if the file does not exist.
- Raises `ValueError` if the algorithm is not supported by `hashlib`.

## INT-004: Module Exports

**Invariant:** `ext.integrity.__all__` contains:
`checksum`, `verify`, `verify_hex`.
