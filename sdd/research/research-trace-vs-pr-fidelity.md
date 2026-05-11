# Research: Trace-vs-PR Fidelity Analysis (BK-193)

**Date:** 2026-05-11
**Backlog items:** BK-193 (Trace schema: `audience` field + post-hoc fields; re-tag unreleased traces)
**Status:** Research complete — informed BK-193 schema additions and re-tagging of all 39 unreleased traces under `sdd/traces/`.

---

## 1. Problem Statement

PR #608 added `sdd/traces/` to record the ordered reads an agent performs while doing backlog work, intending to drive documentation optimisation (hotspot detection, gate-density ranking, co-read clustering). The stated goal: identify the spine of files an agent must read, then refactor `sdd/` so that spine shrinks.

**Current limitation.** Traces were authored by the same agents that did the work — often before or during the work, not after the PR merged. The data therefore describes *anticipated* reads, not necessarily the reads the work actually required. If the gap is large, aggregator outputs optimise for the rule-following spine, not for the surface where real work happens.

**Affected.** Agents working on backlog items; future authors of trace tooling; doc maintainers who would act on aggregator findings.

**Constraints from existing artefacts.** The SDD pipeline (`sdd/000-process.md` § Rule 6) treats specs as authoritative; the ripple-check table in `sdd/CLAUDE-REFERENCE.md` enumerates expected cross-cuts; PR #608's trace schema (`sdd/traces/_schema.yml`) models step-level reads but not the messy aggregate signals (review iteration, discovery cascades, ripple omissions). Research docs are point-in-time snapshots per `sdd/000-process.md` § Document types.

**Decision this research is meant to inform.** Ship the trace data as-is and let aggregator design absorb the gaps, or extend the schema first so the data can carry the missing signals? Specifically: which signals are missing, how can they be modelled without bloating the schema, and which taxonomy correctly represents who a change is *for* (the polysemous "is this user-facing?" question that motivates the CHANGELOG gate).

---

## 2. Survey: Three-Phase Empirical Investigation

Three phases, each blind to the next, to keep early-phase intuitions from biasing later evidence.

### 2.1 Phase 1 — Pure data analysis

**Pattern.** Treat the 39 trace YAMLs as opaque records. Compute distributions, phase sequences, file rank-frequency, co-occurrence clusters, read-type by phase, section-string patterns. No repo knowledge.

**How it works.** Aggregation over ~280 step references across 39 traces:

- *File rank-frequency.* Six files account for 60% of all reads. `sdd/CLAUDE-REFERENCE.md` (41), `sdd/000-process.md` (28), `sdd/TESTING.md` (24), `sdd/DESIGN.md` (22), `CHANGELOG.md` (19), `CLAUDE.md` (17). Long tail of 29 files cited 1–3 times.
- *Phase-vocabulary instability.* Seven phases appear in ≥ 25% of traces (orient, implement, verify, tests, fix, spec, docs); ten more appear ≤ 2 times. Outliers (`spec_review`, `reproduce`, `classify`, `wire`) suggest authors reach for new phase IDs when the standard set does not capture the work shape.
- *Read-type by phase.* `orient` reads are 87% gate; `verify` reads are 100% verify; `implement` reads are 78% reference. The `orient → middle → verify` envelope is stable.
- *Section-string convention.* 19% of section references use the "X / Y" form. All of them are ripple-check table row pointers. Outside the ripple-check table this pattern does not appear.
- *Jaccard co-occurrence clusters.* Two arcs emerge: a doc-framework cluster (BK-167 family, BK-171, BK-178, ID-177) sharing the authoring/process docs; and an async-Azure cluster (BK-173, BK-174, BUG-189–194) sharing the backend / WriteResult / Azure specs.

**Trade-offs.**

- Pro: reveals structural facts that are robust regardless of doc content; cheap to compute.
- Con: cannot say whether the structure matches what the work actually required — only what was anticipated.

### 2.2 Phase 2 — Cross-check against the real docs

