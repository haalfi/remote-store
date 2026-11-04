# RFC-0031: 0.33 is frozen; spec work files nothing against it

## Status

Accepted, 2026-11-04, by the maintainer. Tracked as **BK-512**, which it
decides. Amends [RFC-0024](rfc-0024-spec-first-reset.md) § Summary's last
sentence, R1's D2, D8 and D9 rows, R2's admission list, R3's class K, R4's
first paragraph and R5's sentence on which differences get a row; and
[RFC-0025](rfc-0025-freeze-kernel-line.md)'s row for R3, class K (§ What
changes in RFC-0024 and elsewhere). Decisions: the rule and its vehicle in
decision log `sdd/decisions/2d3cd12d-fc9a-5a23-975e-07578aa00b3d.jsonl`
("Freeze rule": amend RFC-0024), the four questions below in
`sdd/decisions/c51bda27-d121-5b99-9216-5f2363c5ac6e.jsonl`.

## Summary

**0.33's code and specs 001 to 050 are frozen. No item is filed against 0.33
from spec, observe, spike, audit or review work; only an issue a user of a
released 0.33 version reports becomes a 0.33 BUG.** A difference between v1
and 0.33 that such work finds is evidence for its flow's 0.33 comparison
(RFC-0024 D8), and there a break record, never a 0.33 item.

## Motivation

The maintainer set the rule on 2026-11-04, after BK-511 recorded Local's
`read()` gaps C1 to C7 and an Azure gap as evidence only (its
[report § 7](../research/bk-511-op01-behaviour-classification/report.md)).
The repo said the opposite, in the places the trace's orient commands found
(`sdd/traces/bk-512-033-frozen.yml`, `orient:`):

- RFC-0024's Summary, D8 and R4 make a difference "a break record or a 0.33
  defect"; R5 makes the defect "a K item instead"; R3's class K "Stays open.
  Fixed master first".
