# Research: Trace-vs-PR Fidelity Analysis (BK-193)

**Date:** 2026-05-11
**Status:** Research complete; informed BK-193 schema additions and the
re-tagging of all 39 unreleased traces under `sdd/traces/`.
**Scope:** Empirical investigation of how the trace YAMLs introduced in
PR #608 compare to the work that actually shipped in the corresponding
merged PRs. The analysis was deliberately staged so each phase could
falsify the previous one's claims.

---

## 1. Intent & Scope

PR #608 added `sdd/traces/` to record the ordered files and sections an
agent reads while doing backlog work. The stated purpose is documentation
optimisation: identify hotspot files, gate-density rankings, and co-read
pairs, then refactor `sdd/` so the spine an agent must read shrinks.

Before optimising on the trace data, this research asked a more basic
question: does the data describe what agents actually did, or what trace
authors thought they should do? The two are not the same. Traces were
written as anticipated workflows, then committed alongside the items they
describe. The merged PR is the only ground truth for what work the item
required. If the gap is large, optimisation guided by trace data
optimises for the rule-following spine, not for the surface where real
work happens.

This doc is the frozen snapshot of that investigation. It is not a living
doc. Subsequent findings (e.g., expanding the sample beyond nine PRs)
belong in a new research doc; this one stands as written.

---

## 2. Method

Three phases, each blind to the next:

1. **Pure data analysis.** Treat the 39 trace YAMLs as opaque records.
   Compute distributions, phase sequences, file rank-frequency,
   co-occurrence clusters, read-type by phase. No repo knowledge.
2. **Cross-check with real docs.** Validate the data-only claims against
   the actual `sdd/` and `CLAUDE.md` content. Test which hypotheses hold.
3. **Trace-vs-PR cross-check.** For nine randomly-picked traces, fetch
   the merged PR (commits, file changes, review rounds, follow-up items)
   and compare against the trace's anticipated reads.

The point of staging was to keep early-phase intuitions from contaminating
later evidence. In particular Phase 3 needed to be willing to overturn
Phase 1 and 2's optimisation suggestions if the PRs told a different
story.

---

## 3. Phase 1 — Pure Data Findings

### 3.1 File rank-frequency

Across 39 traces and ~280 step references, file citation follows a strong
Zipf shape. Six files account for 60% of all reads:

| File | Citations | Role-by-data |
|---|---|---|
| `sdd/CLAUDE-REFERENCE.md` | 41 | verify hub |
| `sdd/000-process.md` | 28 | gate (rules, pipeline) |
| `sdd/TESTING.md` | 24 | gate (rules, placement) |
| `sdd/DESIGN.md` | 22 | reference (style) |
| `CHANGELOG.md` | 19 | verify (gate stub) |
| `CLAUDE.md` | 17 | gate (principles) |

The long tail (29 files cited 1–3 times) covers specs, ADRs, and
backend-specific source files.

### 3.2 Phase-vocabulary instability

Phase IDs are author-chosen; the schema enumerates none. The data shows
seven phases appearing in ≥ 25% of traces (orient, implement, verify,
tests, fix, spec, docs) and ten more appearing ≤ 2 times. Outliers like
`spec_review`, `reproduce`, `classify`, `wire` suggest authors reach for
new phase IDs when the standard set does not capture the work shape.

### 3.3 Read-type distribution by phase

- `orient` phase reads are 87% gate.
- `verify` phase reads are 100% verify.
- `implement` phase reads are 78% reference, 22% gate.

The `orient → middle → verify` envelope is stable. Authors treat the
middle phases as situation-dependent. Gates cluster at entry, verifies at
exit.

### 3.4 Section-string patterns

19% of section references use the "X / Y" form. All of these are
ripple-check table row pointers (e.g., `Ripple-check table / A bug fix`).
The convention is consistent. Outside the ripple-check table, "X / Y"
does not appear — meaning the table is a uniquely deep navigational
target that the schema's `section` field handles via a per-row dotted
path convention.

### 3.5 Jaccard co-occurrence clusters

Pairwise Jaccard similarity on the file sets reveals two arcs:

- **Doc-framework cluster** — BK-167 family, BK-171, BK-178, ID-177
  share `CLAUDE.md`, `sdd/AUTHORING.md`, `sdd/DOCUMENTATION.md`,
  `sdd/CONTENT-RULES.md`, `sdd/CLAUDE-REFERENCE.md`.
- **Async-Azure cluster** — BK-173, BK-174, BUG-189, BUG-190, BUG-192,
  BUG-193, BUG-194 share `sdd/specs/003-backend-adapter-contract.md`,
  `sdd/specs/029-async-store-backend-api.md`,
  `sdd/specs/045-write-result.md`, `sdd/specs/012-azure-backend.md`.

