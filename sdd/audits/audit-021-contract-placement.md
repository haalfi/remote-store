# Audit 021 — Where the backend contract is implemented, read from six releases of bugs

**Date:** 2026-09-28
**Scope:** Every user-impacting defect from v0.28.0 (2026-06-15) through the
`[Unreleased]` stub at `8fa22d6`, plus the open `BUG-`/`BL-` items in
`sdd/BACKLOG.md`, read against `src/remote_store/` at the same commit. The
question is BK-366's, asked one level up: not whether the bug share rose, but
whether the package's design produces the bugs.
**Method:** Every `[x]` entry in `sdd/BACKLOG-DONE.md` lines 242 to 7931 (the
seven sections Unreleased through v0.28.0) and every open header in
`sdd/BACKLOG.md` was read and tabulated: 77 `BUG-` headers plus 30 `BK-`/`ID-`
entries whose body describes a defect a user meets. The table was filtered to
entries with a `user.` audience that changed code behaviour, leaving 71, and
each was assigned to a root-cause cluster by hand; membership is listed under
each finding so the assignment can be disputed. Code figures were measured with
the `rg` and `wc` commands quoted beside them. This is a **report-only** audit;
nothing was modified. The proposals at the end are advisory and are worked out
in [RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md).

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low.

---

## Summary

**The three-layer architecture is sound; the placement of the contract is
not.** 71 defects with a user audience were closed across six releases or sit
open, and 45 of them (63%) are rules the contract or one backend's lifecycle
states once and every class re-implements by hand: 35 a contract clause
re-applied per class (cluster A), 10 the SFTP session lifecycle (cluster B).
The contract is written once in spec 003 and implemented per class, 204
public-method bodies in the 12 sync backend modules alone, and nothing at the
`Store` boundary enforces it. The prior remedies, more conformance cells and
more spec text, were both applied by 2026-04, and cluster A's closed members
by release since then, from the appendix's *Section* column, run Unreleased 1,
v0.31.0 13, v0.30.0 2, v0.29.0 4, v0.28.0 2: not a flat or rising series but
one spike, and 8 of the 13 in v0.31.0 are two review cascades (BUG-243 to
246, 247, 248; BK-354 to 358, 359, 265, 275), which is the detection
confound § H-1 item 3 states. What the series does support is that the class
did not close: every release in the window has members. Eight of the 71
(cluster C) were fixed before their backend's first release; on the 63 that
reached a release the share of A and B is 45 of 63 (71%).

**Items are not clauses.** This repo files one item per class per finder
chain, which is what "the same clause is fixed N times" measures, so an item
count falls under a single implementation by construction. Counted by the
clause each item breached (a by-hand assignment, listed in § H-1), cluster
A's 35 items sit on 11 clauses and cluster B's 10 on 3; the 63% is the item
share, and 14 of 71 is the clause share. Both are given because the remedy
changes the first and not the second.

| Severity | Count | Description |
|----------|-------|-------------|
| High     | 2 | The backend contract is implemented once per class per method, and the SFTP session state machine is hand-rolled across its guards |
| Medium   | 2 | A new backend pays the whole contract again; two services are implemented two or three times over |
| Low      | 1 | Dependency floors, already covered by the floor lane and out of design scope |

**The population, classified.** Filter: audience contains a `user.` value, the
item changed code behaviour (docs-only claims and CI or test-only items
excluded), backend column not `n/a`. Released or not is not part of the
filter; the appendix marks the eight that were not. The register the filter
was applied to is the appendix.

| Cluster | Closed | Open | Total | Share |
|---|---|---|---|---|
| A. Contract clause re-implemented per backend (H-1) | 22 | 13 | 35 | 49% |
| B. Hand-rolled SFTP session lifecycle (H-2) | 10 | 0 | 10 | 14% |
| C. New-backend burn-in: Graph (M-1) | 8 | 0 | 8 | 11% |
| D. Dependency floors and packaging (L-1) | 11 | 3 | 14 | 20% |
| E. Driver-level logic (out of scope) | 2 | 2 | 4 | 6% |

---

## 🔴 High

