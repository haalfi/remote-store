# RFC-0026: The v1 operations are catalogued before the first operation flow

## Status

Accepted, 2026-10-26, by the maintainer. Drafted 2026-10-26. Tracked as
**BK-493**. Amends
[RFC-0024](rfc-0024-spec-first-reset.md) in three places: step 4b joins the
step table of [research § 9](../research/research-spec-first-reset.md#9-results-and-recommendation),
which RFC-0024 makes binding (C1); step 4b's output joins the ground without a
formal model (C4); and § R4 gains a second exception, spec 053's sections
having no test until a v1 surface exists (C3). It edits the
[ground register](../observe/ground-register.md) (C4). Decisions taken in this
RFC's sessions: decision logs `sdd/decisions/3f9651c0-09db-5c69-8bbb-77ea5f97177e.jsonl`
and, for the revision against the maintainer's deep research (C5),
`sdd/decisions/c886d81c-7d81-58f9-bc3d-f11dc7304e4a.jsonl`.

## Summary

**Before `read()`'s flow, v1's operations are fixed as a catalogue: what v1
offers, one entry per intent, with no signatures and no semantics.**
[Spec 053](../specs/053-store-operations.md) binds it, and
[`sdd/observe/catalogue.md`](../observe/catalogue.md) holds one row per entry;
both join the ground. Each later `/observe` session designs exactly one entry,
so the sessions share one scope instead of each finding its own. Semantics
still grow from `read()` (D5).

## Motivation

Spec 051 states what a store holds and spec 052 how a key addresses it. Step 5
then designs `read()`, and every flow after it one more operation, but nothing
says which operations v1 has. Two costs follow:

- **Each session draws its own boundary.** Whether listing a folder, walking a
  subtree and matching a pattern are one operation or three, or whether a
  conditional write is a mode of writing or its own operation, would be decided
  by whichever session meets it first, from a primed context, and the next
  session would meet it again.
- **Decisions about the surface as a whole have no home.** Whether every
  operation has an async twin, or whether a method may exist that no
  operation's design covers, would be decided per session. Decisions that bind
  every operation's behaviour are a different kind: the first `/observe` run
  (`exists`) decided one, an unacceptable key refused identically by every
  operation, and left two shared open items. Those are not this step's; they
  grow from `read()` under D5 (Open Question 1) and stay tracked in
  [BK-485's dossier](../backlog/bk-485-spec-first-reset.md).

## Proposal

### C1. Step 4b

Research § 9's step table gains a row between step 4 and step 5:

| Step | Work | Why here |
|---|---|---|
| 4b | The operation catalogue: spec 053 and the table beside it, one entry per intent, derived from use cases with 0.33's surface as an omission check only; a deep research on comparable libraries as background. | Every flow from step 5 on designs one entry, so the set of entries is fixed before the first flow. |

Step 5 then depends on steps 4 and 4b.

### C2. How it sits with D5

D5 makes `read()` the first flow and grows the shared layers (key, error,
lifecycle, consistency) from what it needs. Step 4b fixes **scope**, not
semantics, so D5 stands:

- **What the catalogue decides:** which entries exist, each entry's intent,
  what it targets, the kind of result it gives, and whether it is in v1 or
  optional; and what v1's core leaves out, which an extension may still add
  on top of the entries. Spec 053 adds the decisions about the surface as a
  whole: the set is exact, and every entry has a sync and an async form. Which
  stores offer an entry, `v1` on every store and `optional` only where the
  backend declares it, is bound by OP-18's spec, the one place that answers
  what a store supports; a clause in spec 053 would need a call to witness.
- **What it leaves to each entry's session:** signatures, forms (bytes, text,
  stream), outcomes, failures and every axis of
  [`axes.md`](../observe/axes.md). The shared layers still grow from `read()`.
- **When a session finds the cut wrong**, for example an entry that should
  split (research § 8, open point 2), it records a reopen under research § 3;
  spec 053 and the table change in their own flow, never on the side.

### C3. Placement

Spec 053 binds and the table details it, as spec 052 does with its profile
table. The spec cites the table and never copies a row; the table's columns
are defined in the table's own file. Spec 053 is a structure spec in
[`SPEC-DESIGN.md`](../SPEC-DESIGN.md) Rule 2's sense: a witness of its
violation is one public surface of the v1 API, read without a call, so it
takes Rule 3's form for structure. Whether an operation does what its entry
intends is the entry's spec, never spec 053's.

**RFC-0024 § R4 gains a second exception.** § R4 makes `SPEC-DESIGN.md` bind
every v1 spec, and its Ready item 2 wants a failing test per section. No test
can witness spec 053 until a v1 surface exists, so its Tested against is
`None.` and its IDs sit on `check_spec_marks.py`'s deferred-feature allowlist
until the flow that builds the surface adds the test.

**0.33 is an omission check, not a column.** The table carries no 0.33 name,
since the table is ground and 0.33's surface in the ground is the priming the
first `/observe` run traced to a register row (BK-485's dossier). The check was
run on the draft entries against `src/remote_store/_store.py` and `ext/` at
`e285319`; its per-entry result is in
[BK-493's dossier](../backlog/bk-493-operation-catalogue.md), which the D8
comparison of each flow reads.

**Spec 053 supersedes** spec 001's STORE-008 and spec 029's ASYNC-046, the two
lists of 0.33's surface, and both specs get RFC-0024 D7's header.

### C4. Ground

The ground register gains two `active` rows with flow `catalogue`:
`sdd/specs/053-store-operations.md` and `sdd/observe/catalogue.md`. Neither
holds semantics, so admitting them primes a session with scope only. Step 4b
is not one of research § 3's flows, which each take one operation to a spec
and its formal model, so its output joins on this RFC's acceptance, with no
formal model. The number 053 is reused after RFC-0025 froze the contract
kernel's spec 053, so the register's Spec numbering section gains the same
dated rule RFC-0025 D6 gave 052. Not ground: BK-493's dossier, which holds the 0.33 mapping, and the deep-research
doc ([`research-operation-catalogue.md`](../research/research-operation-catalogue.md)),
whose per-entry pitfalls are notes for each entry's session and would prime
every other one; a session's maintainer may name its entry's part at the
start (research § 4, S3).

### C5. The deep research

The maintainer ran the brief in BK-493's dossier against ten comparable
libraries; the report is filed as
[`research-operation-catalogue.md`](../research/research-operation-catalogue.md),
whose filing note maps each finding to what the catalogue took from it. In
short: the cut stands (conditions on writes only, three listing entries with
OP-07's depth limit); OP-20 widens to system properties and OP-09's info to
an identity token where the backend offers one; the catalogue gains a Not in
v1 list; and spec 053 bounds the core only, so an extension may add a feature
no entry has.

## Alternatives Considered

All decided in the log above:

- **Depth:** inventory only, which leaves the decisions about the surface as a
  whole (the exact set, both forms) without a home; or inventory with signatures and error kinds, which
  decides what each unprimed session exists to decide.
- **Input:** 0.33's surface pruned, which anchors v1 on 0.33; or a fresh
  unprimed session, which needs the hook's allowlist and one more session.
- **Granularity:** one entry per public method, which fixes method names before
  the sessions design them.
- **Async:** sync only in v1, or async only where I/O waits matter.
- **Placement:** the catalogue alone as ground, or spec 053 alone, which has no
  form for a row per entry; or a research doc outside the ground, which leaves
  scope unenforced. The catalogue binding and the spec explaining it was the
  reverse of the split chosen.
- **The 0.33 column:** kept in the table, against S1; or a sibling table off
  the register, a second file to keep in step.
- **Process:** this RFC first and the catalogue in a second PR, or the
  catalogue first and the RFC after.
- **Fold into BK-485** with no RFC, which leaves RFC-0024's step list out of
  date.
- **Against the research (C5):** one entry for conditions on every operation,
  as OpenDAL's conditional-operations spec does, which is a modifier rather
  than an intent; or a conditional read beside OP-05. One listing entry with
  depth and pattern as options, or no depth limit. Presigned URLs and append
  as optional entries. Shared decisions such as "no silent no-op" in spec
  053, which would give it a second kind of truth, or a shared-decisions
  layer before `read()`, which changes D5.

## Impact

- **Public API:** none now. When the API flow builds v1's surface, spec 053's
  clauses bind it (RFC-0024 § R4).
- **Backwards compatibility:** none now. Each entry's flow compares its
  operations with 0.33 (D8); an entry with no 0.33 counterpart, or a 0.33
  method no entry serves, becomes a break record there.
- **Process:** research § 9's step table, as RFC-0024 carries it; the ground
  register; D7 headers on specs 001 and 029; the research doc under
  `sdd/research/`. RFC-0024 carries an "Amended by
  RFC-0026" line.
- **Testing:** none. Spec 053 is tested against nothing until a v1 surface
  exists (C3, its Notes); the flow that builds the surface adds a test that
  compares its public operations with the catalogue.

## Open Questions

1. **Shared decisions beyond the surface** grow from `read()` under D5, and
   spec 053 states none. Which shared layer each lands in is open; the
   research's advisory note 7 lists the ones comparables most often had to
   retrofit (missing-key delete, no silent ignore of an unsupported option,
   exception typing, retries tied to idempotency, a failure mid-write), as
   input to `read()`'s session and each later one.
2. **Order of the flows after `read()`.** The catalogue lists entries, not the
   order their sessions run in.

## References

- [RFC-0024](rfc-0024-spec-first-reset.md) and
  [`research-spec-first-reset.md`](../research/research-spec-first-reset.md)
  §§ 3, 4 and 9.
- [Spec 051](../specs/051-store-tree.md), [spec 052](../specs/052-store-key.md).
- [`sdd/observe/axes.md`](../observe/axes.md), the axes each entry's session
  walks.