**Pattern.** Validate Phase 1's data-only claims against the actual content of `sdd/` and `CLAUDE.md`.

**How it works.** The six-file spine survives scrutiny: `CLAUDE-REFERENCE.md` carries the ripple-check table and is the most cross-cited file in the repo; `000-process.md` § Rule 6 contains the canonical bug-fix pipeline that traces cite verbatim 14 times; `TESTING.md` § Test Subpackage Placement and § Rules are the authoritative references and traces treat them as gates accordingly. One Phase-1 claim partially failed: the "doc-framework cluster" splits into two sub-clusters under closer reading — pure content edits (BK-178 RST roles) versus framework rollout (BK-167 family). Jaccard distance did not distinguish them because both touch the same authority docs.

**Trade-offs.**

- Pro: catches data artefacts (a hot file in the data might be hot because authors paraphrase it, not because the doc is authoritative).
- Con: still measures the trace data against the docs, not against the work the docs are meant to support.

### 2.3 Phase 3 — Trace vs merged PR (n=9)

**Pattern.** For nine sampled merged PRs spanning iteration-cost regimes (high ≥ 11 commits, medium 4–8, low 1–2), compare the trace's anticipated reads to the PR's actual files, commits, review rounds, and follow-up items.

**How it works.** Sample:

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

Five patterns the trace schema could not model emerged:

- *Trace verbosity does not predict iteration cost.* ID-178 had the longest trace (18 steps) and merged in one commit; ID-176 had one of the shortest traces and required eleven commits.
- *Single-commit is not always simple.* ID-178 trace anticipated six files; the PR touched nineteen — proxy wrapper, two extension files, graph regen, an example, `backlogid.json`.
- *Multi-commit is not always complex.* PR #579 (ID-176) touched four files, +29 / −1, yet had eleven commits of editorial pushback on a 17-line file.
- *Discovery cascades are unmodeled.* BUG-193 started as one bug and surfaced BUG-194 (a real SDK bug), BUG-196, BUG-197, BK-175 supersession of ID-175, TESTING.md rule violations, RST role cleanup, and stale mock tests broken by the chained fix.
- *Bundled scope inflates apparent coverage.* PR #606 traced as two items (BK-189, BK-190); shipped three (BK-188 joined during implementation).

Systematic ripple omissions across the nine PRs:

| Ripple | Hits | Trigger |
|---|---|---|
| `sdd/backlogid.json` | 5/9 | mechanical on backlog moves |
| `.github/workflows/ci.yml` | 3/9 | `pyproject.toml` lint scope or test-layout change |
| `docs-src/_data/graph/graph.json` | 2/9 | docstring or public-API change |
| `docs-src/explanation/graph_viz.html` | 2/9 | same trigger as graph.json |
| `pyproject.toml` lint scope | 2/9 | tooling work |
| `src/remote_store/_proxy.py` | 1/9 | new Store method |
| `src/remote_store/ext/*.py` | 1/9 | new Store method |
| `examples/**` | 1/9 | public API change |
| Stale mock tests | 1/9 | SDK-level fix |

Trace authors mark `CHANGELOG [Unreleased]` as a verify gate in 31/39 traces (79%). The 9-PR sample matches this rate: 7/9 touched CHANGELOG. The two that skipped (BK-179 fixture registry, BK-187 lint scope) were both pure tooling/infra work. The schema offered no way to record this distinction.

**Trade-offs.**

- Pro: ground truth — what the work actually required.
- Con: nine-trace sample only; covers iteration-cost regimes but not every item-type slice.

### 2.4 Audience-taxonomy survey

Phase 3 motivated a follow-on survey: going through the 39 unreleased entries in `sdd/BACKLOG-DONE.md` § Unreleased one by one, what is each change *for*?