Suggests the spec lookups, not the source files, are the true cost
centre for backend-bug work.

---

## 4. Phase 2 — Cross-Check Against Real Docs

The data-only spine (`CLAUDE-REFERENCE`, `000-process`, `TESTING`,
`DESIGN`, `CHANGELOG`, `CLAUDE.md`) holds against the actual content:

- `CLAUDE-REFERENCE.md` carries the ripple-check table and is the most
  cross-cited file in the repo. Its central role is real, not an
  artefact of trace authoring.
- `000-process.md` § Rule 6 contains the canonical bug-fix pipeline
  (BACKLOG → CHANGELOG → failing TEST → FIX → COMMIT together). Traces
  cite this section verbatim 14 times.
- `TESTING.md` § Test Subpackage Placement and § Rules are the
  authoritative placement and quality references. Trace data treats
  them as gates, matching their authoritative role.

One Phase-1 claim partially failed under Phase-2 scrutiny: the
"doc-framework cluster" splits into two sub-clusters under closer
reading — pure-content edits (BK-178 RST roles) versus framework rollout
(BK-167 family). The Jaccard distance did not distinguish them because
both touch the same authority docs.

---

## 5. Phase 3 — Trace vs Merged PR (n=9)

Nine traces sampled across iteration-cost regimes — high (≥ 11 commits),
medium (4–8), low (1–2):

| Trace | PR | Trace steps | PR files | PR commits | Reviews | Fan-out\* | Pattern |
|---|---|---|---|---|---|---|---|
| BK-187 | #604 | 6 | 31 | 2 | 1 | 5.2× | tooling, CI ripple |
| BK-176 | #607 | 12 | 5 | 2 | 1 | 0.4× | clean fix |
| BK-178 | #591 | 5 | 18 | 8 | 2+ | 3.6× | RST + audit re-sweep |
| BK-179 | #597 | 11 | 70 | 22 | 4 | 6.4× | massive reorg |
| BUG-193 | #590 | 13 | 9 | 21 | 4 | 0.7× | discovery cascade |
| BK-189+190 | #606 | 17 | 32 | 11 | 4 | 1.9× | bundled scope |
| ID-176 | #579 | 4 | 4 | 11 | 2 | 1.0× | content churn |
| ID-178 | #592 | 18 | 19 | 1 | 1 | 1.1× | best-fit trace |
| BK-174 | #582 | 8 | 7 | 4 | 8 | 0.9× | docstring grew into code-fix |

\* Fan-out = PR files / trace-cited files. Median 1.2×, mean 3.2×.

### 5.1 Five patterns the trace schema could not model

**Trace verbosity does not predict iteration cost.** ID-178 had the
longest trace (18 steps) and merged in one commit. ID-176 had one of the
shortest traces and required eleven commits, all wordsmithing a
seventeen-line file. BK-179 (medium trace) needed 22 commits.

**Single-commit is not always simple.** ID-178 trace anticipated six
files; the PR touched nineteen — proxy wrapper, two extension files,
graph regen, an example, backlogid.json. The "A Store method"
ripple-check row covers these implicitly but no trace cited them
explicitly.

**Multi-commit is not always complex.** PR #579 (ID-176) touched four
files, +29 / −1 — a tiny diff over eleven commits of editorial pushback
(rewrites, schema validation fix, em-dash sweep). The schema has no
field for content-churn risk.

**Discovery cascades are unmodeled.** BUG-193 started as one bug and
surfaced BUG-194 (a real SDK bug), BUG-196, BUG-197, the BK-175
supersession of ID-175, TESTING.md rule violations in the new test file,
RST role cleanup, and stale mock tests broken by the chained fix. The
trace had thirteen careful steps; the PR had 21 commits and 4 review
rounds.

**Bundled scope inflates apparent coverage.** PR #606 was traced as two
items (BK-189, BK-190); it shipped three (BK-188 joined during
implementation). Trace aggregators would double-count shared file reads
without a `co_shipped_items` signal.

### 5.2 Systematic ripple omissions

Across nine PRs, these files were touched but cited by no trace:

| Ripple | Hits | Trigger |
|---|---|---|
| `sdd/backlogid.json` | 5/9 | mechanical on backlog moves |
| `.github/workflows/ci.yml` | 3/9 | pyproject lint scope or test layout changes |
| `docs-src/_data/graph/graph.json` | 2/9 | docstring or public-API changes |
| `docs-src/explanation/graph_viz.html` | 2/9 | same trigger as graph.json |
| `pyproject.toml` lint scope | 2/9 | tooling work |
| `src/remote_store/_proxy.py` | 1/9 | new Store method |
| `src/remote_store/ext/*.py` | 1/9 | new Store method |
| `examples/**` | 1/9 | public API change |
| Stale mock tests | 1/9 | SDK-level fix |

