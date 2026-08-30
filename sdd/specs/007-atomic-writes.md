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

**Scoped to a failure the backend can still act on.** Cleanup is an operation
against the same store, so it presupposes a usable connection. A backend whose
failure *is* the connection dying may be unable to honour this clause. Whether
it should still attempt the unlink is the backend's own call and turns on
whether the attempt would re-enter the *same* failed connection: an
HTTP-per-request client can often complete a delete that a wedged SSH channel
cannot. Either way the orphan is possible, and a backend in that position says
so in its own spec section.

**Two backends do, and they diverge differently.** `SFTPBackend.write_atomic` /
`open_atomic` **deliberately skip** the cleanup unlink when the failure is itself
a dropped-connection signal, because it would re-enter the same dead channel and
stall again inside the error path — so a stalled atomic write leaves a
`.~tmp.<name>.<uuid8>` behind, asserted by
`test_a_stalled_atomic_write_preserves_the_destination_and_leaves_an_orphan_temp`.
`AzureBackend` **attempts** the delete under a suppressing guard and may simply
fail, which [012-azure-backend.md](012-azure-backend.md) already records as an
inherent limitation of simulated atomicity over a network.
See [009-sftp-backend.md](009-sftp-backend.md) SFTP-014 for the SFTP caveat and
SFTP-030 for what the destination itself holds. Stated here rather than left to
those specs because this clause is the cross-backend one, and an unqualified
invariant that a shipped test contradicts is a spec defect however narrowly the
divergence is scoped.

## AW-005: Intermediate Directories

**Invariant:** `write_atomic` creates intermediate directories as needed, same as `write`.

## AW-006: Local Backend Implementation

**Invariant:** The local backend implements atomic writes via `tempfile.mkstemp` in the target directory + `os.replace`.
**Postconditions:** `os.replace` is atomic on POSIX systems. On Windows it is atomic if the source and destination are on the same volume.

## AW-007: Atomicity is Never Assumed

**Invariant:** The core never falls back to non-atomic writes if atomic writes are unavailable.
**Postconditions:** If the caller requests `write_atomic` and the backend lacks the capability, the operation fails. The caller must explicitly choose `write` as an alternative.
**Note (non-atomic `write` failure semantics):** `write` makes no atomicity guarantee. If the content source raises partway through, a backend MAY leave a partial object at the target — the local backend leaves the partially-written file, and S3-PyArrow may leave a truncated object. Only `write_atomic` guarantees "no partial content is ever visible" (AW-001). Callers that need all-or-nothing must use `write_atomic`. (The s3fs `S3Backend` happens to abort and clean up its `write` too (see S3-010), but that is a backend convenience, not a contract `write` callers may rely on.)