### H-1. The contract is implemented 13 times, method by method, and enforced 0 times at the boundary — *confirmed (code figures); partial (cluster assignment, by hand)*

**Members, closed (22):** BUG-254, 275, 264, BK-358, BUG-265, BK-359, BUG-259,
247, 246, 249, 248, 243, 242, BK-324, BK-316, BUG-231, BK-301, BUG-222, BK-266,
BK-263, BK-306, BK-298. **Open (13):** BUG-276, 273, 279, 293, 256, 255, 257,
245, 253, 280, 292, 240, 260.

Every one is a clause the contract states once that one class failed to apply
on one or more of its methods. Two shapes sit inside that definition and the
finding's title names only the first: **where the classifier is invoked** (a
method whose wire call was never wrapped, a guard never called, a root or
container answer never decided) and **what the classifier maps** (a row
missing or wrong inside a classifier every boundary passes through). The 35
by clause, each a by-hand assignment:

| Clause | Items | Shape |
|---|---|---|
| Never-leak invariant, BE-021 head: the wire call or stream is unwrapped | BUG-249, 280, 279, 245, BK-358 | invocation |
| Mapping rows, BE-021 table: the classifier's content | BUG-222, 275, 264, 265, 276, 293, 273, BK-316, BK-266, BK-359, BK-263 | content |
| Absent container and the determinant rule, BE-021 § Reach | BUG-243, 246, 248, 242, 255, 257, 256 | invocation |
| Root, BE-029 | BUG-259, 247, 254, 260 | invocation |
| Wrong-type rows on flat namespaces | BK-324 | invocation |
| Close posture, BE-020 | BK-298 | invocation |
| Resource release on close, S3-019 | BK-306 | driver resource |
| Path normalisation before a self-op, AZ-014 | BK-301 | invocation |
| Health probe, PING-011 | BUG-231 | driver resource |
| File-ancestor gate, BE-008 | BUG-253, 292 | invocation |
| `max_depth`, DEPTH-003 against ASYNC-014 | BUG-240 | spec contradiction |

Eleven clauses, 35 items: 21 invocation-shaped, 11 content-shaped, 2 driver
resource, 1 spec contradiction. The invocation shape is what a single boundary
removes; the content shape passes through any boundary unchanged. RFC-0017
§ What each cluster-A bug becomes assigns each of the 35 against its own
design by explicit rules; that assignment, which the RFC owns and revises,
rather than the 63%, is what a disposition of the proposals turns on. Three
properties of the cluster are measured rather than read:

1. **The same clause is fixed N times.** 14 of cluster A's 35 entries name two
   or more backend classes in the appendix's backend column (BUG-254, 259, 246,
   243, 242, BK-324, BUG-276, 256, 255, 240, 292, 293, BK-306, BK-298). BUG-259
   changed eight classes on two halves of one rule that binds eleven (its done
   entry: "Eight concrete classes take code changes in this PR, not six"), and
   spec 003's own table for it records that "a class compliant on the writers
   was not thereby compliant on the destination".
2. **The fix lands per method, so it is missed per method.** BUG-249: three
   listing methods on one class were "the only methods on that class whose wire
   call was not wrapped in its error mapper, against fifteen methods that do
   wrap". BUG-280 is the same shape on `LocalBackend`; BUG-279 is `unwrap`
   outside `_errors()`; BUG-293 is twelve `except` arms across the two Azure
   classes, seven sync and five async; BUG-276 is seven sites in five files.
3. **Cluster A and B defects were latent in released code and found by
   audit.** The appendix's finder column, tallied: 57 of the 71 are marked
   caught before any user report, 56 of them naming the finder (audit-016 for
   Graph, audit-019 for Azure, audit-020 for SFTP, the floor lane, the drift
   guard, and the review rounds of BUG-243, 246, 259 and 265); 11 record no
   finder; 3 name a user-facing trigger, and only two of those are user
   reports (BK-354 and BK-356, issue #970; BUG-254's divergence was published
   in the v0.31.0 migration guide, not reported). BK-366's question therefore
   answers "detection improved", but for clusters A and B what it detected was
   shipped behaviour, and the audits that found it have read three of the
   thirteen classes in depth. Cluster C is the exception: its eight were found
   by audit-016 (2026-06-09) and the readiness review before v0.28.0 shipped
   (2026-06-15), so no user met them.

