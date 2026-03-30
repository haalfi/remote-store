# Audit 006 — Documentation List Completeness

**Date:** 2026-03-30
**Scope:** All `docs-src/` pages, `guides/`, and `README.md` — every list
(including table rows and columns) that enumerates backends, extensions,
capabilities, or Store API methods.
**Branch:** `claude/docs-audit-expert-role-LUJE8`
**Method:** Documentation Expert role (consumer advocate perspective). Read all
doc source files, identified every list of items belonging to the four
categories above, cross-checked each against the authoritative source of truth
in `src/`.

**Source of truth:**

- **Backends (9):** Local, Memory, HTTP, S3, S3-PyArrow, SFTP, Azure, SQLBlob,
  SQLQuery
- **Extensions (14):** batch, cache, glob, integrity, observe, parquet,
  partition, streams, transfer, arrow, dagster, otel, pydantic, yaml
- **Capabilities (10):** READ, WRITE, DELETE, LIST, MOVE, COPY, ATOMIC_WRITE,
  METADATA, GLOB, SEEKABLE_READ
- **Store public methods (29):** read, read_bytes, read_seekable, read_text,
  write, write_text, write_atomic, open_atomic, delete, delete_folder,
  list_files, list_folders, iter_children, glob, move, copy, exists, is_file,
  is_folder, get_file_info, get_folder_info, unwrap, resolve, native_path,
  to_key, supports, ping, close, child

**Completeness rule:** If a list enumerates items of a kind, it must either
(a) include all items, or (b) clearly signal to the reader that it is a
selection. If neither, it is a finding. An item that does not belong to the
category of its list is also a finding.

---

## Summary

| Severity | Count |
|----------|-------|
| High     | 7     |
| Medium   | 11    |
| Low      | 2     |
| **Total**| **20**|

**Dominant pattern:** SQLBlob and SQLQuery backends are systematically absent
from backend lists across the docs (12 findings). These backends have API
reference pages and nav entries, but the surrounding prose, tables, and guides
were not updated when they were added. Secondary pattern: the ghost "Seekable
read" extension lingers in extension lists after being absorbed into the core
API (4 findings).

---

## Findings

### Category A — Missing backends (SQLBlob, SQLQuery omitted)

#### A-1 — `capabilities-matrix.md:10` — Backend x Capability table missing SQL backends

**Severity:** High
**Category:** Completeness

The table columns list 7 backends (Local, Memory, HTTP, S3, S3-PyArrow, SFTP,
Azure). SQLBlobBackend and SQLQueryBackend are missing. The page title
"Capabilities Matrix" implies completeness.

---

#### A-2 — `api/index.md:16-24` — API Reference backends section missing SQL backends

**Severity:** High
**Category:** Completeness

The "Backends" table lists 7 backends. SQLBlobBackend and SQLQueryBackend are
absent. No selection signal.

---

#### A-3 — `api/backends/index.md:8-15` — Backends index table missing SQL backends

**Severity:** High
**Category:** Completeness

The backends index table lists 7 backends but omits SQLBlobBackend and
SQLQueryBackend. Contradicts the nav file (`api/backends/_nav.yml`) which
correctly lists all 9.

---

#### A-4 — `guides/backends/index.md:10-18` — Supported Backends table missing SQL backends

**Severity:** High
**Category:** Completeness

The "Supported Backends" table lists 7, missing SQLBlobBackend and
SQLQueryBackend. The heading "Supported Backends" implies completeness.

---

#### A-5 — `guides/choosing-a-backend.md:7-30` — Decision tree missing SQL backends

**Severity:** Medium
**Category:** Completeness

The decision tree covers 7 backends. No mention that SQL backends exist.

---

#### A-6 — `guides/choosing-a-backend.md:36-44` — Trade-offs table missing SQL backends

**Severity:** Medium
**Category:** Completeness

"Trade-offs at a glance" table lists 7 backends, missing SQLBlobBackend and
SQLQueryBackend.

---

#### A-7 — `api/store.md:239-246` — Backend Behavior Matrix missing backends

**Severity:** Medium
**Category:** Completeness

