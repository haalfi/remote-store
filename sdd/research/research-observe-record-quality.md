# Research: Checking an `/observe` record before its spec (BK-505)

**Date:** 2026-10-29
**Backlog items:** BK-505 (An `/observe` record's freeze has no stopping rule: the record-quality report's checks are neither adopted nor rejected)
**Status:** Research complete. Background to [RFC-0029](../rfcs/rfc-0029-faithfulness-before-spec.md) R2 and to BK-505; it decides nothing.

---

**Most of what a reader of an `/observe` record is asked to judge can become
mechanical, and a record is not done when a review round finds nothing.**
The report turns cross-references in a record into slots and typed claims a
script checks on every amendment, keeps judgement for extraction and for
what the scripts raise, and replaces "a round found nothing" with gates
calibrated by seeded defects per kind of reviewer. Its stopping rule is the
report's own inference and has not been validated.

## 1. Question and method

The brief is in [BK-505's dossier](../backlog/bk-505-record-quality-research.md):
is an `/observe` record complete, internally consistent and faithful to its
dialog, and when is it done. The full report, with a grade per source, is
[`reports/Observation record completeness and consistency.md`](https://github.com/haalfi/research/blob/28d58e9e482ca514901b5909deae105a410ccdd2/reports/Observation%20record%20completeness%20and%20consistency.md)
in the `haalfi/research` repository at `28d58e9`, branch
`research/observation-record-quality`. Its own trials ran on OP-01's record
at `eb08d990e`, with open items `O14` to `O44` as the known defect set, a set
the report notes is incomplete. A verified edition on the same branch, at
[`8853e80`](https://github.com/haalfi/research/blob/8853e80ac104b24f652741be3b3992e407abe0de/reports/Observation%20record%20completeness%20and%20consistency%20verified.md),
checked six further leads and changes nothing structural; its changes are
folded in below, cited as "verified". This document keeps the results this
repository relies on; other section numbers are the earlier report's.

## 2. Results

| Finding | Strength | Report |
|---|---|---|
| The record's consistency-check lines named 61 of 946 decision pairs. They covered 4 of the 27 known defect pairs in `O14` to `O44` and caught none of the four | own trial on OP-01 | § 2 T2 |
| On OP-01, two unprimed readers found 13 and 12 items, 11 shared, so a Chapman estimate put about 0.2 items left; the primed review then found four more (`O41` to `O44`) | own trial on OP-01 | § 2 T4 |
| With fewer than four inspectors, no capture-recapture estimator of remaining defects was satisfactory; the jackknife estimator's median relative error was −52 % at two and −27 % at three | A (Briand et al. 2000; Petersson et al. 2004) | § 2 T4 |
| Checklist reading did not beat ad hoc reading; perspective-based reading did not beat checklist reading per reader; the document mattered more than the technique | A, human-only evidence | § 2 T2 |
| Pairwise conflict detectors, LLM or NLI, ran at precision 19 % to 67 % and miss conflicts that need three or more statements; only solver hybrids reached high precision, in small studies by their own authors | A to A-workshop, 2023-24 models | § 2 T2 |
| LLM judges of a summary against its dialog do worst on additions that are implied and on the main topic, which is the record's case: open-source judges at 50 % to 60 % balanced accuracy with 2023-24 models. In 2026 one call reaches 91 % to 95 % on short formal statements, with no precision reported, mostly easy negation defects, and long cross-referenced documents such as a record outside what was measured; a judge's finding stays a lead, not a verdict | A (TofuEval); A-pre, its authors' own tool (claimcheck) | § 2 T3; verified change 2 |
| An agent that restates a statement while seeing its source lost 6.0 to 8.8 points of defect recall; a judge also shown the derived artefact raised more false alarms | A-pre, its authors' own tool (claimcheck), short formal statements | verified change 1 |
| An LLM applying a fixed 10-dimension checklist recalled 79.5 % to 98.4 % of a reference set built from production systems, at 46.4 % to 78.8 % precision | A, the authors' own method and data (Kabadi et al., ESEM 2026) | verified change 4 |
| No surviving source measures a way to find questions no checklist raises | search result, unchanged in the verified edition | § 2 T1, § 5; verified change 4 |

## 3. The proposals

The report's own design, *Inference* throughout, in its § 3 and § 4:

- **Mechanical, during the session.** A slot per Environment row × step of
  the operation, each filled or marked not exposed with a reason; each table
  over a declared domain; a register of typed claims extracted from the
  record (a closed list, a rule, an option adopted by reference, a member of
  a domain), checked against each other on every amendment; each claim of a
  Decision aligned to a span of its dialog's answer. The agent that splits a
  Decision into claims does not see the dialog, and the judge sees only one
  claim and the answer (verified change 1).
- **Judged.** The extraction itself, built twice by different agents and
  diffed, and each extracted claim restated in English blind to the record
  and judged against the record text (verified change 6); the candidates the
  scripts raise; reviewers of different kinds
  after the session (a primed backend reviewer, a reader of how a caller
  uses the object).
- **Stopping rule.** A record is ready for its spec when the mechanical
  gates are clean; for each kind of reviewer, seeded defects of that kind's
  class are found at a rate of at least 0.8 and the estimate of real defects
  left is below one blocking defect; and a reviewer of a kind not used before
  finds nothing blocking. Capture-recapture is a cross-check only, within one
  kind and with at least four readers. It assumes, among other things, that
  seeded defects are as hard to find as real ones; that is unverified.

## 4. Consequences here

RFC-0029 R2 takes one thing now: a record is frozen only after
`/observe-review` has re-run on it as its last reopen left it. Whether the
checks of § 3 and the stopping rule bind is BK-505's open decision; R1's
table check (BK-504) is the first of the mechanical gates either way. The
verified edition's first open measurement fits BK-504's run on OP-01: two
independent extractions of the record plus a blind restatement of each
claim, scored against `O14` to `O44` (verified § 4, item 1).