**Where the contract lives, measured at `8fa22d6`:**

| Figure | Value | Derivation |
|---|---|---|
| Concrete backend classes | 13 (12 shipped; `S3Boto3Backend` is the parked ID-202 PoC, excluded from the wheel) | `rg -n '^\s+CAPABILITIES\b' src/remote_store`: 16 lines, less the 2 ABC declarations with no value and `SyncBackendAdapter`, whose universal set is narrowed per instance from the wrapped backend (spec 003 BE-021 states the same exclusion as "the two abstract bases and the sync adapter"); `pyproject.toml` `[tool.hatch.build.targets.wheel] exclude` for the wheel |
| Public-method bodies across sync backend modules | 204 | command (a) below |
| `except` handlers in `src/` | 395 across 40 files | command (b) below |
| `except` handlers, sync Azure against async Azure | 61 against 56 | command (b), `backends/_azure.py` and `aio/backends/_azure.py` |
| Lines matching the eight shared contract guards | 200 across 11 files | command (c) below |
| of which definitions | 28 (6 in `_flat_ns`, 22 per-class wrappers) | command (e) below |
| of which lines of a per-class wrapper the substring match caught (`_flat_children_or_absent_container`) | 8 (2 definitions, 6 calls) | command (f) below |
| of which call lines of the eight names | 164 across 10 files | (c) minus (e) minus (f); command (g) reproduces it directly |
| Error-mapping definitions outside `ext/` | 25 across 11 modules, enumerated below | command (d) below |
| `except` handlers in `Store` that touch backend I/O | 0 | `_store.py` carries 2: a `KeyError` on the gate table, a `UnicodeEncodeError` on key validation |
| BE-021, the error-mapping clause | 497 lines | spec 003 lines 676 to 1172 inclusive |
| Hand-maintained ABCs | 2: the sync one carries the 21 names command (a) lists; the async one 19 of them (no `read_seekable`, no `open_atomic`, `aclose` for `close`), implemented by 3 of the 13 classes | command (a)'s name list against `rg -n 'def ' aio/_async_backend.py` |
| Conformance test functions | 323 | `rg -c 'def test_' tests/backends/conformance` |

```text
(a) rg -c '^\s+def (exists|is_file|is_folder|read|read_bytes|read_seekable|write|write_atomic|open_atomic|delete|delete_folder|list_files|list_folders|get_file_info|get_folder_info|move|copy|iter_children|glob|check_health|close)\(' src/remote_store/backends
(b) rg -c '^\s*except\b' src/remote_store
(c) rg -c '_reject_root_as_write_target\(|_reject_root_as_file\(|_wrong_type_if_folder\(|_wrong_type_if_file\(|_children_or_absent_container\(|_raise_if_closed\(|_maybe_check_no_file_ancestor\(|_check_no_file_ancestor\(' src/remote_store
(d) rg -n '^\s*(async )?def \w*(classif|_errors|map_exception|map_error|map_stream_error)\w*\(' src/remote_store --glob '!**/ext/**'
(e) rg -n '^\s*(async )?def (_reject_root_as_write_target|_reject_root_as_file|_wrong_type_if_folder|_wrong_type_if_file|_children_or_absent_container|_raise_if_closed|_maybe_check_no_file_ancestor|_check_no_file_ancestor)\(' src/remote_store
(f) rg -n '_flat_children_or_absent_container\(' src/remote_store
(g) rg -P -c '(?<!def )\b(_reject_root_as_write_target|_reject_root_as_file|_wrong_type_if_folder|_wrong_type_if_file|_children_or_absent_container|_raise_if_closed|_maybe_check_no_file_ancestor|_check_no_file_ancestor)\(' src/remote_store
```

Of the 164 call lines, at most 22 are the one delegating call inside a
per-class wrapper (a wrapper such as `S3Boto3Backend._reject_root_as_file`
calls its `_flat_ns` twin), so distinct applications of a guard lie between
142 and 164. The 22 wrappers exist because the shared helper has no home in
the method bodies it guards.

