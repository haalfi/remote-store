# RFC-0024: A spec-first reset toward v1

## Status

Accepted, 2026-10-23, by the maintainer. Tracked as **BK-485**, § 9 steps 1
and 2 of [`research-spec-first-reset.md`](../research/research-spec-first-reset.md).
That research doc is the decision record for D1 to D11, with the options
each rejected; this RFC makes them binding process, records step 1, and answers
the research's open points 5, 9 and 10. Decisions taken in this RFC's own
session: decision log
`sdd/decisions/69e4bf99-0899-474b-bb47-606425c66a1a.jsonl`.

It changes no spec format. [`SPEC-DESIGN.md`](../SPEC-DESIGN.md) and
[ADR-0048](../adrs/0048-how-specs-are-designed.md) stay the authority for what
a spec states and the form it takes, with one bounded exception in § R4. The
format RFC (§ 9 step 6) amends them with the research's F1 to F6.

## Summary

**remote-store v1 is specified first, as what a caller can observe at the
Store boundary, and implemented only after.** The spec work runs on master,
which publishes nothing until v1 is implemented and ships it as one 1.0.0.
`release/0.33.x` carries fixes to the 0.33 line in the meantime. RFC-0017's
migration onto the kernel is paused from step 2 on, until D10 decides when
kernel and driver work resumes. A difference between a v1 spec and 0.33 is a
break record or a 0.33 defect, never a defect in the v1 spec.

## Motivation

The research's § 1 is the motivation: specs 001 to 050 mix what a caller
observes with how 0.33 achieves it, and RFC-0017's D3 steps build the kernel
against them. Recorded decisions bind no one until a process document carries
them. Three things that follow from them also had no answer:

- **What the pause does to the work queued behind D3.** Open items name a D3
  step as their due date or as their fix's home (§ R3 lists them).
- **How a break reaches a user.** D1 promises a break record and a migration
  note, and the research did not say what a break record is (open point 9).
- **What the authority rules say when a v1 spec disagrees with 0.33 code.**
  [`000-process.md` Rule 3](../000-process.md#rules) makes the code wrong,
  which for a spec designed ahead of its implementation would be true of
  every clause that changes behaviour.

## Proposal

### R1. D1 to D11 are binding

Each row is the binding rule; the decision, and the alternative it rejected, is
the research's [§ 2](../research/research-spec-first-reset.md#2-reset-decisions)
row of the same number.

| D | Binding rule | Carried out by |
|---|---|---|
| D1 | The v1 Store API is specified as consistent observable semantics. Behaviour may differ from 0.33; every difference is a break record (§ R5) before it is implemented and a migration-guide section when it is. | every flow; § R5 |
| D2 | Spec work runs on master. `release/0.33.x` takes patch-rated fixes only (§ R2). | § R2 |
| D3 | The spec phase's evidence is formal models, executable reference models with property tests, spikes and live probes. No production kernel or driver code is written in it (§ R2's freeze). | every flow |
| D4 | Each operation is designed in an unprimed session by the method of the research's [§ 4](../research/research-spec-first-reset.md#4-the-design-method-working-name-observe) (S1 to S5). | § 9 step 3 builds the tool |
| D5 | The `read()` slice is the first flow, end to end; key, error, lifecycle and consistency layers grow from what `read()` needs. | § 9 step 5 |
| D6 | A spec defines abstract axes. Beside it, one profile table per axis records Memory, Local, S3 and SFTP, each cell citing a dated probe or a vendor document. | every flow |
| D7 | A spec 001 to 050 gets a header marking it as 0.33 behaviour being superseded only when a new spec replaces sections of it. The new spec names each section it supersedes. A file left with no live section is deleted, and the ground register (D11) maps its old IDs to the new. | the flow that supersedes |
| D8 | After the decisions, a separate pass compares a flow's spec with 0.33. The conformance suite on `release/0.33.x` is the evidence of what 0.33 does, not master's, which carries changes made after the tag (§ R2); a difference becomes a break record or a 0.33 defect, and the pass never changes a decision. No test cell is removed until a new one replaces it. | step 4 of each flow |
| D9 | One 1.0.0 cut. Master publishes nothing until v1 is implemented; every release before it is a 0.33 patch from `release/0.33.x`. | § R2; [`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release) |
| D10 | **OPEN**, postponed by the maintainer: when kernel and driver work resumes. It is decided with the `read()` flow's evidence in hand ([research § 9](../research/research-spec-first-reset.md#9-results-and-recommendation), Not yet). Until then § R2's pause holds. | an RFC amending this one |
| D11 | One file, the ground register, lists every ground artifact, the flow that admitted it and its status (`active` or `reopened`). The design tool's hook reads its allowlist from it. | § 9 step 3 creates it |

**The flow and the ground** are as the research's
[§ 3](../research/research-spec-first-reset.md#3-the-flow-and-the-ground)
states them, and bind as stated there: design, record, spec, compare; the ground
grows only from the new layer; 0.33's code, tests and specs 001 to 050 are
never ground; a reopen is recorded and runs its own flow, and nothing changes
ground on the side. At the start the ground holds prior art and spec 051 with
its formal models. Two key artifacts are not ground: PR #1173's key model,
until the key spec is accepted (open point 8), and spec 054 of open PR #1171,
which was designed against spec 004 and probes of 0.33 backends. § 9 step 4
decides whether it is input to the key spec.

### R2. Step 1: the 0.33 line and the pause

**The branch.** `release/0.33.x` was created on 2026-10-23 at the v0.33.0
tag's commit `a51ac1b` and pushed with no commits of its own. It admits what
[`CONTRIBUTING.md` § When to bump](../../CONTRIBUTING.md#when-to-bump) rates
patch or no bump: bug fixes, patch-eligible floor raises, CI, docs and
metadata. A change rated minor is refused there.

**Master first.** A 0.33 fix merges to master and is cherry-picked to the
branch, so that it ships in 1.0.0 as well; merging it forward from the branch
would meet a master that has diverged since the tag. **The branch's suite, not
master's, is the 0.33 record D8 reads:** master's carries the changes made after
v0.33.0, the breaks among them listed in the migration guide's
`## v0.33.0 to v1.0.0` section, and runs Memory on the kernel. Where
the fixed code exists only on one line, the fix is ported rather than
cherry-picked: Memory's code is hand-written at the tag and on the kernel on
master. A fix that would break a caller, which the bump table rates minor,
lands on master only if a clause of a spec 001 to 050 already states the fixed
behaviour, so the code is wrong under Rule 3. Otherwise the fix decides
behaviour no clause states, and it goes to that operation's flow (§ R3, class
F).