The three already documented as gotchas in memory
(`gotcha_sftp_base_path_must_preexist`,
`gotcha_pytest_generate_tests_scope`,
`gotcha_async_docstring_ripple_chain`) surfaced in PR #597 and PR #582
fix commits. They were not in any trace's orient phase.

### 5.3 CHANGELOG gate hit-rate

Trace authors mark `CHANGELOG.md [Unreleased]` as a verify gate in 31/39
traces (79%). The 9-PR sample matches this rate: 7/9 PRs touched
CHANGELOG. The two that skipped (BK-179 fixture registry, BK-187 lint
scope) were both pure tooling/infra work. The schema did not let trace
authors record this distinction.

---

## 6. Audience Taxonomy Derivation

The pattern in § 5.3 motivated a richer way to record what a change is
*for*. Going item-by-item through the 39 unreleased entries in
`sdd/BACKLOG-DONE.md` § Unreleased, the audiences sort into a stable set
of ten values:

| Audience | Items (n=39) | Count | CHANGELOG? |
|---|---|---|---|
| `user.api` | BK-176, ID-178, BUG-194, BUG-192, BUG-190, BUG-189, BK-168 | 7 | yes |
| `user.api_docs` | BK-174, BK-173 | 2 | yes |
| `user.site` | BUG-188, BUG-187, BUG-186, BK-170 + 2 secondary | 4+2 | yes |
| `user.discoverability.llm` | ID-176 | 1 | yes |
| `user.discoverability.human` | (none in unreleased) | 0 | yes |
| `contributor.process` | BK-167, BK-167b, BK-165, BK-175, ID-175 | 5 | sometimes |
| `contributor.tooling` | BK-187, ID-177, BK-169, BK-167a + 1 secondary | 4+1 | no |
| `infra.test` | 13 items (BK-179/180/183-186/188-190, BK-166/172, BUG-182/191/193) | 13 | no |
| `infra.ci` | BK-183 | 1 | no |
| `internal.style` | BK-178 | 1 | no |

The split that motivated the taxonomy:

- **BK-174 vs BK-178** — both docstring edits, but BK-174 adds new
  `Raises:` info (`user.api_docs`, CHANGELOG yes) while BK-178 just
  swaps RST roles for double-backticks (`internal.style`, CHANGELOG no).
- **BK-168 vs BK-172** — both pyarrow work, but BK-168 lifts the
  user-facing pin (`user.api`) while BK-172 reroutes tests to MinIO so
  the lift is safe (`infra.test`).
- **ID-176 (context7) vs BK-187 (lint scope)** — both originally
  candidates for "not user-facing", but context7 is outside-package
  presentation that users (or their LLMs) reach the package through
  (`user.discoverability.llm`, CHANGELOG yes), while lint scope is
  contributor-only (`contributor.tooling`, CHANGELOG no).

### 6.1 Derived rule

```
changelog_required = any(a.startswith("user.") for a in audience)
                  OR ("contributor.process" in audience AND new framework/spec)
```

Validates on all nine sampled PRs. The split `user.discoverability` into
`.llm` and `.human` was kept even though only `.llm` has unreleased
examples; future README badge work would land in `.human` and the rule
applies either way.

### 6.2 Why a list, not a primary

Three of 39 items are honestly multi-audience (BK-167b applies the doc
framework *and* restructures end-user nav; BK-171 adds a contributor
link-validation gate *and* keeps user-site pages from breaking; BK-190
tightens test placement *and* adds a contributor-tooling check script).
A primary + secondary split would force a false choice. A
priority-sorted list lets the first entry act as primary for downstream
tooling without losing the secondary signal.

---

## 7. Outcome — What Shipped Under BK-193

`sdd/traces/_schema.yml` gained six fields plus sharpened description
prose, in two waves:

**Initial wave** (from Phase 3 findings, § 5):

- `audience` (required list, priority-sorted, 10-value enum)
- `discovery_followups` (optional list of backlog IDs born in review)
- `co_shipped_items` (optional list of other items closed by the same PR)
- `expected_ripples` (originally `known_ripples`; renamed below)
- `review_rounds` (optional int)

**Schema-review wave** (after a structured external review of the
schema as data; § 8.1 captures what was rejected):

- `outcome` (optional, step-level, enum `ok` / `unclear` /
  `misleading`) — step-local doc-failure signal; the descriptive-to-
  diagnostic lever for "which sections actually confuse readers."
- `surprising_ripples` (optional, top-level list) — paired with
  `expected_ripples`. The rename of `known_ripples` to
  `expected_ripples` made the distinction load-bearing: expected =
  mechanical, anticipated by ripple-check; surprising = pain ripples
  that point at missing coverage. Three of the nine sampled traces
  carry surprising entries (BK-178, BK-179, BK-187).