**The 25 error-mapping definitions command (d) matches, by class.** One entry
is not error mapping and is excluded from the 25: `SFTPBackend._classify_existing_target`
classifies a stat result, not an exception. `LocalBackend` and `MemoryBackend`
define none; `LocalBackend` maps inline across its 35 `except` arms, and
`MemoryBackend` raises typed errors directly (0 `except` arms, command (b)).

| Class or module | Classifying function (exception to `RemoteStoreError`) | Context managers routing to it |
|---|---|---|
| `_errors.py` (shared fallback) | `_classify_by_message` | — |
| `SFTPBackend` | `_map_exception` | `_errors` |
| `AzureBackend` | `_classify`, delegating to `classify_azure_error` in `_azure_common` | `_errors`, `_file_op_errors`, `_listing_errors` |
| `AsyncAzureBackend` | `classify_azure_error` (shared) | `_errors`, `_file_op_errors` |
| `GraphBackend` | `classify_graph_error`, `classify_graph_error_code` | — |
| `ReadOnlyHttpBackend` | `_classify_status`, `_map_stream_error` | — |
| `_S3Base` (`S3Backend`, `S3PyArrowBackend`) | `_classify_error`, falling through to `_classify_by_message` | `_s3fs_errors`, `_s3fs_file_errors` |
| `S3PyArrowBackend` (own) | — | `_pyarrow_errors`, `_pyarrow_file_errors` |
| `S3Boto3Backend` | `_classify_error`, falling through to `_classify_by_message` | `_boto_errors`, `_listing_errors`, `_file_op_errors` |
| `SQLBlobBackend`, `SQLQueryBackend` | inline in `_map_errors` | `_map_errors` |

Ten classifying functions across eight homes and fourteen context managers
routing to them: the mapping is per class and, on four classes, layered.

`Store` gates capabilities and scopes paths but applies none of the clauses
above and catches nothing, so "backend-native exceptions never leak" is
asserted 13 times inside backends and zero times at the one boundary every
call crosses. The prose needed to state BE-021 is longer than any backend's
classifier.

The repo has already moved partway toward one shared implementation: `_S3Base`
(RFC-0005's deduplication, BK-011), `_flat_ns.py` (ID-211; 495 lines of guards
applied by injection), `_safe_wrap` (BUG-159), `_ErrorMappingStream` with a
`mapper` callback, and `AsyncBackendSyncAdapter` (ADR-0025). None reaches all
13 classes and none owns the method bodies, so each clause is still *called*
164 times rather than *applied* once. The 164 call lines and the 22 wrappers
are the cost of stopping half way.

**Why this is a design finding and not a test-coverage finding.** The
bug-prevention research (2026-04-03) and the contract-completeness research
(2026-04-05) diagnosed the same cross-product, "methods × parameters × backends
× failure modes". The first prescribed seven deliverables; six exist
(`_safe_wrap` in `_stream.py`; the four `tests/test_pbt_*.py` files; ruff
`BLE` in `pyproject.toml`'s `select`; the extended conformance cells; four
`ResourceWarning` sites in `src/`), and the seventh, an AST check over broad
`except` arms in the backends, deferred "until items 1–5 prove insufficient",
was never built (`scripts/check_error_handling*` does not exist). The second
prescribed tightened spec text, and BE-021 reached 497 lines. Cluster A still
produced 35 defects in six releases. A test fails only on the cell it covers,
and the contract-completeness research's own estimate of the product
(`research-backend-contract-completeness.md` § 3: 18 methods × ~5 parameter
combinations × 7 backends × ~3 state conditions) was ~1,890 cells; the same
formula at today's 13 classes, treating the three async twins as classes
although their surface is 19 names rather than 21, gives ~3,510. The design
keeps the backend axis in the product, and the tests chase it. The
unbuilt static check is the one prescription still open; it reaches the
broad-arm shape (BUG-293, 276, 275, 264, 222, 242, BK-316 in cluster A) and
not the missed-wrap or missed-guard shape (BUG-249, 280, 279, 259, 247, 246,
243, 248, 254, 255, 257, 260, 253, BK-324), which is the larger half.

