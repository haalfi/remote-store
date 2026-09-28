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

| Severity | Count | Description |
|----------|-------|-------------|
| High     | 2 | The backend contract is implemented once per class per method, and the SFTP session state machine is hand-rolled across its guards |
| Medium   | 2 | A new backend pays the whole contract again; two services are implemented two or three times over |
| Low      | 1 | Dependency floors, already covered by the floor lane and out of design scope |

**The three-layer architecture is sound; the placement of the contract is
not.** 71 user-impacting defects shipped or sit open across six releases, and
45 of them (63%) are one clause of the `Backend` contract missed on one method
of one class. That clause is written once in spec 003 and implemented by hand
in 13 classes across 204 method bodies, and nothing at the `Store` boundary
enforces it. The prior remedies, more conformance cells and more spec text,
were both applied in full and the class of bug did not shrink, because they
cover the cross-product one cell at a time while the design keeps the product.

**The population, classified.** Filter: audience contains a `user.` value, the
item changed code behaviour (docs-only claims and CI or test-only items
excluded), backend column not `n/a`.

| Cluster | Closed | Open | Total | Share |
|---|---|---|---|---|
| A. Contract clause re-implemented per backend (H-1) | 22 | 13 | 35 | 49% |
| B. Hand-rolled SFTP session lifecycle (H-2) | 10 | 0 | 10 | 14% |
| C. New-backend burn-in: Graph (M-1) | 8 | 0 | 8 | 11% |
| D. Dependency floors and packaging (L-1) | 11 | 3 | 14 | 20% |
| E. Driver-level logic (out of scope) | 2 | 2 | 4 | 6% |

---

## 🔴 High

### H-1. The contract is implemented 13 times, method by method, and enforced 0 times at the boundary — *confirmed*

**Members, closed (22):** BUG-254, 275, 264, BK-358, BUG-265, BK-359, BUG-259,
247, 246, 249, 248, 243, 242, BK-324, BK-316, BUG-231, BK-301, BUG-222, BK-266,
BK-263, BK-306, BK-298. **Open (13):** BUG-276, 273, 279, 293, 256, 255, 257,
245, 253, 280, 292, 240, 260.

Every one is a clause the contract states once — the error-mapping rows and
never-leak invariant (BE-021), the root rule (BE-029), the absent-container
rule, the wrong-type rule, the first-page listing bound, the close posture
(BE-020) — that one class failed to apply on one or more of its methods. Three
properties of the cluster are measured rather than read:

1. **The same clause is fixed N times.** 17 of the 71 entries name two or more
   backend classes (BUG-254, 259, 246, 243, 242, BK-324, BUG-276, 256, 255, 240,
   292, BK-306, BK-298, BUG-285, 232, 287, 289). BUG-259 touched eleven classes
   on two halves of one rule, and spec 003's own table for it records that "a
   class compliant on the writers was not thereby compliant on the destination".
2. **The fix lands per method, so it is missed per method.** BUG-249: three
   listing methods on one class were "the only methods on that class whose wire
   call was not wrapped in its error mapper, against fifteen methods that do
   wrap". BUG-280 is the same shape on `LocalBackend`; BUG-279 is `unwrap`
   outside `_errors()`; BUG-293 is twelve `except` arms on one class; BUG-276
   is seven sites in five files.