**The pause (open point 5).** [RFC-0017 D3](rfc-0017-contract-kernel-over-thin-drivers.md#d3-migration-one-step-at-a-time-with-the-suite-as-oracle)
steps 2 to 8 are paused, the retirements inside steps 2 and 4 with them, and
so is D8 step 4's re-audit, which runs after the last step. `MemoryBackend` and
`AsyncMemoryBackend` stay on the kernel. No further class moves onto it until
the specs for what it implements exist and D10 is decided.
[ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md)'s decisions are
neither withdrawn nor amended: the pause changes when they are carried out,
which D3 owns. D10 decides whether they stand.

**The freeze.** During the pause the kernel and both Memory drivers change for
two reasons only: to keep the gates green, and to fix a defect that a released
0.33 version also has. Nothing is added to them. A defect found only in
kernel-era code is recorded and parked with the work it belongs to.

**Not done by the cut.** The branch carries v0.33.0's `ci.yml` and
`ci-full.yml`, whose `on:` blocks name master only, so a pull request into it
runs no CI until the first one into it adds the branch to both. Neither branch
protection nor a patch release's checklist for the branch exists yet (Open
Questions). No 0.33 patch is released before all three exist.

### R3. Open backlog items (open point 10)

**Every open item falls in one class.** Items do not move to the branch: the
backlog is master's, and a fix reaches the branch as its fix PR's cherry-pick or
port (§ R2).

| Class | What it holds | Disposition |
|---|---|---|
| K | A defect in 0.33: code against its own spec or docs | Stays open. Fixed master first; patch-rated fixes reach the branch. |
| P | Kernel, driver, `Session` or migration work: due at a D3 step, or building toward one | Stays in its section; its entry reads "paused (RFC-0024)". Resumes when D10 is decided. |
| F | An open decision about what a caller observes, which no clause of a spec 001 to 050 decides | Re-scoped: decided in its operation's flow, its options as candidate input, as research § 7 holds `read()`'s. |
| S | Rework of a spec 001 to 050 for its own sake | Paused (D7). A K fix still amends the clause it fixes. |
| U | Process, tooling, CI, docs and extensions that do not depend on 0.33's behaviour | Unchanged. |

**The items this RFC disposes of** are those whose index entry or dossier names
an RFC-0017 D3 step, a kernel migration or a spec 001 to 050 rework. They were found by
`hatch run backlog-find "D3 placement|D3 step|step [2-8]" --dossiers --max 80`
and a Grep of `sdd/BACKLOG.md` for `kernel|D3|driver|Session`, at `74538f0`,
and clustered in the trace (`sdd/traces/bk-485-reset-rfc.yml`, `orient:`), which
carries the evidence per cluster. The other open items were not classified one
by one; whoever works one classifies it by the table above first.