### H-2. The SFTP session state machine is re-derived at every guard — *confirmed*

**Members (10):** BUG-278, 274, 277, 272, 270, BK-356, 357, 355, 354, BK-313.

SFTP is the one shipped backend whose transport can die under it, and it
hand-rolls connect, the retry budget, liveness, dead-client invalidation and
the temp-and-promote fallback inside a 3,461-line module. BUG-274's own
diagnosis is the shape: "the mid-operation re-entry guards asked only whether
an established connection had dropped", at five guards, so an unreachable host
paid the connect budget two to three times. Two open items in H-1 are this
cluster's residue — BUG-279 (`unwrap` evaluates the lazy client outside the
mapper) and BUG-273 (connect-time context is not visible where the errno is
classified) — and neither is fixable by a mapping arm, because the information
lives in the session, not in the exception.

---

## 🟠 Medium

### M-1. A fourteenth backend pays the whole contract again — *confirmed*

**Members (8):** BK-296, 292, 294, 291, 290, BUG-219, 218, BK-259.

`GraphBackend` shipped in v0.28.0 having re-derived lifecycle, retry, closed
guard, monitor polling and auth offload, and got eight of them wrong before
release, all found by audit-016 (2026-06-09) and the readiness review and fixed
before the 2026-06-15 release; no user met them, which is why the Summary
states the A and B share both with and without this cluster. Under H-1's
design that is the expected price of a new backend: 21 methods, each owing
every clause. BK-345 (open) names the same gap from the test side: "a new backend
that can delete passes CI without meeting" the absent-container rule.

### M-2. Two services are implemented two and three times over — *confirmed*

Two S3 lanes ship (`S3Backend` over s3fs, `S3PyArrowBackend`) with a third
parked (`S3Boto3Backend`, ID-202), and Azure ships as a hand-written sync and
async pair (2,106 and 1,716 lines; 61 and 56 `except` arms). Eight of the 71
entries touched two or more S3 lanes (BUG-254, 242, 276, 255, BK-306, BK-298,
BUG-259, BK-324); the open register still reads "all three S3 backends"
(BUG-276) and "the two s3fs lanes" (BUG-255). BUG-293 counts its arms "seven
sync and five async", one defect fixed in each twin. Each copy is another
chance to miss a clause, and under H-1 every copy misses independently.

---

## 🟡 Low

### L-1. Dependency floors — *confirmed, out of design scope*

**Members, closed (11):** BUG-281, BK-370, BUG-286, 285, 284, 283, 258, 232,
BK-311, BUG-225, ID-198. **Open (3):** BUG-289, 287, 288.

An extra declares a range whose bottom installs and cannot run. This is
packaging, and the floor lane (BK-369) and recipe gate (BK-368) address it
directly. Its one design coupling is M-2: three S3 extras and two Azure classes
are three and two floors to get wrong.

---

## Out of Scope

### Cluster E — driver-level logic, 4 entries

BUG-220 (Windows 8.3 short-name race in `LocalBackend`), BUG-223 (Azure HNS
probe cached on a transient failure), BL-011 (`LIKE` prefix escaping in
`SQLBlobBackend`), BUG-251 (`ext.cache` keys omit the store). Each is a bug in
a backend's own primitive and would exist under any placement of the contract.
This is the cluster a corrected design leaves behind.

### Docs-claim and infrastructure entries

Excluded from the 71 by the filter. They are real, are tracked, and say nothing
about the package design.

---

## Appendix: the register

The 71 entries the filter kept, in `BACKLOG-DONE.md` order then `BACKLOG.md`
order. *Backends* is the register's backend column as read from each entry's
body; *finder* is what the entry names as having found the defect ("?" when it
names nothing, "yes" when it names a user-facing trigger); *released* is "no"
for the eight cluster-C entries closed before v0.28.0 shipped. Tallies in
§ H-1 item 3 are counted over the *finder* column of this table.