| Audience | Items (n=39) | Count | CHANGELOG? |
|---|---|---|---|
| `user.api` | BK-176, ID-178, BUG-194, BUG-192, BUG-190, BUG-189, BK-168 | 7 | yes |
| `user.api_docs` | BK-174, BK-173 | 2 | yes |
| `user.site` | BUG-188, BUG-187, BUG-186, BK-170 + 2 secondary | 4+2 | yes |
| `user.discoverability.llm` | ID-176 | 1 | yes |
| `user.discoverability.human` | (none in unreleased) | 0 | yes |
| `contributor.process` | BK-167, BK-167b, BK-165, BK-175, ID-175 | 5 | sometimes |
| `contributor.tooling` | BK-187, ID-177, BK-169, BK-167a + 1 secondary | 4+1 | no |
| `infra.test` | 13 items | 13 | no |
| `infra.ci` | BK-183 | 1 | no |
| `internal.style` | BK-178 | 1 | no |

Three gray-case splits drove the taxonomy:

- BK-174 vs BK-178 — both docstring edits, but BK-174 adds new `Raises:` info (`user.api_docs`, CHANGELOG yes) while BK-178 just swaps RST roles for double-backticks (`internal.style`, CHANGELOG no).
- BK-168 vs BK-172 — both pyarrow work, but BK-168 lifts the user-facing pin (`user.api`) while BK-172 reroutes tests to MinIO so the lift is safe (`infra.test`).
- ID-176 vs BK-187 — both candidates for "not user-facing", but context7 is outside-package presentation users (or their LLMs) reach the package through (`user.discoverability.llm`, CHANGELOG yes), while lint scope is contributor-only (`contributor.tooling`, CHANGELOG no).

---

## 3. Evaluation

