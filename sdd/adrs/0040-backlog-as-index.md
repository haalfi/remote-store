# ADR-0040: `BACKLOG.md` Is an Index, and Item Detail Lives in Dossiers

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Graduates [RFC-0016](../rfcs/rfc-0016-backlog-as-index.md) (BK-365). No earlier
record decides the backlog's structure: every ADR's `Supersedes` and `Amends`
rows are `—` or name an ADR on another subject, and a search of `sdd/adrs/` for
`BACKLOG`, `Icebox` and `Closes when` finds only citations of individual items.
So this record amends nothing. It departs from a *research* recommendation
(§ 9.1 below), which is not a decision record and has no amendment field.

## Context

`sdd/BACKLOG.md` is read by every session that picks, files or closes work, and
it no longer fits one default `Read`: at `e5fb4a8` it was 3,013 lines and
~51k tokens, 82% of it item bodies written as evidence dossiers
(`python sdd/rfcs/rfc-0016-measure.py --at e5fb4a8`). The three kinds of content
that share the file are in the RFC's § Motivation. Re-run the script without
`--at` rather than quoting these figures: the file changes on every merge.

Two structural causes, both from the RFC. The file's placement rules were
review-enforced, so each shipped with its full argument attached and nothing
stopped an item body growing after filing. And section preambles narrated
closures (`Closes when`) while omitting open items, so they were neither a
closing condition nor a list.

## Decision

- **`BACKLOG.md` is an index.** An item is at most eight content lines: header,
  attribute line, a diagnosis of at most five lines (the observed problem and
  the open decision), and an optional `Detail:` link. *Reverse if* the index
  stops fitting one read at the size the caps predict.
- **Detail lives in a per-item dossier**, `sdd/backlog/<id>-<slug>.md`, whose
  path never moves. Migration **moves** a body into it verbatim and writes a new
  diagnosis; it never cuts, so no rationale is lost to the cap.