| ID | Cluster | Section | Backends | Finder | Released |
|---|---|---|---|---|---|
| BUG-281 | D | Unreleased | sql-blob, sql-query | caught (drift guard) | yes |
| BUG-254 | A | Unreleased | s3, s3-pyarrow, s3-boto3, azure | yes (divergence documented in v0.31.0 migration guide) | yes |
| BK-370 | D | Unreleased | all (conda) | ? (published feedstock diverged) | yes |
| BUG-286 | D | v0.32.0 | azure | caught (maintainer sweep after conda review) | yes |
| BUG-285 | D | v0.32.0 | sql-blob, sql-query, http, ext(dagster) | caught (hand sweep) | yes |
| BUG-284 | D | v0.32.0 | sftp | caught (conda recipe read) | yes |
| BUG-283 | D | v0.32.0 | sftp | caught (conda-forge reviewer) | yes |
| BUG-278 | B | v0.31.0 | sftp | caught (BUG-274 review) | yes |
| BUG-275 | A | v0.31.0 | sftp | caught (BUG-265 closing pass) | yes |
| BUG-274 | B | v0.31.0 | sftp | caught (BUG-265 round-5 reviewer) | yes |
| BUG-277 | B | v0.31.0 | sftp | caught (BUG-272 review) | yes |
| BUG-272 | B | v0.31.0 | sftp | caught (BK-360 review) | yes |
| BUG-270 | B | v0.31.0 | sftp | caught (BK-360 review) | yes |
| BUG-264 | A | v0.31.0 | azure | caught (BK-359 review) | yes |
| BK-358 | A | v0.31.0 | sftp | caught (BK-355 review) | yes |
| BUG-265 | A | v0.31.0 | sftp | caught (BK-359 observation) | yes |
| BK-359 | A | v0.31.0 | sftp | caught (BK-356 review) | yes |
| BK-356 | B | v0.31.0 | sftp | yes (issue #970 reporter objection) | yes |
| BK-357 | B | v0.31.0 | sftp | caught (BK-355 review) | yes |
| BUG-259 | A | v0.31.0 | sftp, s3, s3-boto3, s3-pyarrow, azure, async-azure, graph, local | ? | yes |
| BK-355 | B | v0.31.0 | sftp | caught (BK-354 review) | yes |
| BK-354 | B | v0.31.0 | sftp | yes (issue #970) | yes |
| BUG-247 | A | v0.31.0 | local | caught (BUG-243) | yes |
| BUG-246 | A | v0.31.0 | s3-boto3, azure, sql-blob | caught (BUG-243) | yes |
| BUG-249 | A | v0.31.0 | s3-boto3 | ? | yes |
| BUG-258 | D | v0.31.0 | ext(dagster) | caught (CI typecheck) | yes |
| BUG-248 | A | v0.31.0 | graph | caught (BUG-243) | yes |
| BUG-243 | A | v0.31.0 | s3, azure, sql-blob | ? | yes |
| BUG-242 | A | v0.31.0 | s3, s3-pyarrow | caught (PR #945 review round 5) | yes |
| BK-324 | A | v0.31.0 | all | caught (research audit, review) | yes |
| BK-316 | A | v0.30.0 | sftp | caught (audit-020) | yes |
| BK-313 | B | v0.30.0 | sftp | caught (audit-020) | yes |
| BUG-232 | D | v0.30.0 | s3-pyarrow, ext(arrow), sql-query | caught (PR review) | yes |
| BUG-231 | A | v0.30.0 | graph | caught (BK-310 docs work) | yes |
| BK-311 | D | v0.30.0 | all (conda, context7) | caught | yes |
| BUG-225 | D | v0.29.1 | graph, http(httpx) | caught (drift guard) | yes |
| ID-198 | D | v0.29.0 | ext(dagster, otel), azure | caught (live validation) | yes |
| BK-306 | A | v0.29.0 | s3, s3-pyarrow, s3-boto3 | caught (BK-298) | yes |
| BK-298 | A | v0.29.0 | azure, s3, s3-pyarrow, s3-boto3 | caught (audit-019) | yes |
| BK-301 | A | v0.29.0 | azure | caught (audit-019) | yes |
| BUG-223 | E | v0.29.0 | azure | caught (audit-019) | yes |
| BUG-222 | A | v0.29.0 | azure | caught (audit-019) | yes |
| BK-296 | C | v0.28.0 | graph | caught (release-readiness rerun) | no |
| BK-292 | C | v0.28.0 | graph | caught (review, live-confirmed) | no |
| BK-294 | C | v0.28.0 | graph | caught (live-reproduced) | no |
| BK-291 | C | v0.28.0 | graph | ? | no |
| BK-290 | C | v0.28.0 | graph | caught (review) | no |
| BUG-220 | E | v0.28.0 | local | caught (BK-289 lane) | yes |
| BUG-219 | C | v0.28.0 | graph | caught (review, live-reproduced) | no |
| BUG-218 | C | v0.28.0 | graph | caught (ID-127 readiness review) | no |
| BK-259 | C | v0.28.0 | graph | caught (audit-016) | no |
| BK-266 | A | v0.28.0 | graph | caught (audit-016) | yes |
| BK-263 | A | v0.28.0 | graph | caught (audit-016) | yes |
| BL-011 | E | open, Release Blockers | sql-blob | ? (absorbed BUG-241) | yes |
| BUG-276 | A | open, § 1 | s3, s3-pyarrow, s3-boto3, azure, sftp | caught (BK-359 review) | yes |
| BUG-273 | A | open, § 1 | sftp | caught (BUG-265, BUG-275) | yes |
| BUG-279 | A | open, § 1 | sftp | ? | yes |
| BUG-293 | A | open, § 1 | azure, async-azure | ? | yes |
| BUG-256 | A | open, § 1 | s3-pyarrow, sql-blob, sql-query, http | caught (BUG-246 branch) | yes |
| BUG-255 | A | open, § 1 | s3, s3-pyarrow | caught (BUG-246) | yes |
| BUG-257 | A | open, § 1 | graph | caught (BUG-246) | yes |
| BUG-245 | A | open, § 1 | sql-blob | caught (BUG-243) | yes |
| BUG-253 | A | open, § 1 | graph | ? | yes |
| BUG-280 | A | open, § 1 | local | caught (BUG-275 measurement) | yes |
| BUG-292 | A | open, § 1 | sql-blob, and the flat-namespace `_head_one` probes on S3 and Azure | caught (BUG-281) | yes |
| BUG-251 | E | open, § 2 | ext(cache) | ? | yes |
| BUG-240 | A | open, § 2 | graph, async-memory, async-azure | ? | yes |
| BUG-260 | A | open, § 2 | sql-blob | caught (BUG-259 work) | yes |
| BUG-289 | D | open, § 5 | sftp, s3 | caught (floor lane) | yes |
| BUG-287 | D | open, § 5 | s3-pyarrow, ext(arrow), sql-query | caught (floor lane) | yes |
| BUG-288 | D | open, § 5 | azure | caught (floor lane) | yes |

---

## Proposals (advisory)

Dispositions are the user's; the design itself is argued in
[RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md).

| Finding | Proposed shape | Effort |
|---|---|---|
| H-1, M-1 | One contract kernel implementing the public `Backend` surface over a thin per-backend `Driver` with one operation-scoped classifier; error mapping at a single choke point over calls, listing pages and streams. Reaches the invocation-shaped items and, through its message and attribute guarantee, part of the content-shaped ones; which items it reaches under the RFC's design is the RFC's assignment, not this audit's. Migrate one class at a time with the conformance suite as oracle and its changed cells enumerated first. | L |
| H-2 | A `Session` owning connect, the connect-retry budget, liveness and invalidation behind one `run(op)` entry; SFTP first, Graph second. | L |
| M-2 | One S3 driver (the parked boto3 lane is the candidate ID-202 itself names, with ID-202's own Ship list as the precondition) with the s3fs and PyArrow lanes retired behind a gate; one Azure driver, with how sync callers reach it decided by the RFC's first open question. | M each |
| L-1 | None here; BK-369 and BK-368 own it. | — |

**What the proposals leave.** Clusters D and E, 18 of 71, plus the cluster-A
items RFC-0017 assigns to the driver or to a pending decision rather than to
the kernel, by the rules it states and revises. No
projection of a future count is made here: the residual is the enumeration,
not a number.
