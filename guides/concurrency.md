# Concurrency and Atomicity Guarantees

remote-store wraps multiple storage backends behind a single API, but each backend inherits the concurrency and atomicity characteristics of its underlying platform. This guide documents two inherent limitations that affect all (or most) backends, and suggests practical workarounds.

## `overwrite=False` and TOCTOU

When you call `store.write(path, data, overwrite=False)`, the backend checks whether the file exists and then writes it. These are two separate operations -- a classic **Time-Of-Check-to-Time-Of-Use (TOCTOU)** race window:

```
Thread A: exists("report.csv") -> False
Thread B: exists("report.csv") -> False    # concurrent check
Thread A: write("report.csv", data_a)      # succeeds
Thread B: write("report.csv", data_b)      # also succeeds -- overwrites A's file
```

This affects **all backends**. The check-then-act pattern cannot be made race-free without an external coordination mechanism. `overwrite=False` is a convenience guard against accidental overwrites in single-writer scenarios -- it is **not** a mutual exclusion mechanism.

### Mitigations

- **External locking.** Use a distributed lock (e.g., DynamoDB lock table for S3, blob lease for Azure, advisory locks for SFTP/local) to serialize writers.
- **Idempotent writes.** Design file names to be unique (e.g., include UUIDs or content hashes) so concurrent writers never target the same path.
- **Backend-native conditional writes.** Some platforms offer conditional put (e.g., S3 `If-None-Match`, Azure `If-None-Match` ETag conditions). These are not exposed through remote-store's API, but you can use `backend.unwrap()` to access the native client.

## Non-atomic `move()`

Several backends implement `move(src, dst)` as a **copy followed by a delete**. If the process crashes between the two steps, both the source and destination will exist (data duplication, not data loss).

| Backend | `move()` implementation | Atomic? |
|---------|------------------------|---------|
| Local | `os.replace()` (same filesystem) | Yes |
| S3 | Copy object + delete object | No |
| S3-PyArrow | Copy object + delete object | No |
| Azure (HNS) | `rename_file()` | Yes |
| Azure (non-HNS) | Copy blob + delete blob | No |
| SFTP (primary) | `posix_rename` | Yes |
| SFTP (fallback) | Read + write + delete | No |

SFTP uses `posix_rename` when the server supports it (most OpenSSH servers do). When `posix_rename` is not available, it falls back to copy+delete.

### Mitigations

- **Verify after move.** After `move()`, check that the source no longer exists. If it does, delete it or alert.
- **Write + delete instead of move.** If atomicity matters, write the data to the destination first, verify, then delete the source. This gives you explicit control over each step.
- **Use `write_atomic()` for the write step.** `write_atomic()` uses temp-file-and-rename on backends that support it, ensuring the destination is written atomically even if `move()` is not.

## Summary table

| Backend | `move()` atomic? | `write_atomic()` truly atomic? | `overwrite=False` race-free? |
|---------|-----------------|-------------------------------|------------------------------|
| Local | Yes | Yes (temp file + `os.replace()`) | No (TOCTOU) |
| S3 | No (copy + delete) | N/A (direct PUT) | No (TOCTOU) |
| S3-PyArrow | No (copy + delete) | N/A (direct PUT) | No (TOCTOU) |
| Azure (HNS) | Yes (`rename_file`) | Yes (temp file + rename) | No (TOCTOU) |
| Azure (non-HNS) | No (copy + delete) | N/A (direct PUT is atomic) | No (TOCTOU) |
| SFTP | Yes* | Yes* (temp file + rename) | No (TOCTOU) |

\* SFTP `move()` is atomic when `posix_rename` is available; falls back to copy+delete otherwise. `write_atomic()` has an orphan-file risk if the connection drops between write and rename (see the [SFTP backend guide](backends/sftp.md)).
