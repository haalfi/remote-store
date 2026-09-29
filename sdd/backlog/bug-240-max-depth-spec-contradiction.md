# BUG-240 — ASYNC-014 and DEPTH-003 state opposite rules, and `GraphBackend` implements the async one
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

[ASYNC-014](../specs/029-async-store-backend-api.md) says "`max_depth` limits
traversal depth (when set, `recursive` is ignored)" **while citing DEPTH-003**,
which states the opposite for the Backend ABC: `max_depth` applies only when
`recursive=True`. `GraphBackend.list_files` follows ASYNC-014 and pins it at
`tests/backends/graph/aio/test_list.py:183` — `recursive=False, max_depth=2`
returns depth-2 files, where a sync backend returns immediate children only.
So identical arguments return different files depending on the backend.
**Both readings are asserted by a passing test, on different backends.** That
is the state Rule 7 calls a live disagreement rather than a defect in one side,
so which way it resolves is a decision, not a lookup.
**The split is inside the async lane, not between the lanes.**
`AsyncMemoryBackend` and `AsyncAzureBackend` implement DEPTH-003's reading;
`GraphBackend` implements ASYNC-014's — two async backends already disagree
with a third.
**Three artifacts assert the ASYNC-014 reading, not one.** ASYNC-014 itself,
`tests/backends/graph/aio/test_list.py:183`, and `GraphBackend.list_files`'s
own docstring — which BK-331 made *authoritative* for depth strategy by
replacing spec 037's per-backend table with a pointer to each backend's
docstring. So closing this means changing a doc BK-331 promoted to source of
truth.
**Why nothing caught it:** there is no async twin of
`test_list_files_non_recursive_ignores_max_depth`, so conformance never
cross-checks the two; and both `Store` and `AsyncStore` normalise `max_depth`
into `recursive` before delegating, so the divergence is invisible to every
caller above the ABC. Reachable only by a direct backend call.
**Whichever way it goes, the async conformance cell is part of the fix** —
without it the next divergence is equally invisible. Expect it to turn a
backend red on arrival; that is the item working, not a regression.

## Decision (2026-09-29, BK-387)

**DEPTH-003 wins.** Taken as RFC-0017's Open Question 4 answer: the kernel
encodes the `max_depth` algorithm once at D3 step 1, and it cannot encode a
clause the specs dispute. DEPTH-003's reading is the one
`sdd/formal/BackendContract.dfy` verifies (`rg -n 'DEPTH-003'
sdd/formal/BackendContract.dfy`: the `ListFiles` postcondition constrains
`!recursive` to depth 0). ASYNC-014's wording is DEPTH-001's Store-level rule
copied onto the backend. The fix therefore does four things:

- amends ASYNC-014;
- changes `GraphBackend.list_files` and its docstring;
- changes the pin in `tests/backends/graph/aio/test_list.py`;
- adds the async conformance cell named above.
