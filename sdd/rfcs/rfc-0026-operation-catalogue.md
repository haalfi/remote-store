# RFC-0026: The v1 operations are catalogued before the first operation flow

## Status

Draft, 2026-10-26. Tracked as **BK-493**. Amends
[RFC-0024](rfc-0024-spec-first-reset.md) by adding step 4b to the step table
of [research § 9](../research/research-spec-first-reset.md#9-results-and-recommendation),
which RFC-0024 makes binding, and adds two rows to the
[ground register](../observe/ground-register.md). Decisions taken in this RFC's
session: decision log `sdd/decisions/3f9651c0-09db-5c69-8bbb-77ea5f97177e.jsonl`.
Revised against the maintainer's deep research on the drafted catalogue before
review.

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
- **Decisions that bind every operation have no home.** The first `/observe`
  run (`exists`) decided one, an unacceptable key refused identically by every
  operation, and left two shared open items; the next session would rediscover
  them ([BK-485's dossier](../backlog/bk-485-spec-first-reset.md), the report
  on that run).

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
  optional. Spec 053 adds the decisions about the surface as a whole: the set
  is exact, every entry has a sync and an async form, and an optional entry is
  served only where its backend declares it.
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
violation is one public surface of the v1 API, so it takes Rule 3's form for
structure and needs no exception to RFC-0024 § R4.

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
holds semantics, so admitting them primes a session with scope only. Not
ground: BK-493's dossier, which holds the 0.33 mapping, and the deep-research
doc, whose per-entry pitfalls are notes for each entry's session and would
prime every other one; a session's maintainer may name its entry's part at the
start (research § 4, S3).

## Alternatives Considered

All decided in the log above:

- **Depth:** inventory only, which leaves the decisions shared by every
  operation without a home; or inventory with signatures and error kinds, which
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

## Impact

- **Public API:** none now. When the API flow builds v1's surface, spec 053's
  clauses bind it (RFC-0024 § R4).
- **Backwards compatibility:** none now. Each entry's flow compares its
  operations with 0.33 (D8); an entry with no 0.33 counterpart, or a 0.33
  method no entry serves, becomes a break record there.
- **Process:** research § 9's step table, as RFC-0024 carries it; the ground
  register; D7 headers on specs 001 and 029. RFC-0024 gets an "Amended by
  RFC-0026" line on acceptance.
- **Testing:** none. Spec 053 is tested against nothing until a v1 surface
  exists (its Notes).

## Open Questions

1. **The deep research** on the drafted entries, run by the maintainer from the
   brief in BK-493's dossier: completeness, the cut, optional entries, shared
   decisions and per-entry pitfalls. Its doc is filed under `sdd/research/` and
   the catalogue and spec 053 are revised against it before review.
2. **Further shared decisions.** Whether spec 053 also states decisions about
   every operation beyond the surface (key refusal, error taxonomy, timeouts,
   closing, consistency), or whether each grows from `read()` under D5. The
   research's question 4 informs it.
3. **Order of the flows after `read()`.** The catalogue lists entries, not the
   order their sessions run in.

## References

- [RFC-0024](rfc-0024-spec-first-reset.md) and
  [`research-spec-first-reset.md`](../research/research-spec-first-reset.md)
  §§ 3, 4 and 9.
- [Spec 051](../specs/051-store-tree.md), [spec 052](../specs/052-store-key.md).
- [`sdd/observe/axes.md`](../observe/axes.md), the axes each entry's session
  walks.