| Item | Class | What changes |
|---|---|---|
| BUG-341 | K | New: BK-450's T1 split out. Measured on v0.33.0 and on master: a returned `FileInfo.metadata` is the stored dict, and `copy` shares one dict between source and destination. |
| BK-450 | P | Paused; T1 leaves it as BUG-341. |
| BK-455, BK-452, BK-439, BK-446, BK-345, BK-390 | P | Paused, each with the D3 step it was due at. |
| ID-244 | U | Kept: a 0.33 conformance gap. Its consumer BK-345 is paused. |
| BK-434, BK-382, BK-242 | P, U, U | Index unchanged: no entry names a D3 step. Their dossiers' D3 placements are advisory and lapse with the pause. BK-382 and BK-242 bind 0.33 classes and stay open as such. |
| BK-451 | F | Re-scoped: `glob`'s defining clause and dialect are decided in `glob`'s flow. |
| BK-438 | F | Re-scoped: how a foreign flat key such as `a/` appears to a caller is a profile-table question of the listing flows (D6). |
| BK-454 | F | Re-scoped: its read handle is candidate R-2 of `read()`'s flow. |
| BUG-319, BUG-334, BUG-299, BUG-300, BUG-245 | K | Their "or at D3 step N" alternative is paused; each is decided as a 0.33 fix. |
| BUG-318, BUG-266, BUG-287, BUG-288, BUG-289 | K | Index unchanged. Each dossier places it at a D3 step; that placement lapses, and the item is worked as a 0.33 fix. |
| ID-140, ID-181 | P | Index unchanged. Each dossier places it as an option of a driver (steps 3 and 6), so it waits with that driver. |
| BK-456 | S | Stage three, the prune of spec 003, is paused; the two shipped stages stand. |
| BK-465, BK-466 | U | Kept: `SPEC-DESIGN.md` defects, the format RFC's to weigh. |
| BK-484 | U | Kept as § 9 step 4. |

### R4. How a v1 spec relates to 0.33 code and to `SPEC-DESIGN.md`

