# BK-242 — Flat-NS file-ancestor pre-check perf (SQLBlob IN-list, memoisation)
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 4](../BACKLOG.md#no-workarounds) by the ADR-0040 § 4
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Two perf optimisations the ID-211 disposition (b) opt-in didn't ship:
- **SQLBlob `WHERE key IN (ancestors)`**: today `_head_one` issues one
  `SELECT 1` per ancestor — N round trips for a depth-N path. The
  research note (`sdd/research/research-id-211-flat-ns-file-ancestor-precheck.md`
  § 5.4) already flagged this; a single `SELECT key FROM table WHERE
  key IN (:ancestors)` collapses the walk to one RTT. On in-memory
  SQLite the win is sub-ms; on PostgreSQL/MySQL over the network at
  depth 6 it is 6 RTTs → 1 RTT (~10-50 ms each).
- **`head_one` memoisation**: bulk-write workloads (`a/b/c/file-{i}.bin`
  for i in 1..N) re-HEAD the same `a`, `a/b`, `a/b/c` ancestors N
  times. A bounded per-instance `TTLCache(maxsize=…, ttl=…)` on the
  closure collapses O(N×D) HEADs to ~O(D) per distinct prefix without
  changing the contract (the TTL accepts staleness within its window).
  Applies to S3, S3PyArrow, Azure non-HNS, and SQLBlob.
Both ship behind the existing `reject_write_under_file_ancestor=True`
opt-in only, so there is no contract risk. Includes refreshing `§ 4` /
`§ 5.4` in the research note with measured before/after numbers. Touches
`src/remote_store/backends/_flat_ns.py`,
`src/remote_store/backends/_sqlalchemy.py`,
`src/remote_store/backends/_s3.py`,
`src/remote_store/backends/_s3_pyarrow.py`,
`src/remote_store/backends/_azure.py`,
`src/remote_store/aio/backends/_azure.py`.

## Correction, 2026-09-27

The backend list above omits `S3Boto3Backend`, and the file list names `_s3.py`
where the shared S3 closure lives. `rg -n 'def _head_one' src` finds the
pre-check's closures at `_s3_base.py:153` (shared by `S3Backend` and
`S3PyArrowBackend`), `_s3_boto3.py:1230`, `_azure.py:314`, `_sqlalchemy.py:423`
and `aio/backends/_azure.py:177`. The sync four feed `_check_no_file_ancestor`;
the async one feeds a separate walk, `_acheck_no_file_ancestor`
(`_flat_ns.py:139`), so a memoisation placed in the sync walk alone misses
async Azure. `rg -n 'TTLCache|lru_cache|memo' src/remote_store/backends/_flat_ns.py`
finds nothing, so neither optimisation has shipped. Found by the ADR-0040 § 4
conversion.