- Schema description text tightened to instruct authors that traces
  record what actually happened. Authoring discipline is the only
  defence against cleanup-on-write distorting aggregator results.

All 39 unreleased trace YAMLs were re-tagged with `audience` lists. The
nine traces in the Phase-3 sample additionally carry retrospective
`discovery_followups`, `co_shipped_items`, `expected_ripples`,
`surprising_ripples`, and `review_rounds` filled from their merged PRs.

No validator is wired — the `required: audience` constraint acts as
authoring convention. Future traces missing `audience` will fail at the
next aggregator run rather than at commit time.

---

## 8. Open Questions

The Phase-3 sample was nine traces. Several findings deserve
verification at full scale:

- **Extend sample to all 39.** Re-run the trace-vs-PR comparison on
  every unreleased item to confirm the median fan-out (1.2×) and identify
  whether the three outliers (BK-187 5.2×, BK-179 6.4×, BK-178 3.6×)
  generalise or are coincidental.
- **Model review-driven phases.** Three patterns appeared in real
  commits but no trace recorded them: `rebase_fix`,
  `address_review_thread`, `regenerate_artefacts`. Worth asking whether
  the schema should enumerate them or whether `discovery_followups`,
  `review_rounds`, and step-level `outcome` capture enough.
- **Promote ripple-check from verify to also-implement-start.** Three of
  the nine sampled PRs missed ripples (`.github/workflows/ci.yml` in
  #604, `graph.json` + `graph_viz.html` in #591, `_proxy.py` + extension
  wrappers in #592) because `CLAUDE-REFERENCE.md` was treated as a
  closing checklist, not an opening one. The cheapest fix is doc:
  rewrite the trigger phrases in the ripple-check table so the table
  reads usefully *before* coding, not only after. The schema-review
  wave's `surprising_ripples` field now gives this a measurable signal
  — a recurring entry in `surprising_ripples` is direct evidence that
  the ripple-check table is missing a row.
- **Stable section anchors for non-spec docs.** Specs already have
  stable IDs (`ASYNC-016`, `WR-013`); non-spec docs (CLAUDE.md
  "Principles", CLAUDE-REFERENCE "Ripple-check table / A bug fix") do
  not. Adding HTML-anchor IDs (`<!-- id: ripple-bug-fix -->`) across
  `sdd/` would inoculate traces against heading-text drift. Significant
  authoring work; deferred but worth tracking as the trace data grows.
- **Content-churn flag.** PR #579 (ID-176) had eleven commits on a
  seventeen-line file. The schema-review wave deliberately rejected a
  numeric `effort: 1-5` field on inconsistency grounds; `outcome:
  unclear` carries the signal for the underlying spec/doc, but does
  not flag that the change *itself* is editorially volatile. One
  example is not enough to establish the pattern.
- **Aggregator metric: within-trace duplication.** A schema-review
  suggestion to model "did the agent re-read the same section because
  it was unclear, or because it is central?" was reframed as an
  aggregator concern — the data is in the existing fields, count the
  `(file, section)` pairs per trace. Worth implementing once a real
  aggregator exists.
- **Validator.** The audience field is `required` in the schema but
  unenforced. Wiring a check into `hatch run lint` would turn the
  convention into a gate. Cost is small; risk is that authors learn to
  tag mechanically without thinking. Same risk applies to `outcome` —
  defaulting to `ok` invites rubber-stamping. Open question.

### 8.1 What the schema-review wave rejected

The same external review that drove the `outcome` / `surprising_ripples`
additions also proposed three changes that were judged net-negative and
not shipped:

- **`effort: 1-5` step-level scoring.** Subjective integer effort rots
  across authors. The signal it promises (rank pain) is already covered
  at PR level by `review_rounds` and Phase-3 fan-out math, both of
  which are objective. Step-local pain lands in `outcome: misleading`
  instead.
- **A separate `reason:` field on each step.** The motivation and the
  product of a read overlap enough that splitting them invites both
  fields being thin. Tightening `extract`'s description to require
  motivation when non-obvious does the same work in one field. The
  schema description text was updated accordingly.
- **Step-reuse tracking.** Suggested as a schema field; reframed as an
  aggregator metric (above).

---

## 9. Method Provenance

All evidence in this doc derives from:

- 39 trace files under `sdd/traces/` (committed in PR #608 and the
  follow-ups BK-176, BK-179, BK-184, BK-187 etc.).
- Merged PRs #579, #582, #590, #591, #592, #597, #604, #606, #607
  fetched via `gh pr view --json files,commits,reviews`.
- `sdd/BACKLOG-DONE.md` § Unreleased for audience derivation.

Phase 1 and 2 aggregator scripts were prototyped under `tmp/` during the
investigation; they are not retained because the findings they produced
are now in this doc and the trace data they aggregated is stable.
