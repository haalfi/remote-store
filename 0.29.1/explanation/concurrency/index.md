# Concurrency and Atomicity Guarantees

remote-store wraps multiple storage backends behind a single API, but each backend inherits the concurrency and atomicity characteristics of its underlying platform. This guide covers three things: whether one backend instance is safe to **share across concurrent callers** (the concurrent-use posture), and two per-operation limitations — non-atomic `move()` and the `overwrite=False` race window.

## Concurrent-use posture

Before the per-operation guarantees below, there is a more basic question: **is one backend instance safe to share across threads** (or, for async backends, across concurrent coroutines on one event loop)? Most backends are; a few wrap a native client that is not, and must be used one-instance-per-thread instead.

| Backend                                                                               | Posture                       | Why — and the remedy where it applies                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Local](https://docs.remotestore.dev/stable/guides/backends/local/index.md)           | Thread-safe                   | Stateless; delegates to the OS filesystem.                                                                                                                                                                                                                                                   |
| [Memory](https://docs.remotestore.dev/stable/guides/backends/memory/index.md)         | Thread-safe                   | Guarded by a single internal lock.                                                                                                                                                                                                                                                           |
| [HTTP](https://docs.remotestore.dev/stable/guides/backends/http/index.md)             | Single-connection on `urllib` | Only the auto-detect *fallback* `urllib` opener (shared redirect counter) is unsafe; the `httpx` / `requests` transports — auto-selected ahead of it when installed — are thread-safe. **Remedy:** install and select `http_client='requests'` or `'httpx'`, or use one instance per thread. |
| [S3](https://docs.remotestore.dev/stable/guides/backends/s3/index.md)                 | Thread-safe                   | The boto3 client / s3fs is safe for concurrent per-instance use.                                                                                                                                                                                                                             |
| [S3-PyArrow](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md) | Thread-safe ¹                 | Arrow's C++ `S3FileSystem` is safe per instance.                                                                                                                                                                                                                                             |
| [SFTP](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md)             | Single-connection             | One paramiko channel over one socket. **Remedy:** one instance per thread (or a native async SFTP client).                                                                                                                                                                                   |
| [Azure](https://docs.remotestore.dev/stable/guides/backends/azure/index.md)           | Thread-safe                   | The Azure SDK service clients are immutable once built. The async twin (`AsyncAzureBackend`) is safe for concurrent coroutines on a **single** event loop, and never across loops — use one instance per loop.                                                                               |
| [Graph](https://docs.remotestore.dev/stable/guides/backends/graph/index.md)           | Thread-safe ²                 | Async-only: safe for concurrent coroutines on one event loop.                                                                                                                                                                                                                                |
| [SQLBlob](https://docs.remotestore.dev/stable/guides/backends/sql-blob/index.md)      | Thread-safe ³                 | The SQLAlchemy engine pools connections.                                                                                                                                                                                                                                                     |
| [SQLQuery](https://docs.remotestore.dev/stable/guides/backends/sql-query/index.md)    | Thread-safe ³                 | Same pooled engine (read-only).                                                                                                                                                                                                                                                              |

No backend offers multi-operation transactionality — atomicity is per operation only, and ordering between concurrent callers is never guaranteed.

¹ S3-PyArrow's per-instance thread-safety is expected but not yet pinned by a live concurrency probe; treat heavy concurrent sharing as to-be-confirmed.

² One Graph instance is safe for concurrent coroutines on a **single** event loop, and never across loops — use one instance per loop. Driven from synchronous code through the async→sync bridge it is also safe for concurrent threads (unlike SFTP); see [Bridge asymmetry](#bridge-asymmetry) below.

³ On a pooled RDBMS engine (PostgreSQL, MySQL) SQLBlob and SQLQuery are thread-safe. The `sqlite:///:memory:` configuration is the exception: SQLAlchemy gives each thread its own isolated in-memory database, so a shared instance behaves as single-connection — use one instance per thread.

### Bridge asymmetry

remote-store has two adapters that cross the sync/async boundary, and they do **not** confer the same safety — the direction decides it:

- **Async backend → sync callers** ([`AsyncBackendSyncAdapter`](https://docs.remotestore.dev/stable/guides/async-sync-bridges/index.md)): owns one private event loop in a background thread and serialises every concurrent sync caller onto it. Wrapping a loop-safe async backend (e.g. Graph) this way *manufactures* a thread-safe sync backend — concurrent threads are safe.
- **Sync backend → async callers** (`SyncBackendAdapter`, used by `AsyncStore` when you pass it a sync backend): dispatches each call to a thread pool via `asyncio.to_thread` and adds no serialisation of its own. It is safe **only if the wrapped sync backend is thread-safe**. Wrapping a single-connection backend (SFTP, or HTTP on `urllib`) and driving it with `asyncio.gather` is **unsafe** — the concurrent workers touch the same non-thread-safe client. Use one instance per worker, or an external lock.

In short: async→sync *manufactures* thread-safety by funnelling through one loop; sync→async *borrows* the backend's thread-safety, or its absence.

## `overwrite=False` and TOCTOU

When you call `store.write(path, data, overwrite=False)`, the backend checks whether the file exists and then writes it. These are two separate operations — a classic **Time-Of-Check-to-Time-Of-Use (TOCTOU)** race window:

```
Thread A: exists("report.csv") -> False
Thread B: exists("report.csv") -> False    # concurrent check
Thread A: write("report.csv", data_a)      # succeeds
Thread B: write("report.csv", data_b)      # also succeeds — overwrites A's file
```

This affects **most backends**. The check-then-act pattern cannot be made race-free without an external coordination mechanism. `overwrite=False` is a convenience guard against accidental overwrites in single-writer scenarios — it is **not** a mutual exclusion mechanism.

The exception is **[Graph](https://docs.remotestore.dev/stable/guides/backends/graph/index.md)**: its `overwrite=False` maps to a server-side atomic *create-if-absent*, so two writers racing to create the same new key cannot both win — the loser receives `AlreadyExists`, with no client-side check-then-write window. S3 and Azure expose the same primitive natively (conditional PUT / `If-None-Match`), but remote-store does not wire it into `overwrite=False`; only Graph maps to it today.

### Mitigations

- **External locking.** Use a distributed lock (e.g., DynamoDB lock table for S3, blob lease for Azure, advisory locks for SFTP/local) to serialize writers.
- **Idempotent writes.** Design file names to be unique (e.g., include UUIDs or content hashes) so concurrent writers never target the same path.
- **Backend-native conditional writes.** Some platforms offer conditional put (e.g., S3 `If-None-Match`, Azure `If-None-Match` ETag conditions). These are not exposed through remote-store's API, but you can use `backend.unwrap()` to access the native client.

## Non-atomic `move()`

Several backends implement `move(src, dst)` as a **copy followed by a delete**. If the process crashes between the two steps, both the source and destination will exist (data duplication, not data loss).

| Backend                                                                                    | `move()` implementation                                                | Atomic?                                        |
| ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- | ---------------------------------------------- |
| [Local](https://docs.remotestore.dev/stable/guides/backends/local/index.md)                | `shutil.move()` (`os.rename()` on same filesystem, copy+delete across) | Yes\*                                          |
| [S3](https://docs.remotestore.dev/stable/guides/backends/s3/index.md)                      | Copy object + delete object                                            | —                                              |
| [S3-PyArrow](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md)      | Copy object + delete object                                            | —                                              |
| [Azure](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) (HNS)          | `rename_file()`                                                        | Yes                                            |
| [Azure](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) (non-HNS)      | Copy blob + delete blob                                                | —                                              |
| [Graph](https://docs.remotestore.dev/stable/guides/backends/graph/index.md)                | Server-side move / copy (monitor-polled)                               | —                                              |
| [SFTP](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md) (`posix_rename`) | `posix_rename`                                                         | Yes                                            |
| [SFTP](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md) (`rename`)       | `rename()`                                                             | Yes (but not guaranteed atomic on all servers) |
| [SFTP](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md) (final fallback) | Read + write + delete                                                  | —                                              |
| [Memory](https://docs.remotestore.dev/stable/guides/backends/memory/index.md)              | Dict key reassignment                                                  | Yes                                            |
| [HTTP](https://docs.remotestore.dev/stable/guides/backends/http/index.md)                  | — (read-only)                                                          | —                                              |
| [SQLBlob](https://docs.remotestore.dev/stable/guides/backends/sql-blob/index.md)           | SQL `UPDATE` in transaction                                            | Yes                                            |
| [SQLQuery](https://docs.remotestore.dev/stable/guides/backends/sql-query/index.md)         | — (read-only)                                                          | —                                              |

SFTP tries three strategies in order: `posix_rename` (atomic), standard `rename()`, and finally copy+delete. Most OpenSSH servers support `posix_rename`. Servers that lack it usually still support `rename()`, which is atomic on most POSIX filesystems.

### Mitigations

- **Verify after move.** After `move()`, check that the source no longer exists. If it does, delete it or alert.
- **Write + delete instead of move.** If atomicity matters, write the data to the destination first, verify, then delete the source. This gives you explicit control over each step.
- **Use `write_atomic()` for the write step.** `write_atomic()` uses temp-file-and-rename on backends that support it, ensuring the destination is written atomically even if `move()` is not.

## Summary table

| Backend                                                                               | `move()` atomic?      | `write_atomic()` truly atomic?   | `overwrite=False` race-free?  |
| ------------------------------------------------------------------------------------- | --------------------- | -------------------------------- | ----------------------------- |
| [Local](https://docs.remotestore.dev/stable/guides/backends/local/index.md)           | Yes\*                 | Yes (temp file + `os.replace()`) | No (TOCTOU)                   |
| [S3](https://docs.remotestore.dev/stable/guides/backends/s3/index.md)                 | No (copy + delete)    | Yes (PUT is inherently atomic)   | No (TOCTOU)                   |
| [S3-PyArrow](https://docs.remotestore.dev/stable/guides/backends/s3-pyarrow/index.md) | No (copy + delete)    | Yes (PUT is inherently atomic)   | No (TOCTOU)                   |
| [Azure](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) (HNS)     | Yes (`rename_file`)   | Yes (temp file + rename)         | No (TOCTOU)                   |
| [Azure](https://docs.remotestore.dev/stable/guides/backends/azure/index.md) (non-HNS) | No (copy + delete)    | Yes (direct PUT is atomic)       | No (TOCTOU)                   |
| [Graph](https://docs.remotestore.dev/stable/guides/backends/graph/index.md)           | No (server move/copy) | Yes (server `PUT`)               | Yes (server create-if-absent) |
| [SFTP](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md)             | Yes\*\*               | Yes\*\* (temp file + rename)     | No (TOCTOU)                   |
| [Memory](https://docs.remotestore.dev/stable/guides/backends/memory/index.md)         | Yes                   | Yes (direct)                     | No (TOCTOU)                   |
| [SQLBlob](https://docs.remotestore.dev/stable/guides/backends/sql-blob/index.md)      | Yes (SQL transaction) | Yes (direct)                     | No (TOCTOU)                   |

\* Local `move()` uses `shutil.move()`, which delegates to `os.rename()` on the same filesystem (atomic) but falls back to copy+delete across filesystems. Only `write_atomic()` uses `os.replace()`.

\*\* SFTP `move()` is atomic when `posix_rename` or `rename()` succeeds; falls back to copy+delete as a last resort. `write_atomic()` has an orphan-file risk if the connection drops between write and rename (see the [SFTP backend guide](https://docs.remotestore.dev/stable/guides/backends/sftp/index.md)).

## See also

- [Capabilities Matrix](https://docs.remotestore.dev/stable/reference/capabilities-matrix/index.md) — atomicity and move semantics per backend
- [Architecture](https://docs.remotestore.dev/stable/explanation/architecture/index.md) — threading model and Store immutability
