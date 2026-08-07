# Research: GitHub spec-kit compared against our SDD process (ID-238, BK-343)

**Date:** 2026-08-07
**Backlog items:** ID-238 (trace-outcome report review trigger), BK-343 (backlog item authority rule)
**Status:** Research complete — recommendations filed and shipped

---

## 1. Problem Statement

[GitHub spec-kit](https://github.com/github/spec-kit) is an open-source
Spec-Driven Development toolkit with a workflow, a command set and a
customization model that overlap ours. The question this document answers is
what, if anything, we should adopt from it.

The obvious way to answer that question is to read spec-kit's feature list and
pick the features we lack. That method has a defect this repo has already
diagnosed elsewhere: it selects for *absence* rather than for *cost*. A missing
mechanism that has never cost us anything is not a gap, and adopting it spends
review attention — the scarce resource — on a problem we do not have.

So the decision this research informs is narrower than "what can we learn":
**which external ideas address a failure this repo can show evidence of.** The
filter is the trace corpus, which records where our own descriptions have failed
their readers ([`CONTENT-RULES.md` § Finding the documents that are failing
readers](../CONTENT-RULES.md)).

Constraints that bind the answer:

- [`DRIFT-RULES.md` Rule 5](../DRIFT-RULES.md#mandatory-path) and
  [Rule 7](../DRIFT-RULES.md#miss-rate): a new check needs a stated reason to
  exist and a stated bound. "Spec-kit has one" is neither.
- [`CONTENT-RULES.md` Rule 1](../CONTENT-RULES.md#six-month-test): anything
  adopted has to still be true in six months.
- [`CLAUDE.md` § Audits](../../CLAUDE.md#audits): a diagnosis is what carries
  authority; a prescription is advisory. This document is bound by its own
  finding (§ 3.2).

---

## 2. Survey

### 2.1 spec-kit

**Pattern:** specifications are executable inputs that generate implementations,
rather than documents that guide them. "Specifications don't serve code — code
serves specifications."

**How it works:** a command pipeline — `/constitution`, `/specify`, `/clarify`,
`/plan`, `/tasks`, `/implement`, with `/analyze`, `/checklist` and `/converge` as
consistency passes. Artifacts live per-feature under `specs/NNN-feature/` as
`spec.md`, `plan.md` and `tasks.md`. A `constitution.md` holds project
principles that downstream artifacts are checked against. Customization is
layered as extensions, presets and bundles; 30+ agents are supported.

The mechanisms worth naming individually:

- **`/clarify`** scans a nine-category ambiguity taxonomy (functional scope, data
  model, UX flow, non-functional attributes, integration, edge cases,
  constraints, terminology, completion signals), marks each Clear / Partial /
  Missing, asks at most five multiple-choice questions, and writes each answer
  back into the spec under a dated `## Clarifications` heading.
- **`/analyze`** runs six detection passes (duplication, ambiguity,
  underspecification, constitution alignment, coverage gaps, inconsistency) and
  emits a findings table plus a requirement-to-task coverage table with a
  coverage percentage.
- **`/converge`** classifies every gap between spec and code as `missing`,
  `partial`, `contradicts` or `unrequested`, and may only append.
- **`/checklist`** generates "unit tests for requirements writing" — items that
  grade whether a requirement is well-written, with an explicit ban on items
  that verify system behaviour.
- **`spec-template.md`** marks unresolved decisions inline as
  `[NEEDS CLARIFICATION: ...]`, orders user stories P1/P2/P3 with each
  independently testable, and requires success criteria to be measurable and
  technology-agnostic.

**Trade-offs:**

- Pro: cheap to adopt, agent-agnostic, and the ambiguity and gap taxonomies are
  genuinely well-factored vocabulary.
- Pro: `[NEEDS CLARIFICATION]` makes an unresolved decision visible *in the
  artifact* instead of resolving it by guess.
- Con: enforcement is a model reading artifacts and reporting. `/analyze` claims
  "rerunning without changes produces consistent IDs and counts", which is not a
  property an LLM pass has.
- Con: its consistency model is pairwise comparison across spec ↔ plan ↔ tasks ↔
  code, which is the N² shape [Rule 1](../DRIFT-RULES.md#one-driver) rejects; and
  those four artifacts are generated from one another by one model in one
  session, so [Rule 8](../DRIFT-RULES.md#independence) applies at full force.
- Con: specs are per-feature and effectively disposable. There is no concept of a
  stable ID, a published contract, or a breaking change.
- Con: the constitution's articles are asserted rather than derived, and several
  are over-fitted (Article I requires every feature to begin as a standalone
  library; Article VII caps a project at three sub-projects).

### 2.2 Our process

**Pattern:** specs are durable contracts with immutable section IDs; agreement
between artifacts is enforced mechanically where it can be, and arbitrated by a
written authority rule where it cannot.

**How it works:** 50 specs under `sdd/specs/` with stable `PREFIX-NNN` sections,
34 ADRs, a formal layer (Dafny and TLA+) with a compiled-oracle principle, and
roughly 25 `check_*.py` gates wired into `lint`, `preflight`, `docs-gate` and CI.
[`000-process.md` Rules 3 and 7](../000-process.md#rules) settle what happens when
prose, the Dafny model and the conformance suite disagree, including a residue
where the contract is undecided rather than misattributed.
[`DRIFT-RULES.md`](../DRIFT-RULES.md) governs how any cross-artifact check is
designed. The trace corpus records what each piece of work actually read.

**Trade-offs:**

- Pro: the enforcement is deterministic and localizing, and each gate states its
  own bound.
- Pro: the process is instrumented. It can be asked which of its own documents
  are failing readers, which is the question this document runs.
- Con: the authority stack is large. Roughly 2,900 lines across the top-level
  `sdd/` process docs before a spec is written.
- Con: it is entirely repo-bound and does not travel.

---

## 3. Evaluation

### 3.1 The filter

`hatch run report-trace-outcomes`, measured at **`4076ed7`**:

| Measure | Value |
|---|---|
| Traces | 270 |
| Steps | 3,838 |
| Steps carrying an explicit `outcome` | 1,655 (43.1%) |
| Negative tags | 207 (`misleading` 180, `unclear` 27) |
| Traces and references carrying them | 110 traces, 110 references |

Top-ranked references:

| Total | `misleading` | `unclear` | Reads | `rate` | Reference |
|---:|---:|---:|---:|---:|---|
| 22 | 18 | 4 | 236 | 9.3% | `sdd/BACKLOG.md` ¹ |
| 10 | 3 | 7 | 287 | 3.5% | `sdd/CLAUDE-REFERENCE.md` |
| 8 | 7 | 1 | 55 | 14.5% | `src/remote_store/backends/_sftp.py` |
| 7 | 6 | 1 | 15 | 46.7% | `src/remote_store/backends/_local.py` |
| 6 | 6 | 0 | 78 | 7.7% | `sdd/BACKLOG-DONE.md` ¹ |

¹ Two halves of one artifact — `BACKLOG.md` drains into `BACKLOG-DONE.md`, so
the combined signal is **28**. See bound 1 below.

**These counts are exact and already perishable, and the commit is stamped above
because this document has now gone stale twice on itself** — once when the branch
rebased, once when a review-fix commit added tags to the very trace being counted.
Both were caught by a reader, not by the table. They follow the precedent set
by [research § 5 finding
7](research-inconsistency-detection-multi-artifact.md): a dated measurement,
with the generated report named as the successor SSoT. **Re-run the report and
compare against the stamped commit rather than trusting these figures** — that
comparison is the only thing that makes the staleness visible, which is the same
argument § 4.1 makes for recording corpus totals at each release.

**The stamp is what stops the regress.** This document's own trace is in the
corpus it measures, so every commit that edits the trace changes the figures —
including the commit that corrects them. An unstamped table is therefore false on
arrival and there is no commit at which it is not; a stamped one is a fact about
a named ref, which stays true and merely gets older. Read the figures as
"the corpus at `4076ed7`", never as "the corpus now".

**Three bounds the report documents, which this table must be read under**
([Rule 7](../DRIFT-RULES.md#miss-rate) — the tool states them, so citing the
ranking without them is a partial reading):

1. **Rows 1 and 5 are two halves of one artifact.** The report's "Drain files"
   bound: `sdd/BACKLOG.md` drains into `sdd/BACKLOG-DONE.md` as items complete,
   and a tag written against a live item stays pinned to `BACKLOG.md` after the
   cited section moved out. Combined signal is **28**, not 22, and localization is
   broken for the drained part. This is not hypothetical here: every exemplar in
   § 3.2 is a completed item now living in `BACKLOG-DONE.md`. It does not
   overturn § 3.3's adopt decision, because the rule belongs where items are
   *authored*, which is `BACKLOG.md`.
2. **The sort key is exposure at least as much as failure rate.** `CLAUDE.md`
   makes "open the backlog item" the first step of nearly every trace, so
   `sdd/BACKLOG.md` gets a chance to earn a tag in almost all of them. A file
   that misled every reader it ever had can sort below one that misled a small
   fraction of many.
3. **`rate`'s denominator mixes assessed and never-assessed reads.** Coverage is
   43.1% overall and varies per reference, so `rate` is "negative tags per
   citation" and interrogates a row rather than ordering rows.

That precedent also supplies a second measurement for free. The same
reference ranked first there, at **16**, hand-counted at that branch head. It is
**22** now. The signal has been visible, attributed, and growing, across the
entire interval in which nothing consumed it.

### 3.2 What the top row actually is

The tag is noisy: a `misleading` tag can mean the reader was misled, or merely
that they recorded checking and diverging. So the 22 extracts were read rather
than counted. Roughly 11 are a genuine defect in the item, and they share one
shape — **the item's prescription or premise was wrong by the time it was
implemented**:

- BK-331: "Trusting the item body over the cross-reference would have produced a
  wrong fix to the Azure row."
- BK-291: prescribed atomic write plus a lock; "the os.replace half proved wrong
  on Windows."
- BK-269: the item said "install hatch in the job, as the publish/drift jobs
  already do". No CI job used hatch.
- BK-324 facet 3: "neither half of it survived checking."
- BUG-220: "The BACKLOG recipe under-specified: it reproduces 0/20 with SHORT
  path components."
- BUG-221: "as written is NOT reproducible."
- BK-271: the item's framing and line references described work that had already
  happened.

The other high-ranked rows are not process wounds. `CLAUDE-REFERENCE.md` is
mostly `unclear` tags recording ripple rows that did not anticipate a case, and
those already became BK-333 and BK-334 — a feedback loop that is working. The
backend files are review rounds catching real defects, which is review working.

`sdd/audits/` shows the same prescription-decay shape as the backlog (4 tags,
all "audit proposes X; prescription reframed"), and that is precisely the failure
[`CLAUDE.md` § Audits](../../CLAUDE.md#audits) rule 3 already exists to absorb.
**`BACKLOG.md` has no equivalent rule.** `BACKLOG-DONE.md:3848` shows a
contributor applying the audit rule to a backlog item by analogy, which is the
norm existing informally without a home.

### 3.3 Candidates against the evidence

| Candidate from § 2.1 | Evidence in the corpus | Verdict |
|---|---|---|
| Mark prescriptions as advisory / `[NEEDS CLARIFICATION]` | ~11 of 22 tags on the top-ranked reference | **Adopt**, reshaped as an authority rule (BK-343) |
| `/clarify` nine-category taxonomy | Spec-side tags are staleness after behaviour changed, not authoring ambiguity | Reject: solves a problem we do not have |
| `/analyze` requirement-to-task coverage | `check_spec_marks.py` already does this direction, deterministically and with five failure modes | Reject: we are ahead |
| Gate for "code without a spec" ([Rule 1](../000-process.md#rules)) | Zero tags | Reject: theoretical symmetry, not a measured cost |
| `/converge` four-way gap vocabulary | Weak (the audit rows) | Defer: cheap but unmeasurable alone |
| Checklists as "unit tests for English" | Zero tags | Reject |
| Extensions / presets / bundles packaging | Zero tags; no consumer | Reject |
| Stale `path:line` reference gate | Only 6 such references in `BACKLOG.md`; the real defect is stale premises, which no gate can check | Reject on [Rules 5 and 7](../DRIFT-RULES.md#mandatory-path) |

### 3.4 The finding the filter produced about itself

Nothing consumes the report. `hatch run report-trace-outcomes` is referenced by
`CLAUDE.md`, `CONTENT-RULES.md`, its own tests and the backlog, and by no skill,
no CI job and no checklist. This session is, as far as the repo records, its
first reading.

That is not a new discovery — **ID-238 already states it**, and states why: BK-330
shipped [research § 9](research-inconsistency-detection-multi-artifact.md) step
3's report and dropped step 3's cadence sentence. What is new is that the item
now has the measurement it was waiting on, and that the interval it describes has
a measured cost (§ 3.1: 16 → 22 on one reference).

It also has a deadline the repo set for itself.
[`DRIFT-RULES.md` Rule 6](../DRIFT-RULES.md#tolerated) says a check with no
register owner "will be switched off instead", and BK-330 named ID-238 as that
owner. Leaving ID-238 open indefinitely is therefore an argument for deleting the
report, not for keeping it.

---

## 4. Recommendation

**Two changes, both filed.** Everything else in § 3.3 is rejected or deferred,
and the rejections are the substance of this document as much as the adoptions.

### 4.1 Close ID-238 with a release-anchored trigger

[Rule 9](../DRIFT-RULES.md#period) requires the period to come from the drift
rate, not the calendar, so the TLA+ six-month analogy ID-238 cites is rejected as
the mechanism even though it supplies the pattern.

What invalidates the report is merged traces. The repo's only recurring, ticketed
checkpoint downstream of merged traces is a release.

**The growth rate is re-derived here, not carried forward.** ID-238's body quoted
BK-330's "roughly +3 negative tags per merged PR" and explicitly said to
re-measure rather than trust it. Measuring the corpus at the refs themselves:
`83e22a3` (BK-330's last in-review point) carries 193 negative tags over 260
traces, and `73d4079` carries 205 over 269, across the eight pull requests
#944–#951.

| Metric | BK-330's figure | Re-derived |
|---|---:|---:|
| Negative tags per merged PR | ~3 | **~1.5** |
| Traces per merged PR | ~1 | **~1.1** |

The trace rate holds; the tag rate is roughly *half* what BK-330 measured.

**The per-release figure is a separate measurement, and the obvious shortcut is
wrong.** Those eight PRs span three days (#944 merged 2026-08-04, #951 on
2026-08-07), so that window is the *measurement* window, not a release interval.
Measured separately: CHANGELOG release dates give intervals of 4 to 18 days,
median ~10, and merged commits per interval over the last three are **0**
(0.29.0 → 0.29.1, a genuinely quiet 17 days), **24** (0.29.1 → 0.30.0, 10 days),
and **27** (0.30.0 → today, 19 days and still open).

So a release fires on anywhere from 0 to ~27 PRs, or roughly 0 to 40 negative
tags at the re-derived rate. The decision survives, and the range is a better
argument for it than the point estimate was: a busy interval moves the ranking
comfortably, and a quiet one moves it not at all — which is exactly what bound 1
below is for, and why the totals have to be recorded rather than eyeballed.

So: **`CONTRIBUTING.md` § Release Phase 0 gains one step** — run the report,
record the corpus totals, and record a decision (act / defer / accept) as a
backlog entry. The ticket half is what the ID-150 pattern exists to enforce:
`sdd/formal/README.md` notes that "a calendar without a ticket is the same as no
calendar."

**The ticket is pinned, not merely required.** ID-150 works because
`formal/README.md` names the ID, so the next reader can find the previous
decision instead of grepping for a phrase; a step that says only "record a
backlog entry" keeps the ticket and drops the pin. So the first revisit is
tracked as **ID-249**, it lives in `BACKLOG.md` as `[ ]` (a scheduled decision is
pending work, not completed work), and each revisit names its successor's ID on
close — the same self-renewing chain ID-150 runs.

**Bound 1 — the cadence proxy, and its mitigation.** A release is a *proxy* for
corpus growth, not the growth itself, so a lengthening cadence degrades the
trigger silently. The mitigation has to be built rather than asserted: the report
prints only *current* totals and stores no prior reading, so recording the totals
in the Phase 0 backlog entry is what gives the next reading a baseline to
difference against. Without that the bound would be stated and left unmitigated.
The failure mode is a stale ranking, not a missed gate, because the report was
never a gate.

**Bound 2 — the selection rule.** "The top-ranked reference" selects on the
absolute count, which § 3.1's bound 2 says measures exposure. At 22 against 10
for the runner-up, that phrase resolves to `sdd/BACKLOG.md` for many releases
running, while a high-`rate`, low-`reads` document never reaches the checklist.

So the step selects the top-ranked row **plus any row with `rate` at least twice
the top row's `rate` and `reads` ≥ 20**. That threshold is stated numerically on
purpose: the report computes no dispersion, no baseline and no outlier flag, so
"is an outlier" would have left the second selector undefined, and an undefined
second selector collapses to the defined first one — reinstating the very
under-selection this bound exists to prevent. Against § 3.1's table it selects
`_sftp.py` (14.5% over 55 reads) and excludes `_local.py` (46.7% but only 15
reads, where one tag swings the figure by seven points).

**The threshold is a judgement pinned here, not a derived quantity**, and it is
in mild tension with the instrument: the module docstring says `rate` "ranks
poorly across rows", so comparing rows on it is exactly what the tool cautions
about. The defence is that the comparison is used to *widen* a selection rather
than to order one, and that the `reads` floor removes the small-denominator rows
the caution is really about. A reader who finds the threshold selecting noise
should change it and say so, rather than treat it as measured.

This settles BK-330's [Rule 6](../DRIFT-RULES.md#tolerated) register entry: the
report is tolerated because it now has a named consumer. The register's **owner
is the Phase 0 checklist step**, not this closed item — an owner has to be
answerable the next time the question is asked, and a closed item records only
that it was answered once.

### 4.2 Give `BACKLOG.md` the authority rule audits already have (BK-343)

An item's **diagnosis** is durable and is what the item is for. Any
**prescription** it carries — a fix shape, a disposition, a line reference, a
scope claim — is advisory and presumed stale by the time it is implemented.

This is a *new* authority direction for a *new* artifact pair (item body ↔
implementation), not a copy of the audits rule, which governs a different pair
(audit finding ↔ implementation).
[Rule 4](../DRIFT-RULES.md#authority) requires the direction to be declared in
the document that owns the pair, which is `BACKLOG.md`, and requires it not to be
restated elsewhere — so `BACKLOG.md` cites `CLAUDE.md` § Audits as the sibling
precedent rather than reproducing its wording.

**Measurable prediction.** Re-run the report after roughly 20 merged PRs.
`BACKLOG.md`'s negative tags per 100 reads should fall from 9.3, and the residue
should shift from wrong prescriptions toward wrong diagnoses, which is a rarer
and more expensive failure. If neither moves, the rule did not change behaviour
and should be reconsidered rather than defended — § 4.1's trigger is what causes
that re-measurement to actually happen. At the velocity measured in § 4.1,
20 merged PRs is about a week, so the check will usually fall inside a single
release interval rather than spanning several.

**Check this confound before believing either result.** The predicted figure is
`rate`, whose denominator is coverage-dependent: `reads` counts every citing
step, but only 43.1% of steps carry an explicit `outcome`, and that fraction
varies per reference. If tagging discipline on `BACKLOG.md` shifts over those 20
PRs — and shipping an authority rule *about backlog items* is exactly the kind of
change that shifts it — the ratio moves without the underlying failure rate
moving at all. So the re-measurement co-reports tag coverage, both globally and
for this reference, and a change in `rate` unaccompanied by stable coverage
falsifies nothing in either direction.

### 4.3 What this document does not claim

The comparison in § 2 is a reading of spec-kit's published templates and
methodology document, not of a project run with it. Claims about how its
mechanisms behave in practice are inferences from their prompts. That is
sufficient for the adopt/reject decisions in § 3.3, which turn on our evidence
rather than on theirs, and insufficient for any claim about how well spec-kit
works for its own users.

**"Presumed stale" is a default chosen from the failures, not from a base rate.**
§ 3.2 measures the prescriptions that *did* go wrong; it does not measure how
many prescriptions were still correct at implementation time, nor the interval
over which staleness sets in. So the evidence establishes that the failure is
common enough to be the top-ranked reference's dominant shape, and does not
establish that most prescriptions rot. A reader who thinks the default costs more
attention than it saves is disagreeing with an unmeasured quantity, not with the
data — and § 4.2's re-measurement is the cheaper test, since a rule that changes
nothing shows up there first.
