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
**Postconditions:** If `overwrite=True`, the atomic rename replaces the existing
file. **A failure that did not perform the promote does not destroy it**: it is
either still at its path, or — where a backend simulates the overwrite by
displacing it and cannot undo that — recoverable under a name in the same
directory.

**The antecedent is the whole of the clause, and it is narrower than "on
failure".** A reported failure can mean the promote *was* performed and only its
answer was lost, and there the existing file is replaced and gone: no backup, no
temp, nothing to recover. That is not a defect of this clause — the write
succeeded — but a postcondition reading "on failure the existing file is not
destroyed" would be false there, and `test_a_lost_reply_can_complete_the_operation_it_reports_as_failed`
measures it. AW-004's own standard applies: an unqualified invariant a shipped
test contradicts is a spec defect however narrow the divergence.

**Within that antecedent, the second arm is what a caller cannot reconstruct.** A
backend whose overwrite is not a single server-side operation has to clear the
target before it can put the new file there, and the caller's file is that
backend's to hand back. `SFTPBackend`'s `rename` fallback is the one such window
in the library: it renames the destination to `.~bak.<name>.<uuid8>` and renames
it back if the promote fails, so a promote that failed costs the caller nothing —
except over a dropped connection, where nothing can be renamed back and the
backup itself is the recovery. See [009-sftp-backend.md](009-sftp-backend.md)
SFTP-014 and SFTP-030 for that residue. Backends whose overwrite is one operation
(`os.replace`, a PUT, a DFS rename) have no window and nothing to add here.

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

**A second artifact class on the SFTP fallback path, and it is not litter.**
The `.~bak.<name>.<uuid8>` AW-003 describes is released as soon as the promote
succeeds and renamed back as soon as it fails, so it outlives the call only when
the restore did not complete — over a dropped connection, where it is never
attempted, and on a live one where the server refuses a step of it. Both leave
it holding the caller's previous file. Cleaning it up unasked is the one thing
that would make this clause's guarantee false, so it is left where a caller can
find it.

**A drop is not the only way the restore fails, and stating it as one would be
the same over-claim AW-003 was just scoped against.** The restore is
best-effort: two suppressed calls against a server that may refuse either. What
the guarantee rests on is not that it succeeds — it is that the backup exists
whether or not it does, which is why the backup is taken instead of a delete.
`test_a_restore_the_server_refuses_leaves_the_old_content_findable` measures the
live-connection case.

**"Renamed back" is a claim about a path that may not be free**, which is the
part of it that had to be built rather than assumed: `move`'s copy rung opens the
destination before it can fail, so the restore clears the target first. Without
that step the guarantee holds only on servers whose `rename` replaces silently —
never on the ones that refuse it, which are exactly the servers this fallback
exists for.
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
