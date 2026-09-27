# ID-140 — SQLBlob lazy reads for SQLite & PostgreSQL
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 4](../BACKLOG.md#no-workarounds) by the ADR-0040 § 4
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

The current blanket claim that `SQLBlobBackend` cannot do lazy reads is too
strong (see spec 040 SQL-BLOB-020, `_sqlalchemy.py:47` excluding
`Capability.LAZY_READ`), so users materialise large blobs they need not.
Both primary dialects have a path to honest `LAZY_READ`; MySQL does not. This
item captures the direction — **no implementation yet**.

**SQLite (Py 3.11+):** `sqlite3.Connection.blobopen(table, col, rowid)`
returns a seekable, chunked `Blob` handle. Reachable through SQLAlchemy via
`sa_conn.connection.driver_connection`. Requires a `SELECT rowid FROM t
WHERE key = :key` lookup first, and only works when the user-supplied table
has an implicit rowid (i.e. not `WITHOUT ROWID`). Genuine streaming.

**PostgreSQL (`bytea`, our current schema):** no native blob handle API.
Pseudo-stream via repeated `SELECT substring(data FROM :off FOR :len) FROM
t WHERE key = :k`. Client memory stays bounded (satisfies LAZY_READ
semantics per spec 006 line 70-73), but each chunk is a round trip, and on
compressed TOAST (`EXTENDED`, the default) the server must decompress per
call. `ALTER COLUMN data SET STORAGE EXTERNAL` makes substring cheap at
the cost of disk space — caller-controlled tradeoff.

**PostgreSQL Large Objects (`lo_*`):** genuine streaming via
`psycopg.connection.lobject()`, but requires an `oid` column and manual
lifecycle (`lo_unlink` on delete/overwrite/move, otherwise we leak).
Different storage model — belongs in a separate backend variant
(e.g. `sql-largeobject`), not a retrofit to `SQLBlobBackend`.

**MySQL:** no streaming story. Same `SUBSTRING()` pseudo-stream is
possible but out of scope here (not a primary target).

**Constraints & gotchas:**
- `requires-python = ">=3.10"` (`pyproject.toml:11`) stays. SQLite
  `blobopen` is 3.11+ → runtime check, fall back to current eager path on
  3.10.
- Capability becomes **per-instance, dialect-conditional** — new pattern
  in this codebase; no other backend varies capabilities at runtime.
  Consider whether `Capability` set should be computed in `__init__` and
  cached, and how `store.supports()` interacts with it.
- Connection lifetime: streaming handle must keep the DBAPI connection
  checked out until the returned `BinaryIO.close()`. Needs a wrapper that
  owns both.
- Custom tables (`create_table=False`): rowid may not exist; substring
  path is schema-agnostic and works as a universal fallback.

**Ripple checks the ripple-check table does not carry.** Process steps are
omitted per [§ Item scope](../BACKLOG.md#how-this-file-works); these three are not process
steps, and each would be missed by a reader following the table alone:
- `FEATURES.md`'s capability matrix is the authoritative capability surface
  per [`CLAUDE.md` § Feature reference](../../CLAUDE.md#feature-reference), and
  this item's whole subject is making a `Capability` declaration
  dialect-conditional — the first such declaration in the repo that is not a
  flat per-backend fact.
- `tests/backends/sqlblob/test_config.py:148` asserts LAZY_READ is **not**
  declared, so it must split into dialect-conditional assertions rather than
  simply flip.
- Verification shape: a large blob (e.g. 50 MiB) read in 4 KiB chunks with
  bounded RSS. Content and chunking assertions alone pass against an eager
  read, which is the same hole ID-244 records for SIO-009.

**Open decisions for whoever picks this up:**
1. SQLite-only first, or SQLite + PG `bytea` substring together?
2. Declare `LAZY_READ` for PG substring path given the per-chunk
   round-trip cost, or reserve LAZY_READ for "true" lazy and add a
   separate `CHUNKED_READ` quality flag?
3. PG Large Objects as a follow-up backend — separate idea, own ID.

Related: ID-136 (non-lazy **write** is by-design; this item is about
**reads** only — writes remain eager).

## Correction, 2026-09-27

Three statements above are corrected here.

- "Capability becomes **per-instance** … new pattern in this codebase" and
  "the first such declaration in the repo that is not a flat per-backend fact"
  are false because of this backend itself: `SQLBlobBackend` computes
  `self._capabilities` per instance in `__init__` (`_sqlalchemy.py:355-362`),
  dropping `USER_METADATA` and `WRITE_RESULT_NATIVE` by which optional columns
  the table has, and its `capabilities` property returns that (`:371-372`);
  `FEATURES.md:272` already publishes `sql-blob`'s `USER_METADATA` as
  requiring a column. A dialect-conditional `LAZY_READ` extends that pattern
  rather than introducing one. "No other backend varies capabilities at
  runtime" still holds: `rg -n -A3 'def capabilities' src` shows every other
  concrete backend returning its class-level `CAPABILITIES`, and the two
  bridge adapters deriving theirs from the backend they wrap. Derived with
  `rg -n '_capabilities' src/remote_store/backends/_sqlalchemy.py` and
  `rg -n -i 'column' FEATURES.md`.
- `tests/backends/sqlblob/test_config.py:148` is now the loop head; the
  `LAZY_READ` branch and its assertion are at `:149-150`
  (`rg -n 'LAZY_READ' tests/backends/sqlblob/test_config.py`).

Still true: `_sqlalchemy.py:47` excludes `LAZY_READ` from `_ALL_CAPABILITIES`,
and `pyproject.toml:11` reads `requires-python = ">=3.10"`. Found by the
ADR-0040 § 4 conversion.
