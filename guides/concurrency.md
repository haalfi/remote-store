# Concurrency and Atomicity Guarantees

remote-store wraps multiple storage backends behind a single API, but each backend inherits the concurrency and atomicity characteristics of its underlying platform. This guide documents two inherent limitations that affect all (or most) backends, and suggests practical workarounds.

## `overwrite=False` and TOCTOU

When you call `store.write(path, data, overwrite=False)`, the backend checks whether the file exists and then writes it. These are two separate operations — a classic **Time-Of-Check-to-Time-Of-Use (TOCTOU)** race window:

```text
Thread A: exists("report.csv") -> False
Thread B: exists("report.csv") -> False    # concurrent check
Thread A: write("report.csv", data_a)      # succeeds
Thread B: write("report.csv", data_b)      # also succeeds -- overwrites A's file
```

This affects **all backends**. The check-then-act pattern cannot be made race-free without an external coordination mechanism. `overwrite=False` is a convenience guard against accidental overwrites in single-writer scenarios — it is **not** a mutual exclusion mechanism.

### Mitigations

- **External locking.** Use a distributed lock (e.g., DynamoDB lock table for S3, blob lease for Azure, advisory locks for SFTP/local) to serialize writers.
- **Idempotent writes.** Design file names to be unique (e.g., include UUIDs or content hashes) so concurrent writers never target the same path.
- **Backend-native conditional writes.** Some platforms offer conditional put (e.g., S3 `If-None-Match`, Azure `If-None-Match` ETag conditions). These are not exposed through remote-store's API, but you can use `backend.unwrap()` to access the native client.

## Non-atomic `move()`

Several backends implement `move(src, dst)` as a **copy followed by a delete**. If the process crashes between the two steps, both the source and destination will exist (data duplication, not data loss).

| Backend | `move()` implementation | Atomic? |
|---------|------------------------|---------|
| [Local](backends/local.md) | `shutil.move()` (`os.rename()` on same filesystem, copy+delete across) | Yes* |
| [S3](backends/s3.md) | Copy object + delete object | — |
| [S3-PyArrow](backends/s3-pyarrow.md) | Copy object + delete object | — |
| [Azure](backends/azure.md) (HNS) | `rename_file()` | Yes |
| [Azure](backends/azure.md) (non-HNS) | Copy blob + delete blob | — |
| [SFTP](backends/sftp.md) (`posix_rename`) | `posix_rename` | Yes |
| [SFTP](backends/sftp.md) (`rename`) | `rename()` | Yes (but not guaranteed atomic on all servers) |
| [SFTP](backends/sftp.md) (final fallback) | Read + write + delete | — |

SFTP tries three strategies in order: `posix_rename` (atomic), standard `rename()`, and finally copy+delete. Most OpenSSH servers support `posix_rename`. Servers that lack it usually still support `rename()`, which is atomic on most POSIX filesystems.

### Mitigations

- **Verify after move.** After `move()`, check that the source no longer exists. If it does, delete it or alert.
- **Write + delete instead of move.** If atomicity matters, write the data to the destination first, verify, then delete the source. This gives you explicit control over each step.
- **Use `write_atomic()` for the write step.** `write_atomic()` uses temp-file-and-rename on backends that support it, ensuring the destination is written atomically even if `move()` is not.

## Summary table

| Backend | `move()` atomic? | `write_atomic()` truly atomic? | `overwrite=False` race-free? |
|---------|-----------------|-------------------------------|------------------------------|
| [Local](backends/local.md) | Yes* | Yes (temp file + `os.replace()`) | No (TOCTOU) |
| [S3](backends/s3.md) | No (copy + delete) | Yes (PUT is inherently atomic) | No (TOCTOU) |
| [S3-PyArrow](backends/s3-pyarrow.md) | No (copy + delete) | Yes (PUT is inherently atomic) | No (TOCTOU) |
| [Azure](backends/azure.md) (HNS) | Yes (`rename_file`) | Yes (temp file + rename) | No (TOCTOU) |
| [Azure](backends/azure.md) (non-HNS) | No (copy + delete) | Yes (direct PUT is atomic) | No (TOCTOU) |
| [SFTP](backends/sftp.md) | Yes** | Yes** (temp file + rename) | No (TOCTOU) |

\* Local `move()` uses `shutil.move()`, which delegates to `os.rename()` on the same filesystem (atomic) but falls back to copy+delete across filesystems. Only `write_atomic()` uses `os.replace()`.

\*\* SFTP `move()` is atomic when `posix_rename` or `rename()` succeeds; falls back to copy+delete as a last resort. `write_atomic()` has an orphan-file risk if the connection drops between write and rename (see the [SFTP backend guide](backends/sftp.md)).

## See also

- [Capabilities Matrix](capabilities-matrix.md) — atomicity and move semantics per backend
- [Architecture](architecture.md) — threading model and Store immutability
