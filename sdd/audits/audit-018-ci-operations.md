# Audit 018 — CI Operations: scheduled-guard notification surfaces

**Backlog item:** — (ad-hoc operational audit prompted by the weekend mutation
failure; follow-ups proposed at the end)
**Date:** 2026-06-09
**Scope:** The nine workflows under `.github/workflows/` and `.github/dependabot.yml`,
viewed through one question: *when a scheduled or automated guard finds something,
how does a maintainer (human or agent) learn there is a TODO, and what tells them
how to action it?* Specifically the **scheduled-maintenance family** — `drift-guard`,
`mutation`, the weekly `codeql` sweep, and the two `dependabot` ecosystems — plus
the `dependabot-auto-merge` automation and the absence of a CI-operations handbook.
Out of scope: the internal correctness of `ci.yml`'s test matrix, coverage gates,
and the formal-verification lanes (those are gating, not maintenance).
**Method:** Read every workflow trigger and notification path; compared the one
guard that produces an actionable, deduplicated TODO (`drift-guard` → rolling
GitHub Issue → `/drift` skill) against the rest. Evidence is `file:line` in the
workflow sources, the two referenced PRs (#763 mutation impl failure, #767 failing
upper-pin, #766 rubber-stamped actions bump), and the `/drift` skill as the proven
pattern. This is a **report-only** audit — no workflow was modified. The proposed
backlog items at the end are advisory; the adversarial section challenges them.

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low / Nit.
Each finding tag (H1, M2, …) is referenced by the proposals table at the end.

---

## Summary

The repo has exactly one scheduled guard that does notification right —
`drift-guard` — and it does it so well that it doubles as the template for fixing
the others. It never fails its job; instead each matrix leg writes a structured
JSON status and a dedicated `report` job reconciles a **single rolling GitHub
Issue** (open/update on a finding, comment-and-close on clear), and a `/drift`
skill tells whoever picks it up exactly how to triage. The issue *is* the signal;
it is durable, deduplicated, and visible to anyone, not just the maintainer's
inbox.

Every other scheduled or automated guard leaks its result into a weaker channel:

1. **`mutation` (Sat 05:00) has no durable TODO surface at all** — it lets the job
   fail, so the only signals are a red X in the Actions tab and GitHub's default
   actor email. That is exactly how the weekend failure (#763, an *implementation*
   failure, not even a surviving mutant) reached the maintainer: email or nothing.
   No issue, no dedup, no triage skill. This is the headline gap (H1).

2. **Dependabot has the inverse problem** — the signal arrives (a PR, red or
   green), but there is no codified judgement for the human/agent who must act on
   it, and the act is *load-bearing*: `dependabot-auto-merge` fires the moment a
   maintainer approves, merging straight to `master` (M1). #766 (a github-actions
   bump) went green and was approved essentially on the green check; #767 (a pip
   dev-dep upper-pin) went red with no runbook for "real ceiling vs transient."

3. **There is no CI-operations handbook** (M2). The knowledge that *does* exist is
   excellent but covers a single guard (`/drift` + the `drift-guard.yml` header +
   `CONTRIBUTING § Dependency drift guard`). Nothing inventories what runs when,
   what TODO each produces, where that TODO appears, and which skill actions it —
   the one document a new contributor (or an agent on a cold start) would need.

The remaining findings are smaller surface inconsistencies (codeql's weekly sweep
reports only to the Security tab; the mutation `summary` job tabulates outcomes but
emits nothing actionable).

The through-line: **`drift-guard` proved that "scheduled finding → rolling issue →
triage skill" works. The fix for everything else is to make it the house style,
not a one-off.**

---

## 🔴 High

### H1 — `mutation.yml` produces no durable, actionable TODO; failures reach the maintainer only by email

**Files:** `.github/workflows/mutation.yml` (whole file); contrast
`.github/workflows/drift-guard.yml:218-247` (the `report` job) and
`scripts/drift_report.py:1-14` (the rolling-issue reconciler).

The difference is architectural, not a config slip:

- **`drift-guard` never lets its job fail on a finding.** Each `check-<extra>` leg
  writes a structured JSON status (`drift_check.py diff … --out`,
  `drift-guard.yml:132-137`) and *always* exits 0 on drift
  (`drift-guard.yml:123-125` comment). A separate `report` job
  (`drift-guard.yml:237-247`) runs `scripts/drift_report.py`, which reconciles a
  single rolling issue: create/update when any extra drifts, comment-"cleared"
  and close when all clear (`drift_report.py:8-14`). There is no red X to notice
  and no reliance on email — the issue is the durable, deduplicated signal.

- **`mutation` lets the job fail.** Its terminal steps write a
  `$GITHUB_STEP_SUMMARY` and upload HTML artifacts
  (`mutation.yml:153-186`), and the `summary` job
  (`mutation.yml:188-218`) tabulates `job.status` into the run summary
  (`mutation.yml:166`, `:201-216`). None of that is actionable after the run page
  scrolls away. On failure GitHub emits its default actor email and a red X in the
  Actions tab — and that is the *entire* notification surface.

**Consumer impact (the maintainer is the consumer here):** the weekend run
(#763) was an **implementation failure** — the mutation harness/run itself broke,
not a surviving mutant — and it surfaced only because GitHub mailed the actor.
Nobody opened an issue; there is no `/mutation` triage skill; and a missed or
filtered email means the failure is invisible until someone happens to scan the
Actions tab. A weekly guard whose only durable output is "a red X you might see"
is a guard you cannot rely on.

**Second failure mode the fix must model.** Unlike drift (one axis:
version-drifted vs not), mutation has **two** distinct outcomes a triage entry
must distinguish:

- a **surviving mutant** — a genuine test-coverage gap (the signal mutation
  testing exists to produce); versus
- a **harness/implementation failure** — the run itself broke (what #763 was).

`drift-guard` already models an analogous split (version-drift vs red-smoke; see
the `/drift` skill's step 3). A `[mutation]` rolling issue must carry the same
distinction or every triage starts by re-deriving "did we find a mutant, or did
the run die?"

---

## 🟠 Medium

### M1 — `dependabot-auto-merge` makes human approval the only gate, with no codified pre-approval checklist

**Files:** `.github/workflows/dependabot-auto-merge.yml:17-44`;
`.github/dependabot.yml:1-15`; evidence PRs #766 (github-actions), #767 (pip
dev-dep upper-pin).

The auto-merge workflow triggers on `pull_request_review` (`:19`) and, on a
maintainer `approved` review (`:33-38`), runs `gh pr merge --auto --squash
--delete-branch` (`:41`). By the workflow's own (well-written) header comment, this
is deliberate: *"the human review is the gate, so update-type filtering would be
redundant"* (`:1-4`). That makes the approval click the load-bearing safety
mechanism — and **nothing documents what to verify before clicking it**, per
ecosystem:

- **`Chore(deps)` (github-actions, weekly Monday — `dependabot.yml:10-15`):** an
  action bump usually exercises nothing in the test suite, so CI goes green
  regardless of whether the new pin is correct. #766 was approved essentially on
  the green check. There is no checklist saying *"green here means the workflow
  parsed, not that the action behaves — diff the action's changelog, confirm no
  permission/`with:` surface changed."*

- **`Chore(deps-dev)` (pip, weekly Monday — `dependabot.yml:3-8`):** #767
  introduced a failing **upper-pin bound**. CI red is a better signal, but there is
  no runbook distinguishing *"this ceiling is real, hold the PR / pin the floor"*
  from *"transient or unsupported, close it"* — exactly the per-target triage
  `/drift` provides for a red smoke.

The gate is a single human judgement with no written criteria, immediately
followed by an irreversible merge to `master`.

### M2 — No CI-operations handbook: the scheduled-maintenance picture lives only in one guard's docs

**Files (by absence):** there is no `sdd/`-level or `CONTRIBUTING`-level document
that inventories the scheduled/automated workflows. What exists is complete but
single-guard: the `/drift` skill (`.claude/skills/drift/SKILL.md`), the
`drift-guard.yml` header (`:1-17`), and `CONTRIBUTING § Dependency drift guard`
(`CONTRIBUTING.md:289-314`).

No document answers, for a contributor (human or agent on a cold start): *what
scheduled jobs run, on what cadence, what finding each can produce, where that
finding shows up (issue / PR / Security tab / email), and which skill actions it.*
That table is the skeleton of the missing handbook:

| Workflow | Trigger | Finding surface | Actionable TODO? | Runbook / skill |
|---|---|---|---|---|
| `ci.yml` | push / PR | red X + email | — (contributor present) | CONTRIBUTING |
| `codeql.yml` | push / PR **+ Mon 06:00** | Security tab alerts | partial (Security tab) | — |
| `drift-guard.yml` | **Mon 07:00** | **rolling Issue** | **yes** | **`/drift`** |
| `mutation.yml` | **Sat 05:00** | summary + email | **no** (H1) | none |
| dependabot pip / actions | **Mon** | PR (red/green) | partial (M1) | none |

The established three-layer pattern (skill + workflow header + CONTRIBUTING
section) works; the gap is that it was never generalised, so two guards and an
automation have no entry in any of the three layers.

---

## 🟡 Low / Nits

### L1 — `codeql`'s weekly sweep reports only to the Security tab, undocumented as a maintenance surface

**Files:** `.github/workflows/codeql.yml:11-22` (push/PR + `Mon 06:00` schedule).

The weekly full sweep (`:21-22`) exists precisely to catch what the path-filtered
PR runs miss, and its findings land as code-scanning alerts in the Security tab —
GitHub's canonical surface for this, and arguably fine as-is. But it is a *third*
notification channel (issue / PR / Security tab) that the missing handbook (M2)
should name, if only to record "this guard's TODO lives in the Security tab, by
design, and is reviewed when." Without that line, a contributor has no way to know
the weekly CodeQL sweep is even a maintenance obligation.

### L2 — `mutation`'s `summary` job computes a result table but cannot act on it

**Files:** `.github/workflows/mutation.yml:188-218`.

The `summary` job already downloads every per-scope outcome and renders a
`| Scope | Result |` table (`:201-216`), and that gives the H1 reconciler a job to
attach to. But be precise about what it aggregates: only `job.status`
(`mutation.yml:166`, `:201-216`) — success / failure / skipped, a **single axis**.
That axis cannot carry the two-outcome distinction H1 and C-DECISION require: a
*surviving mutant* and a *harness/impl failure* both collapse to `failure` (or, if
the runner exits 0 on a surviving mutant, both to `success`, in which case the
table cannot surface mutants at all). So the `[mutation]` issue reconciler must
**derive** that distinction from the per-scope reports / exit semantics, not merely
redirect the table this job already computes — closer to A5's "more code than it
looks" than to a pure redirect. Noted as a Low because it is an enabler/scoping
observation, not a defect on its own.

---

## Verified strengths (checked, not rubber-stamped)

These were actively examined and are genuinely well-built:

- **`drift-guard` is exemplary end-to-end.** Never-fail-the-job + structured JSON +
  rolling-issue reconciliation + single-writer concurrency guard
  (`drift-guard.yml:37-44`) + a triage skill that encodes the load-bearing rule
  (the per-extra smoke verdict, not the issue body, decides safety —
  `drift/SKILL.md:19-26`). It is the reference implementation this audit
  recommends copying.
- **`dependabot-auto-merge`'s security model is sound and well-commented.**
  Triggering on `pull_request_review` rather than `pull_request` (`:1-4`), the
  repo/state/actor guards (`:33-38`), and the token-model note (`:12-13`) are all
  deliberate and correct. The gap (M1) is the *absence of a human-side runbook*,
  not a flaw in the automation.
- **Both scheduled guards route user input through env vars, not template
  interpolation.** `mutation.yml:34-48` and `drift-guard.yml:56-81` both guard the
  `workflow_dispatch` input against shell/JSON breakout, and `drift-guard`
  additionally validates the extra against the known list before it reaches the
  matrix (`:70-79`). No injection surface in either dispatch path.
- **`drift-guard` degrades honestly.** A single extra's PyPI flake writes a
  synthetic `status:error` rather than failing the run (`:128-131`), and the
  smoke-install list is documented down to *why* each plugin is present so a
  skipped-everything (rc=0) smoke cannot masquerade as "clear" (`:166-173`).

---

## Proposed backlog items

Advisory groupings for the user to accept, split, or decline. Grouped by theme and
owning files. The adversarial section below challenges each before you commit.

| Group | Findings | Scope / files | Suggested disposition |
|-------|----------|---------------|-----------------------|
| **C1 — `mutation` → rolling `[mutation]` issue + `/mutation` triage skill** | **H1, L2** | `.github/workflows/mutation.yml` (redirect the `summary` job into a reconciler, modeled on `drift-guard`'s `report` job); a new `scripts/mutation_report.py` mirroring `drift_report.py`; a new `.claude/skills/mutation/SKILL.md` mirroring `/drift` | **High.** The body must distinguish **surviving mutant** (test-gap, advisory) from **harness/impl failure** (run broke, like #763). One design decision up front (see C-DECISION below). The `summary` job gives the reconciler a job to attach to, but it aggregates only `job.status` (L2), which cannot tell a surviving mutant from a harness failure — so the reconciler must derive that from the per-scope reports, not just redirect the table (closer to A5 than to "a redirect"). |
| **C2 — Dependabot pre-approval runbook + `/deps` triage skill** | **M1** | a new `.claude/skills/deps/SKILL.md`; a `CONTRIBUTING`/handbook section codifying the per-ecosystem pre-approval checklist; optionally a weekly "open dependabot PRs" digest issue | **Medium.** Because approval auto-merges to `master`, the checklist is a safety control, not a nicety: github-actions = "green ≠ behaves; diff changelog + `with:`/permissions surface"; pip dev = "red ⇒ real-ceiling-vs-transient triage." Decide whether to also add a digest issue or rely on the PR list. |
| **C3 — CI-operations handbook (authority doc) + the consistency principle** | **M2, L1** | one new authority doc (e.g. `sdd/CI-OPERATIONS.md` or a `CONTRIBUTING` section) holding the inventory table from M2; the per-task skills (`/drift`, `/mutation`, `/deps`) become thin pointers to it per the existing skill-overlay convention | **Medium.** States the house principle: *every scheduled-maintenance guard emits a durable GitHub Issue as its TODO and has a triage skill; email/red-X/green-check are insufficient alone.* Records codeql's Security-tab surface (L1) as a deliberate exception. This is the SSoT C1/C2 point at — sequence it to land alongside or just before them. |

**C-DECISION (resolve before C1 code).** `drift-guard` chose *never-red,
issue-is-the-only-signal*. Mutation should likely **diverge**: a **surviving
mutant → issue only (advisory, run stays green)**, but a **harness/impl failure →
issue AND a red run** (a broken weekly job is a real regression worth a red X *and*
a TODO). Drift's all-green model is not automatically right for a guard that can
itself break. Pick the model first; it shapes whether the `mutate` job swallows or
propagates its exit code.

**Priority ordering:** C3 (or at least its principle + inventory) → C1 (the
concrete, highest-value fix; closes the #763 class) → C2 (the auto-merge safety
runbook). C1 and C2 each point at C3, so a thin C3 first avoids forward
references.

---

## Adversarial proposals (challenging the above)

Per principle 7 — be critical, not agreeable. Each recommendation above is
pressure-tested here; some of these may be the better call.

**A1 — "Issues for everything" invites issue fatigue, and a stale handbook is
worse than none.** The recommendation generalises the rolling-issue pattern to
mutation and (optionally) dependabot. But an issue nobody triages is just email
with extra steps, and a hand-maintained inventory table (M2) goes stale the moment
a tenth workflow lands — the exact "hand-maintained lists go stale" trap this
project already legislates against (it auto-generates `FEATURES.md`, the graph
data, etc.). **Counter-proposal:** make C3's inventory *generated* — a
`scripts/check_ci_inventory.py` (or a mkdocs-gen-files page) that parses every
`.github/workflows/*.yml` for `on.schedule`/`on.pull_request_review` and fails if a
scheduled/automated workflow has no documented surface + skill. That turns the
handbook from prose-that-rots into a lint gate, matching the repo's automation
doctrine. If C3 ships as static prose, it should carry an explicit "review when a
workflow is added" obligation, like the `verify-tla` revisit ticket (ID-150).

**A2 — The real dependabot risk is auto-merge-on-approval, not the missing
runbook.** C2 documents how to approve safely, but leaves the gun loaded: one
mis-click on a green-but-wrong github-actions bump (#766's exact shape) merges to
`master` with no second gate. A runbook is advisory; a control is enforced.
**Counter-proposals, strongest first:** (a) drop auto-merge for the
`github-actions` ecosystem specifically — the bumps are low-volume and a manual
`gh pr merge` costs seconds, removing the rubber-stamp path entirely; (b) require
the github-actions PR to pass a job that actually exercises the bumped action
(harder — most do nothing testable); (c) keep auto-merge but gate it behind a
label the maintainer must add *in addition* to approving, making the irreversible
step deliberate. If any of these is adopted, C2 shrinks to "how to triage a red
pip dev-dep" — a much smaller item.

**A3 — Maybe mutation shouldn't produce a TODO at all.** C1 assumes mutation
findings are worth a durable, deduplicated obligation. But surviving mutants are
*advisory* — the project already runs strict coverage gates in CI; mutation is the
belt to coverage's suspenders. If surviving mutants are rarely actioned in
practice, the honest fix is to **stop pretending it's a TODO**: split the two
outcomes hard — *harness/impl failure → fail the run loudly* (the #763 case, which
genuinely needs attention) and *surviving mutants → a report artifact only, no
issue* (read when someone does a coverage-hardening pass). That is strictly less
machinery than C1's rolling issue and may match how the signal is actually used.
The deciding evidence is the base rate: across recent Saturday runs, how often is a
*surviving mutant* (not a harness break) actually acted on? If the answer is
"rarely," A3 beats C1.

**A4 — Three skills may be over-tooling a one-maintainer repo.** `/drift` earns its
keep because drift triage is genuinely multi-step (smoke-verdict reading, baseline
refresh, OS-specific lock resolution). `/mutation` and `/deps` triage may be
shallow enough to live as a handbook section with a checklist, not a skill —
skills carry maintenance cost (allowed-tools, fork-context env gotchas, drift from
the workflows they describe). **Counter-proposal:** ship C3's handbook with
inline checklists first; promote a checklist to a skill only once its triage proves
multi-step enough to need one (the same "promote to BK when it earns it" discipline
the backlog already uses for ID-179/ID-207). This inverts the sequence: doc first,
skills only on demand.

**A5 — Copying `drift-guard`'s machinery imports its complexity.** The rolling-issue
pattern needs a single-writer concurrency guard (`drift-guard.yml:37-44`) precisely
because a manual dispatch can race the schedule on `gh issue edit`/`close`. Cloning
it for mutation clones that subtlety too. If C1 proceeds, the `mutation_report.py` +
concurrency group must be lifted deliberately, not approximated — a half-copied
reconciler that last-writer-wins on the issue is worse than the current email. This
is not an argument against C1, but a warning that "model it on drift" is more code
than it looks.

**Net adversarial read:** C3 (the doc/principle) is robust and cheap — do it, but
**generate the inventory (A1)** rather than hand-maintain it. C1 is the
highest-value fix *if* surviving mutants are actually actioned (A3 is the test);
even if they are not, the **harness/impl-failure half of C1 is unconditionally
worth it** — #763 must never again surface by email alone. C2 should probably be
reframed as a **control** (A2: drop github-actions auto-merge) plus a much smaller
red-pip-dev triage note, and its skill deferred (A4).