The table columns list 6 backends (Local, S3, S3-PyArrow, SFTP, Azure, Memory).
Missing HTTP, SQLBlob, and SQLQuery.

---

#### A-8 — `guides/health-check.md:50-57` — Per-backend strategies table missing backends

**Severity:** Medium
**Category:** Completeness

The table lists 6 backends (Local, S3, S3-PyArrow, SFTP, Azure, Memory).
Missing HTTP, SQLBlob, and SQLQuery.

---

#### A-9 — `guides/concurrency.md:29-39` — move() atomicity table missing backends

**Severity:** Medium
**Category:** Completeness

Lists 6 backends with move() atomicity details. Missing Memory, HTTP, SQLBlob,
and SQLQuery.

---

#### A-10 — `guides/concurrency.md:49-57` — Summary table missing backends

**Severity:** Medium
**Category:** Completeness

Lists 6 backends in the summary table. Missing Memory, HTTP, SQLBlob, and
SQLQuery.

---

#### A-11 — `index.md:35` — Homepage mermaid diagram omits built-in backends

**Severity:** Low
**Category:** Completeness

The diagram lists `"Local - S3 - SFTP - Azure - Http - Memory - ...yours"`.
The `...yours` implies unlisted backends are custom, but S3-PyArrow, SQLBlob,
and SQLQuery are built-in.

---

#### A-12 — `data-lake-patterns.md:25` — Backend layer list missing backends

**Severity:** Low
**Category:** Completeness

The layer table lists "Local, Memory, S3, S3-PyArrow, SFTP, Azure". Missing
HTTP, SQLBlob, and SQLQuery. No selection signal.

---

### Category B — Seekable read listed as extension (item doesn't belong)

#### B-1 — `api/extensions/index.md:20` — Seekable read in extensions table

**Severity:** High
**Category:** Doesn't belong

"Seekable read" is listed as an extension in the extensions table.
`ext.seekable` was never released (per `seekable.md:5-6`); it is a core
`Store.read_seekable()` method, not an extension.

---

#### B-2 — `api/index.md:95` — Seekable read under Extensions in API Reference

**Severity:** High
**Category:** Doesn't belong

"Seekable read" listed under the "Extensions" section of the API Reference
index. Same issue as B-1.

---

#### B-3 — `api/extensions/_nav.yml:11` — Seekable read nav entry in extensions

**Severity:** Medium
**Category:** Doesn't belong

Nav entry `- Seekable read: seekable.md` in the extensions navigation.
The target page states "this isn't an extension." The nav entry leads users
to believe it is one.

---

#### B-4 — `README.md:216` — Seekable read row in extensions table

**Severity:** Medium
**Category:** Doesn't belong

The README extensions table includes a "Seekable read" row described as
"built-in". An item labeled "built-in" does not belong in an extensions list.

---

### Category C — Missing extensions from lists

#### C-1 — `architecture.md:79-80` — Unconditional extensions list incomplete

**Severity:** Medium
**Category:** Completeness

Lists 6 unconditional extensions: `ext.batch, ext.glob, ext.observe,
ext.cache, ext.partition, ext.transfer`. Missing **ext.integrity** and
**ext.streams**. No selection signal.

---

#### C-2 — `architecture.md:81-82` — Optional extensions list incomplete

**Severity:** Medium
**Category:** Completeness

Lists 3 optional extensions: `ext.arrow, ext.otel, ext.pydantic`. Missing
**ext.dagster**, **ext.parquet**, and **ext.yaml**. No selection signal.

---

### Category D — Missing Store API method from reference

#### D-1 — `api/store.md` — `read_seekable()` missing from API reference

**Severity:** High
**Category:** Completeness

The Store API reference page has `:::` directives for all 28 other public
methods but omits `Store.read_seekable()`. It should appear in the Reading
section between `read_bytes` and `read_text`.

---

### Category E — Incomplete installation extras

#### E-1 — `README.md:44-50` — Backend extras list missing SQL extras

**Severity:** Medium
**Category:** Completeness

"Backends that need extra dependencies" lists 4 extras (`s3`, `s3-pyarrow`,
`sftp`, `azure`). Missing **sql** and **sql-query**. No selection signal.
