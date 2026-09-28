# ID-245 — Derived inventories replacing hand-maintained ones
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Four generated surfaces — three of them sharing one design decision, the
fourth independent — and the same
[`DRIFT-RULES.md`](../DRIFT-RULES.md#rules) obligations on each: Rule 3 (the claim
space must be *derived*, and its granularity stated), Rule 4 (which of document
and generator governs), Rule 5 (gating or advisory, and why).
- **Spec 003's cassette-reachability table.**
  [`003-backend-adapter-contract.md`](../specs/003-backend-adapter-contract.md)
  BE-029's coverage note tabulates, per backend, which root-path conformance
  cells execute and which are pinned only in a per-backend home. Every figure
  was counted by hand, against a corpus that grows, and ID-241 has already
  rewritten it once for that reason. This is the direct instance of
  [principle 9](../../CLAUDE.md#principles) on a published spec. Fix shape: a
  script that runs the conformance suite (or its collection plus the replay
  guard's verdict) and emits, per replay fixture, which cells execute and which
  skip for want of a cassette; spec 003 then cites the generator. Not derivable
  from collection alone — whether a cell needs a cassette depends on whether
  the backend issues a request, which only running it answers (ID-241).
  **Position: after ID-244**, which changes which cells a read-only backend can
  reach, so building this first would measure a surface about to move.
- **The characteristic-accountability record** (was ID-236, absorbed here),
  research § 9 step 7.
  `check_formal_trace.py` computes a spec-coverage matrix and discards it.
  Render it at release time — every spec ID, its verification evidence (test
  marker, Dafny tag, TLA+ invariant), its status — so "what was verified, and
  by what" is answerable historically rather than only at HEAD. Its shape
  changes under ID-207, so cost is unknown until that lands.
- [x] **The cross-artifact checker inventory** (was ID-237, absorbed here),
  research § 9 step 8. **Shipped.** [`GATE-INVENTORY.md`](../GATE-INVENTORY.md),
  derived by `scripts/gen_gate_inventory.py` and gating via `--check` in both
  `lint` and `docs-gate` (two homes because CODE_PAT skips `lint` for an
  `sdd/`-only edit, which is exactly an edit to the generated file). Both
  named complications were answered as scoped: single-artifact rule checks
  carry `kind: rule` and render in their own section, alongside a third
  `kind: report` for the mechanisms that measure rather than assert; read the
  per-kind split off that file's section headings rather than from here, since
  it moves whenever a mechanism is declared. The claim space is the wiring in
  `pyproject.toml`, `.pre-commit-config.yaml`
  plus `.github/workflows/` rather than a glob, which is what reaches
  `scripts/docs/check_links.py`. Research § 4b's eleven-row table is annotated
  as a dated measurement naming the generated file as its successor. Two
  bounds worth carrying forward: a mechanism that is not a script invocation
  is out of range (the conformance suite, § 4b's one row with no successor
  entry), and the declarations' *content* is unverified — a gate rewritten to
  compare something else, with its block left alone, renders a truthful-looking
  wrong row. The full bound list is the generated file's last section.
  **One measured lesson worth carrying to the remaining bullets**, since they
  build the same shape: across six review passes the *code* converged after two
  (the last four execution-based passes found no bug between them), while the
  *narrative* around it — the generator's docstring, this entry, the research
  annotation, the trace — kept producing defects at roughly the rate the fix
  passes edited it. Every recurrence was a sentence describing code that a later
  commit changed. Two remedies worked and are worth reusing rather than
  rediscovering: name a thing once in code and render it (`_WIRING_SOURCES`,
  `_BOUNDS`), and point at the derived artifact for any figure that moves rather
  than restating it. One did not: correcting the prose in place, which is what
  the first four passes did.
- **BE-021's divergence counts, and the artifacts that re-count against them.**
  The absent-container divergence set is stated as a bullet list in BE-021, as
  a class count in `sdd/BACKLOG.md` § 1, and again in the CHANGELOG, spec 040
  and BUG-254's register entry — in **four incompatible frames**: bullets, backend classes,
  operations, and helper call sites. Nothing derives any of them, and each
  frame is explained in prose that is itself a claim that can go stale.
  Measured cost: BUG-246 ran four numbered review rounds plus the closing
  gates, and **11 of its round-4 findings were figures or scope sentences in
  this set**, including one fixed by appending the right number beside the
  wrong one and one corrected in the same commit that falsified it by adding an
  item to the section being counted. Each fix pass added figures and produced a
  fresh defect, and the closing audit found three more after round 4 had
  declared the set clean: a `ping()` divergence titled "two backends" over a
  table naming three, a root-breach cell count stated as six in two artifacts
  where expanding the grouped rows gives seven, and a truncation item saying
  "all three" of a set the same item had just reduced to two. Fix shape: one
  authoritative divergence table that the other artifacts link to rather than
  re-count against, and delete the meta-prose explaining which frame each
  sentence uses — that prose was two of the eleven findings on its own.
  **Position: independent of the other three**, and the only one of the four
  with a measured defect rate behind it.
  **Four qualifications from the session that closed BUG-246**, each amending
  the fix shape above rather than restating it:
  1. **The four frames are four different questions, so one flat table serves
     none of them.** Bullets answer how many divergence entries exist; classes,
     how many backends disagree; operations, how wide the breach is on one
     backend; call sites, how much code implements the rule. The shape that
     works is one row per (backend × operation) carrying the clause it
     breaches, with every count derived by filtering it — never a second table.
  2. **"Delete the meta-prose" is too blunt, and following it literally will
     create a defect.** BE-021 counts move/copy as one operation in the roster
     paragraph and as two in the SQLBlob divergence bullet, seventy lines
     apart; the sentence saying so is the only thing stopping a future reader
     "fixing" fourteen or twelve to match the other. Delete prose that explains
     which frame a sentence uses; keep prose that explains why two frames
     legitimately differ.
  3. **A generator cannot produce the whole table.** "Pre-existing", "outside
     the clause until BUG-246 wrote the bound", "the error type actively
     misleads" are judgements. Realistic shape: generated columns for what each
     backend answers, curated annotations for why — which means
     [`DRIFT-RULES.md` Rule 4](../DRIFT-RULES.md#authority) is answered **per
     column, not per table**. Bullet 3 shipped that pattern; its per-column
     authority table is the worked example. It also settles this bullet's
     [Rule 5](../DRIFT-RULES.md#mandatory-path) side: **advisory, not gating** —
     a gate over a table containing judgements produces false failures, where
     bullet 3 gates precisely because no column of it carries one.
  4. **The set changes when the clause changes, not only when code changes** —
     and this is the blocker. BUG-255 and BUG-257 entered § Known divergences
     with no behaviour changing at all: writing the first-page bound into
     § Reach enlarged what the clause governs. A generator keyed on backend
     behaviour alone would have missed both. The input is code-behaviour ×
     clause-text, and the clause-text half has no machine-readable form today.
  **The surface to re-point**, counted at `959814e` with a case-sensitive
  match on `absent container|absent-container`, one count per file, `sdd/` and
  docs prose only: `sdd/specs/003` 15, `sdd/BACKLOG.md` 15,
  `sdd/BACKLOG-DONE.md` 9, `sdd/specs/044` 5, `sdd/specs/040` 3,
  `sdd/specs/029` 2, `sdd/specs/026` 2, `sdd/adrs/0038` 2,
  `docs-src/guides/custom-backend-guide.md` 2, `CHANGELOG.md` 1. Traces and
  the `src/`/`tests/` hits are excluded as records and as the behaviour itself.
  Read the custom-backend guide first: it is the one artifact in that set that
  never drifted, so it shows what a correctly placed statement of this clause
  looks like.
**The shared question, now answered once by bullet 3:** a docstring
convention, not a curated mapping — a curated mapping is precisely the
parallel-artifact-that-drifts problem these exist to close. It shipped as the
`Drift-gate::` block that [`DRIFT-RULES.md` Rule 7](../DRIFT-RULES.md#miss-rate)
now requires of every wired mechanism. The two unbuilt inventory bullets
inherit that decision rather than re-make it. The fourth bullet never shared
it: its answer is one table rather than a better-maintained several, and what
it takes from bullet 3 instead is the per-column authority pattern, since the
convention governs generated columns only and its curated ones need their
authority stated per column.

## Re-measured, 2026-09-28

Bullet 3 holds as shipped: `python scripts/gen_gate_inventory.py --check`
reports the file up to date. The re-point surface has moved since `959814e`:
`rg -c -s 'absent container|absent-container'` gives spec 003 at 23 (was 15),
`sdd/BACKLOG.md` at 4 (was 15, most bodies now in dossiers) and
`BACKLOG-DONE.md` at 17 (was 9), and the § 1 class count the fourth bullet
names no longer exists in the index. Both dependencies stand: ID-244 is open
in § 2, and ID-207 is open above this item. Found by the ADR-0040 § 6 conversion.