**A spec in the ground binds code only once the flow implementing it begins.**
Until then, a difference between it and 0.33 is a break record or a 0.33
defect (D8), not a defect in either the code or the spec. **A ground clause
that a binding spec incorporates by reference binds through that reference**,
as far as that spec binds: spec 053's BE-032 states the store tree as spec
051's TREE clauses, so a kernel or Memory answer contradicting one of them is
a K defect. Both sentences are added to
[`000-process.md` Rule 3](../000-process.md#rules). Rule 5's "not
removed" gains D7's one exception: a file D7 deletes maps its IDs to their
successors in the ground register. No ID changes meaning.

**`SPEC-DESIGN.md` binds every v1 spec, with one exception.** The `read()`
slice, § 9 step 5, is written in the provisional F1 to F6 form as the format
experiment that step 6 measures. The `read()` spec names, in its Notes, each
`SPEC-DESIGN.md` rule its form departs from. The format RFC then adopts the form
or the slice is rewritten. No other spec takes the provisional form before
that RFC.

### R5. Break records (open point 9)

**One register, `sdd/v1-breaks.md`, holds every break that is decided and not
yet implemented; the first comparison pass creates it.** An implemented break's
record is the migration guide's `## v0.33.0 to v1.0.0` section, which already
holds the breaks master made after v0.33.0 and takes a breaking K fix (§ R2)
directly. A row per break:

| Field | Holds |
|---|---|
| ID | `BRK-NNN`, numbered in order and never reused |
| v1 clause | the section ID of the v1 spec that differs |
| 0.33 behaviour | what 0.33 does, with its evidence: a conformance test's node ID or a spec 001 to 050 section ID |
| Caller | who is affected and what they change |
| Status | `decided`, `implemented` or `withdrawn` |
| Guide | once implemented, the migration-guide anchor of its section |

D8's pass adds a row for each difference that is not a 0.33 defect; one that is
a 0.33 defect becomes a K item instead. **A break reaches the migration guide
when it becomes real, not when it is decided:** the PR that implements it
writes its subsection under `## v0.33.0 to v1.0.0` and its `**Breaking**`
CHANGELOG entry under the existing rule
([`CONTRIBUTING.md` § Release](../../CONTRIBUTING.md#release), Phase 1, the
migration-guide line), and sets the row's Status and Guide. The guide is
published from master on every push (`docs.yml` `deploy-dev`), so a break
written into it before its code would describe behaviour no version has.
Before the 1.0.0 cut, every row is `implemented` or `withdrawn`, and the guide's
section is then the whole list of breaks the cut ships.

## Alternatives Considered

The alternatives to D1 to D11 are the research's § 2 rows. Those of this
session, all decided in the log above:

- **Scope:** an RFC that edits only BK-485, leaving every D3 item's due date
  contradicting the pause until a later sweep; or a sweep of every open item,
  for a much larger PR whose U-class edits change nothing.
- **Fix flow:** fixes on the branch first and merged forward into a master
  that has diverged since the tag; or a fixable kernel during the pause, which
  is the production kernel code D3 rules out.
- **The 0.33 record (fix pass, PR #1177):** the v0.33.0 tag's suite, from which
  every patch fix must be subtracted by hand; or master's suite less the
  migration guide's deltas, which list caller-visible breaks rather than every
  changed cell.
- **Spec 051 under Rule 3 (fix pass):** exempted by name, which leaves the next
  ground spec an old spec cites undecided.
- **A 0.33 defect also in the kernel:** fixed on the branch only, against the
  master-first rule; or fixed nowhere, so the 0.33 line ships it.
- **Fixes only:** bug and security fixes alone, freezing the 0.33 line's
  support matrix at v0.33.0; or support additions rated minor shipped as
  patches, which bends semver.
- **Status:** Proposed, with acceptance and RFC-0017's note in a later PR; or an
  ADR beside this RFC for D1, D7, D8 and D9. The pause amends RFC-0017's D3,
  which ADR-0042 left to the RFC as process, so no ADR is amended.
- **Break records:** each flow's research doc lists its own breaks and the
  guide is written from all of them at the cut, which leaves no list of
  decided breaks to check the cut against; or the guide grows as breaks are
  decided, publishing behaviour no version has. In the fix pass: a register of
  every break, backfilled with master's existing ones, which would give an
  implemented break two homes.
- **Authority:** amending CLAUDE.md principle 5 as well, at a recorded
  process-budget raise; or leaving Rule 3 for step 3, so that until then this
  RFC and Rule 3 disagree on paper.
- **PR #1171:** merged first, so that the key spec refines spec 054 and
  brings 0.33-grounded clauses into the ground against S1; or left
  unmentioned until step 4.

## Impact

- **Public API:** none. Master's next release is 1.0.0, so the migration
  guide's section for master's unreleased breaks is `## v0.33.0 to v1.0.0`,
  renamed from `v0.33.0 to v0.34.0` with its two CHANGELOG links.
- **Backwards compatibility:** the 0.33 line takes patch-rated fixes; every
  v1 break is recorded before it is built (§ R5).
- **Process:** `000-process.md` Rules 3 and 5 (§ R4); `CONTRIBUTING.md`
  § Release states D9 and the branch; RFC-0017's Status records the pause.
  Two agent-facing copies of Rule 3 keep its old wording, found by the
  ripple-check's command for an amended authority direction
  (`rg --no-ignore --hidden -e 'code is wrong' -e 'spec is source of truth'
  CLAUDE.md .claude/ sdd/`): `CLAUDE.md` principle 5 and
  `.claude/agents/store-backend-expert.md`'s CONSTRAINTS. Both are left as they
  are to spare a process-budget raise. They are wrong only for a ground clause no
  binding spec incorporates, and today spec 051 is the only ground spec.
- **Testing:** none now. D8 keeps every conformance cell until a v1 cell
  replaces it.

## Open Questions

1. **D10**, open by the maintainer's choice (§ R1).
2. **The 0.33 line's machinery:** the branch's CI triggers, its protection,
   and a patch-release checklist that says how a cherry-picked fix's CHANGELOG
   and `BACKLOG-DONE.md` lines land on both lines. Due before the first 0.33
   patch release; BK-485 tracks it.
3. The research's open points 2, 3, 4, 6, 7, 8 and 11 stay with the steps
   that meet them: 6 and 7 with step 3, 8 with step 4, 2 and 4 with step 5, 3
   and 11 with step 6.

## References

- [`research-spec-first-reset.md`](../research/research-spec-first-reset.md),
  the decision record.
- [RFC-0017](rfc-0017-contract-kernel-over-thin-drivers.md) and
  [ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md): the kernel
  design whose D3 is paused.
- [RFC-0022](rfc-0022-how-specs-are-designed.md),
  [ADR-0048](../adrs/0048-how-specs-are-designed.md) and
  [`SPEC-DESIGN.md`](../SPEC-DESIGN.md): how specs are designed today.
- [Audit 023](../audits/audit-023-kernel-migration-readiness.md) T1, re-measured
  for BUG-341.