3. **The defects were latent in released code and found by audit.** The
   register names the finder for 60 of the 71: audit-016 (Graph), audit-019
   (Azure), audit-020 (SFTP) and the review rounds of BUG-243, 246, 259 and
   265. Only three entries name a user report (BK-354 and BK-356 from
   issue #970; BUG-254 by its migration-guide entry). BK-366's question
   therefore answers "detection improved", but what it detected was shipped
   behaviour, and the audits that found it have read three of the thirteen
   classes in depth.

**Where the contract lives, measured at `8fa22d6`:**

| Figure | Value | Derivation |
|---|---|---|
| Concrete backend classes | 13 (12 shipped; `S3Boto3Backend` is the parked ID-202 PoC, excluded from the wheel) | classes declaring `CAPABILITIES` in their own `__dict__`, spec 003 BE-021's enumeration; `pyproject.toml` `[tool.hatch.build.targets.wheel] exclude` |
| Public-method bodies across sync backend modules | 204 | command (a) below |
| `except` handlers in `src/` | 395 across 40 files | command (b) below |
| `except` handlers, sync Azure against async Azure | 61 against 56 | command (b), `backends/_azure.py` and `aio/backends/_azure.py` |
| Call sites of the eight shared contract guards | 200 across 11 files | command (c) below |
| Error-classifier definitions | 11 | command (d) below |
| `except` handlers in `Store` that touch backend I/O | 0 | `_store.py` carries 2: a `KeyError` on the gate table, a `UnicodeEncodeError` on key validation |
| BE-021, the error-mapping clause | 496 lines | spec 003 lines 676 to 1172 |
| Hand-maintained ABCs | 2 of 21 methods each | `_backend.py`, `aio/_async_backend.py` |
| Conformance test functions | 323 | `rg -c 'def test_' tests/backends/conformance` |

```text
(a) rg -c '^\s+def (exists|is_file|is_folder|read|read_bytes|read_seekable|write|write_atomic|open_atomic|delete|delete_folder|list_files|list_folders|get_file_info|get_folder_info|move|copy|iter_children|glob|check_health|close)\(' src/remote_store/backends
(b) rg -c '^\s*except\b' src/remote_store
(c) rg -c '_reject_root_as_write_target\(|_reject_root_as_file\(|_wrong_type_if_folder\(|_wrong_type_if_file\(|_children_or_absent_container\(|_raise_if_closed\(|_maybe_check_no_file_ancestor\(|_check_no_file_ancestor\(' src/remote_store
(d) rg 'def (_map_exception|_map_error|_classify|classify_\w+|_errors|_translate|_wrap_errors|_map_\w*err\w*)\b' src/remote_store
```

`Store` gates capabilities and scopes paths but applies none of the clauses
above and catches nothing, so "backend-native exceptions never leak" is
asserted 13 times inside backends and zero times at the one boundary every
call crosses. The prose needed to state BE-021 is longer than any backend's
classifier.

The repo has already moved partway toward one shared implementation, and each
step halved the next cluster on the classes it reached: `_flat_ns.py` (495
lines of guards applied by injection), `_S3Base`, `_ErrorMappingStream` with a
`mapper` callback, `_safe_wrap`, `AsyncBackendSyncAdapter`. None reaches all
13 classes and none owns the method bodies, so each clause is still *called*
200 times rather than *applied* once. The 200 call sites are the cost of
stopping half way.

**Why this is a design finding and not a test-coverage finding.** The
bug-prevention research (2026-04-03) and the contract-completeness research
(2026-04-05) diagnosed the same cross-product, "methods × parameters × backends
× failure modes", and prescribed extended conformance and tightened spec text.
Both prescriptions were carried out: the conformance suite reached 323 tests
and BE-021 496 lines. Cluster A still produced 35 defects in six releases. A
test fails only on the cell it covers, and the research's own estimate of the
product was ~1,890 cells; the design keeps the backend axis in the product,
and the tests chase it.

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
release, all found by audit-016 and the readiness review. Under H-1's design
that is the expected price of a new backend: 21 methods, each owing every
clause. BK-345 (open) names the same gap from the test side: "a new backend
that can delete passes CI without meeting" the absent-container rule.

### M-2. Two services are implemented two and three times over — *confirmed*

Two S3 lanes ship (`S3Backend` over s3fs, `S3PyArrowBackend`) with a third
parked (`S3Boto3Backend`, ID-202), and Azure ships as a hand-written sync and
async pair (2,106 and 1,716 lines; 61 and 56 `except` arms). Eight of the 71
entries touched two or more S3 lanes (BUG-254, 242, 276, 255, BK-306, BK-298,
BUG-259, BK-324); the open register still reads "all three S3 backends"
(BUG-276) and "the two s3fs lanes" (BUG-255). BUG-293 counts its arms "seven
sync and five async"; BUG-240 is a sync/async spec disagreement that only the
hand-written pairs can exhibit. Each copy is another chance to miss a clause,
and under H-1 every copy misses independently.

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

## Proposals (advisory)

Dispositions are the user's; the design itself is argued in
[RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md).

| Finding | Proposed shape | Effort |
|---|---|---|
| H-1, M-1 | One contract kernel implementing the public `Backend` surface over a thin per-backend `Driver` of about ten wire primitives plus one classifier; error mapping at a single choke point over calls, listing pages and streams. Migrate one class at a time behind the unchanged conformance suite, flat-namespace family first. | L |
| H-2 | A `Session` owning connect, retry budget, liveness and invalidation behind one `run(op)` entry; SFTP first, SQL and Graph after. | L |
| M-2 | One S3 driver (the parked boto3 lane is the candidate ID-202 itself names) with s3fs and PyArrow lanes deprecated; Azure async-native with the existing sync adapter, as Graph already ships. | M each |
| L-1 | None here; BK-369 and BK-368 own it. | — |

**What the proposals leave.** Clusters D and E, 18 of 71. On this window's
shape a comparable six-release window would carry roughly 20 to 25
user-impacting defects instead of 71, and a new backend would cost ten
primitives and a classifier rather than the eight burn-in defects Graph cost.
