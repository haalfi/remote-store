# Atomic Writes Specification

## Overview

Atomic writes ensure that a file is either fully written or not written at all. This is a capability-driven feature — backends that cannot provide atomicity must fail explicitly rather than silently degrading.

## AW-001: Atomic Write Semantics

**Invariant:** `write_atomic(path, content, overwrite=False)` writes content to a temporary location, then atomically renames it to the target path.
**Postconditions:** From a reader's perspective, the file transitions from non-existent (or old content) to new content in a single operation. No partial content is ever visible.

## AW-002: Capability Gate

**Invariant:** `write_atomic` requires the `ATOMIC_WRITE` capability.
**Raises:** `CapabilityNotSupported` if the backend does not declare `ATOMIC_WRITE`.
**Postconditions:** The check happens *before* any I/O is attempted.

## AW-003: Overwrite Semantics

**Invariant:** If `overwrite=False` and the target file exists, `AlreadyExists` is raised *before* writing the temporary file.
**Postconditions:** If `overwrite=True`, the atomic rename replaces the existing file.

## AW-004: Cleanup on Failure

**Invariant:** If the write fails (e.g. disk full, permission error), the temporary file is cleaned up.
**Postconditions:** No orphaned temporary files are left behind.

## AW-005: Intermediate Directories

**Invariant:** `write_atomic` creates intermediate directories as needed, same as `write`.

## AW-006: Local Backend Implementation

**Invariant:** The local backend implements atomic writes via `tempfile.mkstemp` in the target directory + `os.replace`.
**Postconditions:** `os.replace` is atomic on POSIX systems. On Windows it is atomic if the source and destination are on the same volume.

## AW-007: Atomicity is Never Assumed

**Invariant:** The core never falls back to non-atomic writes if atomic writes are unavailable.
**Postconditions:** If the caller requests `write_atomic` and the backend lacks the capability, the operation fails. The caller must explicitly choose `write` as an alternative.