Combining the four surveys against the constraint set (model what's missing without bloating the schema; preserve authoring discipline; remain analytically useful):

| Criterion | Trace-as-shipped (PR #608) | Extended schema |
|---|---|---|
| Models anticipated reads | yes | yes |
| Models discovery cascades (BUG-193 → BUG-194/196/197) | no | yes (`discovery_followups`) |
| Models bundled scope (PR #606 closing BK-188/189/190) | no | yes (`co_shipped_items`) |
| Models ripple omissions (#604 missing `ci.yml`) | no | yes (`expected_ripples` + `surprising_ripples`) |
| Models review-iteration cost | no | yes (`review_rounds`) |
| Distinguishes user-facing from infra | bool flag only | yes (`audience` list, 10 enum values) |
| Distinguishes `user.api_docs` (BK-174) from `internal.style` (BK-178) | no | yes |
| Distinguishes LLM-discoverability (context7) from contributor-tooling (lint scope) | no | yes |
| Surfaces doc-failure at step level | no | yes (`outcome` enum) |
| Carries CHANGELOG-required rule derivation | no | yes (derived from `audience` prefix) |
| Field count | 5 top-level + 4 step | 10 top-level + 5 step |
| Authoring discipline (records actual, not ideal) | not stated | tightened in schema description |

The extended schema costs five new top-level fields and one new step-level field. Each closes a specific signal-loss observed in Phase 3 or in the audience survey. No field invents structure not already present in the empirical evidence.

Cross-phase consistency check: Phase 1's "CHANGELOG is a near-universal verify gate" claim (79% of traces) is consistent with Phase 3's actual hit-rate (78%) — but only the audience taxonomy explains *which* 22% correctly skip it (pure `contributor.tooling`, `infra.test`, `infra.ci`, `internal.style`).

---

## 4. Recommendation

Extend the schema in two waves, both shipped under BK-193. All 39 unreleased traces re-tagged; the nine Phase-3-sampled traces additionally carry retrospective fields filled from their merged PRs.

### 4.1 Initial wave — anchored in Phase 3 patterns

Five new top-level fields:

- `audience` (required, priority-sorted list, 10-value enum) — closes the conflation that motivated the audience survey. Derived rule: CHANGELOG required iff any entry in `audience` starts with `user.`, or `contributor.process` introduces a new framework.
- `discovery_followups` (optional list of backlog IDs) — captures items born during review.
- `co_shipped_items` (optional list of backlog IDs) — captures bundled scope.
- `expected_ripples` (optional list of paths) — mechanical tag-along files anticipated by the ripple-check table.
- `review_rounds` (optional int) — review-driven fix-commit count.

### 4.2 Schema-review wave — external review acceptance/rejection

A structured external review of the schema-as-data surfaced one design risk (clean-narrative bias) and six tactical suggestions. Three accepted, three rejected.

**Accepted:**

- `outcome` (optional, step-level, enum `ok` / `unclear` / `misleading`) — step-local doc-failure signal. Recurring `misleading` on a section is a doc-rewrite candidate; recurring `unclear` flags underspecified areas.
- `surprising_ripples` (optional, top-level list of paths) — paired with `expected_ripples`. The rename of `known_ripples` to `expected_ripples` made the distinction load-bearing in the name: expected = anticipated, surprising = where coverage failed. A recurring entry in `surprising_ripples` is direct evidence the ripple-check table is missing a row.
- Schema description text tightened: traces record what actually happened, not what should have happened. Authoring discipline is the only defence against cleanup-on-write.

**Rejected and why:**

- *`effort: 1-5` step-level scoring.* Subjective integer effort rots across authors. The signal it promises (rank pain) is already covered at PR level by `review_rounds` and Phase-3 fan-out math, both objective. Step-local pain lands in `outcome: misleading` instead.
- *Separate `reason:` field on each step.* Motivation and product of a read overlap enough that splitting them invites both fields being thin. The `extract:` description was tightened instead to require motivation when non-obvious.
- *Step-reuse tracking as a schema field.* The data is already there — counting `(file, section)` pairs per trace is one line of aggregator code. Reframed as an aggregator metric.

### 4.3 Open questions

- *Extend sample to all 39.* Re-run the trace-vs-PR comparison on every unreleased item to confirm the median fan-out (1.2×) and identify whether the three outliers (BK-187 5.2×, BK-179 6.4×, BK-178 3.6×) generalise.
- *Model review-driven phases.* Three patterns appeared in real commits but no trace recorded them: `rebase_fix`, `address_review_thread`, `regenerate_artefacts`. Open whether the schema should enumerate them or whether `discovery_followups`, `review_rounds`, and `outcome` capture enough.
- *Promote ripple-check from verify to also-implement-start.* The cheapest fix is doc: rewrite the trigger phrases in the ripple-check table so the table reads usefully before coding, not only after. The `surprising_ripples` field now makes this measurable — a recurring entry is direct evidence of a missing row.
- *Stable section anchors for non-spec docs.* Specs already have stable IDs (`ASYNC-016`, `WR-013`); non-spec docs (CLAUDE.md "Principles", CLAUDE-REFERENCE row pointers) do not. Adding HTML-anchor IDs across `sdd/` would inoculate traces against heading-text drift. Significant authoring work; tracked for when trace data grows.
- *Content-churn flag.* PR #579 (ID-176) had eleven commits on a 17-line file. `outcome: unclear` carries the signal for the underlying spec/doc, but does not flag that the change itself is editorially volatile. One example is not enough to establish the pattern.
- *Validator.* The `audience` field is `required` in the schema but unenforced. Wiring a check into `hatch run lint` would turn the convention into a gate. Cost is small; risk is that authors learn to tag mechanically without thinking. Same risk applies to `outcome` defaulting to `ok`.

### 4.4 Method provenance

All evidence derives from:

- 39 trace files under `sdd/traces/` (committed in PR #608 and the per-item follow-ups: BK-176, BK-179, BK-184, BK-187, BK-188–190, BUG-182, BUG-186–194, ID-175–178).
- Merged PRs #579, #582, #590, #591, #592, #597, #604, #606, #607 fetched via `gh pr view --json files,commits,reviews`.
- `sdd/BACKLOG-DONE.md` § Unreleased for the audience-taxonomy derivation.

Phase 1 and 2 aggregator scripts were prototyped under `tmp/` during the investigation; they are not retained because the findings they produced are now in this doc and the trace data is stable enough for re-derivation.