- **The index governs the diagnosis**; the dossier holds evidence (a dated
  record) and prescription (advisory, presumed stale). The authority table lives
  in [`BACKLOG.md` § Item authority](../BACKLOG.md#how-this-file-works), which
  owns the pair ([`DRIFT-RULES.md` Rule 4](../DRIFT-RULES.md#rules)).
- **A section is a heading and a Promise of at most three sentences.**
  `Closes when` is removed; a section with no items is removed or re-argued.
  `## Release Blockers` is the one standing section, filed by prefix.
- **Gates hold the shape**, in `gen_backlogid.py --check`: R1 attribute
  vocabulary, R2 the item cap, R3 section shape, R4 dossier link. R1 lands with
  the mapping of the values it rejects; R2 and R3 land with the § 1 pilot,
  **scoped to migrated sections**, so no gate runs red on an unconverted one.
- **R2 and R3 depart from research
  [§ 9.1](../research/research-appropriate-level-of-detail.md)**, which advises
  no length rule beside Rule 7; a line or sentence count is the text-level
  instrument its § 1 rules out, and this record does not dispute that. The
  departure rests on what the research does not measure: this file's reader is a
  bounded-context session loading it on every pick, file or close. **Two
  bounds:** no other `sdd/` document, and overflow moves rather than being cut.
  *Reverse if* the acceptance re-measurement shows the caps pushing load-bearing
  diagnosis out of the index; a superseding record states that evidence.

## Why the rules are what they are

Moved from `BACKLOG.md` § How this file works, which now states each rule
without its argument. Each reason moved; none was paraphrased away.

**Sections are promises, not topics.** Each section states one outcome. Its
items are mutually reinforcing: shipping half a section under-delivers its
promise, which is why they sit together rather than under the subsystem they
happen to touch. Topic groups decayed because nothing stopped unearned items
accumulating, and conventions without a mechanism decay the same way; that is
why the placement rules' lack of a gate is stated plainly in the header rather
than left implicit, and why ID-235 hosts whatever part of them becomes
checkable. No [`DRIFT-RULES.md`](../DRIFT-RULES.md#rules) obligation attaches to
an authoring convention with no mechanism: that file scopes itself to changes
that add a check, a drift report, a second description, or a period.

**No holding area.** The previous Icebox was a slow deletion that charged review
attention on every pass. Of its eight items, seven were removed and one (ID-125)
was re-argued against a promise and kept, so abolishing it was a re-decision of
each item rather than a bulk delete. The `ID-` prefix meant "idea — not
evaluated" while the Icebox held unevaluated ideas; the admission test replaced
it, so `ID-` now means evaluated enough to earn a section, with the decision
still open.

**Release Blockers is filed by prefix.** A blocker is urgent by prefix, not by
outcome, so it is filed there regardless of which promise it touches. Under the
index it gains a one-line Promise stating that rule as an outcome, the release
gate itself; being the one standing section, empty is its normal state rather
than a reason to remove it, and R3 needs no exemption for it.

**A refused idea is recorded, not dropped.** The argument was had, so throwing
it away means having it again. That is also why a § Decided against entry
carries the diagnosis and not only the verdict: a verdict without it cannot be
re-decided without redoing the investigation.

**Ordering between sections is how directly the promise is felt**, which is not
an audience split and is not claimed to be: sections 3 and 4 both pay users, and
section 5 holds items tagged `user.*`. Read the promise, not the ordinal. A
cross-section dependency is stated inside the item that has it because nothing
about position will show it; the second copy the old rule required, in the
depending section's `Closes when`, goes with that field.

**Granularity has two tests because either alone misfiles.** Surfaces that
merely overlap stay separate with the co-ship recorded in the trace (BUG-249 and
BUG-246). The decision test is why ID-218 sits inside ID-217 and ID-123 inside
ID-121: those pairs touch disjoint paths and would be misfiled on the surface
test alone. An item may still designate future work that will need its own ID,
as ID-199 and ID-140 do.

**Item authority mirrors [`CLAUDE.md` § Audits](../../CLAUDE.md#audits) rule 3**
for a different pair: item body against implementation rather than audit
finding against implementation. That rule is not restated and does not govern
this pair. An item whose prescription survived unchecked is not evidence the
prescription was right. Measured failure modes:
[research § 3.2](../research/research-spec-kit-comparison.md).

**Register entries take the header shape** because `gen_backlogid.py` counts
headers and silently ignores anything else, so a well-meant prose line frees the
number for reuse. The header regex lives in the script; the rules header links
it rather than quoting it, because the quote had already drifted from the code.

**The retirement sweep is unbounded and reviewer-enforced**, stated as a bound
rather than pretended away ([`DRIFT-RULES.md` Rule 7](../DRIFT-RULES.md#miss-rate)).
Every hit is read, not only those that fail to resolve: the defect is an
assertion going stale, not a reference breaking, so a dangling-link check cannot
find it. BK-346 instance 6 measures the miss rate for exactly this task. Some
sites name no ID and no grep reaches them (`sdd/specs/004-path-model.md`
forward-pointed to a follow-up in prose), so budget a read of the specs the item
touched. **What to fix is decided by tense, not by directory**: a present-tense
claim that something is tracked is fixed wherever it lives, including an
`Owner:` field in `sdd/research/**`; past-tense narration is left, since a
recommendation a research doc made then is not a claim about now and
`000-process.md` § Document types forbids rewriting it. Accepted ADRs are never
edited either way ([`000-process.md` Rule 4](../000-process.md#rules)); the
register entry is what makes their citation resolve. Absorption retires an ID
too, so it falsifies the same class of sentence: in the restructure that
produced the promise sections it required repairs to two `BACKLOG-DONE.md`
entries and to `sdd/specs/044-graph-backend.md`.

**Retired IDs are not listed in the rules**, deliberately: a hand-maintained
"never reassign" list is the parallel artifact
[`DRIFT-RULES.md` Rule 3](../DRIFT-RULES.md#claim-space) says not to build. That
restructure retired twenty-three IDs, fourteen removed and nine absorbed, and
each class has a `BACKLOG-DONE.md` header so the generator counts it.
Registering absorbed IDs is not bookkeeping: a sub-bullet is not separately
tracked, so without an entry their citations elsewhere in `sdd/` would resolve
nowhere, including one inside an Accepted ADR that cannot be edited to point
elsewhere. The absorbed marker keeps its literal form
`(was PREFIX-NNN, absorbed here)` because a variant spelling is invisible to
`rg '\(was [A-Z]+-[0-9]+, absorbed here\)'` and to any check built on it.

## Section Promises

Why each section's Promise says what it says, moved out of the section
preambles verbatim except where "the Promise above" had to name its section.
A section with nothing here had no Promise rationale in its preamble; its
preamble argued `Closes when` clauses, which leave with that field at migration.

### Release Blockers

See *Release Blockers is filed by prefix* above.

### 1. Failures are predictable

BK-359 is why § 1's Promise carries a third clause, added with it rather than
left implicit: an error that is the right *type* on every backend but says
nothing is predictable to a checker and not to the person reading their log,
and this section is where that reader is served.

### 2. Answers are correct, and the contract is proven

A corrected clause nobody tests is the same defect one layer up, which is why
the wrong-answer defects and the coverage holes are one promise.

### 3. Users succeed without asking us

This is the group that converts directly into support load not arriving. The
rehearsal sits with the guides because it is the only mechanism that has ever
found their defects, and BK-327 sits here rather than with the gates because a
page nobody can navigate to is a page nobody reads — the gate is the mechanism,
not the payoff.

### 4. Users stop working around us

Each item here is something a user currently works around or eats. They are
grouped because the decision in each is the same: build it, or say plainly and
permanently that we will not — which is why "declined, recorded" closes an item
here as legitimately as "built".

### 5. A release cannot ship a surprise

Nothing moved: the preamble argues its `Closes when` clauses only.

### 6. The repo does not mislead the next person

The argument and gap ranking behind the programme:
[research](../research/research-inconsistency-detection-multi-artifact.md) § 9.

## Consequences

- **Positive:** the file a session loads on every pick fits one read once the
  migration completes, and what the implementer alone needs sits in the one
  file that implementer opens.
- **Positive:** the shape is gated rather than review-enforced, so growth after
  filing fails a check instead of accumulating.
- **Negative:** detail is one link further away. A reader who needs the evidence
  opens a second file; the diagnosis line has to be good enough to decide
  whether to.
- **Negative:** two length rules exist where the research advised none. They are
  bounded to this file, and the reversal condition above is the check on them.
- **Neutral:** until the migration completes, migrated and unmigrated sections
  coexist; the rules header says which shape applies where. `BACKLOG-DONE.md`
  is out of scope and stays open under BK-365.