- [`000-process.md` Rule 3](../000-process.md#rules) and its two
  agent-facing copies repeat "a break record or a 0.33 defect".
- BK-469 expects each key-layer difference to become "a `sdd/v1-breaks.md` row
  or a 0.33 defect".
- BUG-346 was filed from the OP-01 spike's rerun (C8), before the rule.

A session reading these files files 0.33 BUGs from every spec flow, each a fix
to code v1 replaces.

## Proposal

### F1. What may become a 0.33 item

**A 0.33 BUG (RFC-0024 R3 class K) is an issue a user of a released 0.33
version reports, which the maintainer admits.** Admitting it, the maintainer
confirms the rating
[`CONTRIBUTING.md` § When to bump](../../CONTRIBUTING.md#when-to-bump) gives
its fix:

- **patch:** fixed on master and shipped in the next 0.33 patch, as RFC-0025
  D5 and its row for class K say; after the `release/0.33.x` cut, a
  cherry-pick or port to that branch (RFC-0024 R2).
- **minor or higher:** a candidate break for its operation's flow, as
  RFC-0025's row for R2's breaking-fix rule says.

Spec, observe, spike, audit and review work, and a maintainer's own probe,
file no item against 0.33. Rule 3's "the code is wrong" still describes 0.33
code that breaks its own spec; it no longer makes a backlog item of it.

### F2. A difference found by spec work

**It is evidence, then at most a break record.**

- **During a flow** (an `/observe` session, a review, a spike, a
  classification), a difference from 0.33 is recorded in that flow's research
  report, with its reproduction, as BK-511's § 7 records Local's gaps.
- **At D8's comparison**, the pass reads that evidence with the 0.33 record
  (master's suite while master's code is 0.33, RFC-0025 D5). A difference
  becomes a `sdd/v1-breaks.md` row (RFC-0024 R5) when the
  v1 clause differs from what 0.33 does, and nothing otherwise. This holds
  when 0.33 also breaks its own spec: the caller still meets a change.

### F3. Items filed before this RFC

**An open item keeps the class and disposition it was filed with; the rule
covers new items.** BUG-341, BUG-342 and BUG-343, among others, stay K items.
One exception: **BUG-346** is absorbed into BK-485 as evidence for OP-01's
comparison. It was filed from the spike rerun's C8, not by a user, and its
open decision, one wrapper over every `read()` or one per backend, is the
Failed state OP-01's D51 and D93 already decide for v1.

### What changes in RFC-0024 and RFC-0025

| Clause | Becomes |
|---|---|
| RFC-0024 § Summary, last sentence | A difference between a v1 spec and 0.33 is evidence for the comparison and, there, a break record; never a defect in the v1 spec, and never a 0.33 item (F2). |
| RFC-0024 D2, D9 and R2's admission list (from the cut on, RFC-0025 D5) | The fixes `release/0.33.x` takes (D2's "patch-rated fixes", R2's "bug fixes"), and so D9's "0.33 patch from `release/0.33.x`", carry only fixes of K items as F1 defines them. Floor raises, CI, docs and metadata are unchanged. |
| RFC-0024 D8 | "a difference becomes a break record or a 0.33 defect" reads "a difference becomes a break record or nothing" (F2). |
| RFC-0024 R3, class K, with RFC-0025's row | Holds only issues F1 admits. Its disposition is RFC-0025's row's, the patch rating confirmed by the maintainer. |
| RFC-0024 R4, first paragraph | "a break record or a 0.33 defect (D8)" reads "evidence for D8's comparison, where it may become a break record" (F2). |
| RFC-0024 R5, "D8's pass adds a row for each difference that is not a 0.33 defect; one that is a 0.33 defect becomes a K item instead" | Reads "D8's pass adds a row for each difference": one that is also a 0.33 defect gets a row too, and no K item (F2). |

RFC-0024 and RFC-0025 each get an "Amended by RFC-0031" line; their text is
the record and is not rewritten.

## Alternatives Considered

All decided in the second log above:

- **Vehicle:** RFC-0024 rewritten in place under an amendment line, which
  leaves RFC-0025's rows amending text that changed under them and the
  rejected options only in a log.
- **A difference found by spec work:** a `v1-breaks.md` row at discovery,
  before D8, with no v1 clause ID until the spec exists; or evidence plus a
  user-docs list of known 0.33 gaps, a page to keep in step with evidence.
- **The 0.33 line:** the author's own bump-table rating, checked only in
  review; or no 0.33 fixes at all beyond security and floor patches, every
  user report waiting for 1.0.0.
- **BUG-346:** kept as a grandfathered K item; or absorbed together with
  BUG-341, BUG-342 and BUG-343, reversing fixes RFC-0024 and RFC-0025 already
  rated patch.

## Impact

- **Public API:** none.
- **Backwards compatibility:** 0.33 users keep patch fixes, for the issues
  they report.
- **Process:** [`000-process.md` Rule 3](../000-process.md#rules), its copies in
  `CLAUDE.md` principle 5 and `.claude/agents/store-backend-expert.md`
  (the ripple-check's Authority direction command,
  `rg --no-ignore --hidden -e 'code is wrong' -e 'spec is source of truth'
  CLAUDE.md .claude/ sdd/`), and
  [`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release). No skill
  under `.claude/skills/` promises a 0.33 item (case-insensitive `Grep` for
  `0\.33|break record|K item|class K|defect` there: the 0.33 hits are
  `/observe`'s two, which file nothing).
- **Backlog:** BK-469's index entry; BUG-346 absorbed into BK-485 (F3).
- **Testing:** none.

## Open Questions

None.

## References

- [RFC-0024](rfc-0024-spec-first-reset.md),
  [RFC-0025](rfc-0025-freeze-kernel-line.md).
- [BK-511's report](../research/bk-511-op01-behaviour-classification/report.md)
  § 7, the evidence this rule first applied to.
