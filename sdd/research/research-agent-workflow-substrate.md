# Research: Substrate for Data-Driven Improvement of Agent Workflows

**Date:** 2026-05-11
**Backlog items:** BK-193 (Trace schema: `audience` field + post-hoc fields; re-tag unreleased traces)
**Status:** Research complete — informed BK-193 schema additions and re-tagging of all 39 unreleased traces under `sdd/traces/`.
**Reader's orientation:** §§ 1–3 justify the BK-193 schema work already shipped; § 4 recommends what comes next.

---

## 1. Problem Statement

**The bigger programme.** PR #608 added [`sdd/traces/`](../traces/) as the substrate for **data-driven improvement of agent workflows**. The schema's immediate stated use (optimisation of the sdd/ documentation structure via hotspot and co-read aggregation) is one application. The broader intent: turn the way agents move through documentation into analysable structure so the workflow itself can be evolved on evidence rather than intuition. Cross-trace aggregation should be able to surface where docs slow agents down, where reads recur (suggesting consolidation), where review iteration spikes (suggesting unclear guidance), and where the agent process itself should be tightened. The substrate is in scope for this research; the long-term programme that consumes it is sketched in § 4.3 but not planned in detail here. Specific immediate actions surfaced by the analysis (the next-PR work item and the in-PR precondition for it) are in scope and appear in § 4.1.

**Current limitation.** Traces are not written by the agents doing the work. They are authored after the fact by a fresh agent session: one with access to the merged PR record, the backlog item, and the existing docs, but no first-hand experience of the implementation chaos. This produces a sanitized "best-practice" trace, a rule-following spine that walks cleanly down the SDD pipeline. The unresolved question is how far that retrospective reconstruction tracks the reads the work *actually* required versus the reads the work *would have* required under the ideal process.

**Affected.** Agents working on backlog items (whose workflow is the optimisation target); future authors of trace tooling and aggregators; doc maintainers and process owners who would act on aggregator findings.

**Constraints from existing artefacts.** Three classes of authoritative docs are in scope, and the analysis must keep them distinct because they answer different questions:

- *Process authorities* define the rules of how work is done. They gate reads. The inventory: [`CLAUDE.md`](../../CLAUDE.md) (Claude-Code principles), [`CONTRIBUTING.md`](../../CONTRIBUTING.md) (contributor workflow, release flow, signing), [`sdd/AUTHORING.md`](../AUTHORING.md), [`sdd/DOCUMENTATION.md`](../DOCUMENTATION.md), [`sdd/CONTENT-RULES.md`](../CONTENT-RULES.md), [`sdd/000-process.md`](../000-process.md), [`sdd/DESIGN.md`](../DESIGN.md), [`sdd/TESTING.md`](../TESTING.md), [`sdd/CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md), plus the specs, ADRs, RFCs, and audits under [`sdd/`](..).
- *Content authority (special case).* [`FEATURES.md`](../../FEATURES.md) is the only authoritative doc that lives at the repo root rather than under `sdd/`, and the only one machine-generated. Per [`sdd/DOCUMENTATION.md`](../DOCUMENTATION.md) § 2 it is the "feature inventory (exception)": generated from the graph IR by `scripts/gen_features.py`, it is the authoritative answer to *what exists* (backends, capabilities, extensions, install extras), complementary to the process authorities which answer *how to work*. It is read for verification of inventory claims, not for rules.
- *Log artifacts* record outcomes after the fact and do not define rules: [`CHANGELOG.md`](../../CHANGELOG.md) (release history), [`sdd/BACKLOG.md`](../BACKLOG.md) (active work), [`sdd/BACKLOG-DONE.md`](../BACKLOG-DONE.md) (closed-work history). Traces cite these with `read_type: verify` because the read is "have I added my stub?", not "what rule governs me?". Conflating them with process authorities would treat them as rule-defining when they are receive-targets.

The SDD pipeline (rule 6 in [`sdd/000-process.md`](../000-process.md) § Rules) and the ripple-check table in [`sdd/CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) are the load-bearing process authorities for backlog work. PR #608's trace schema ([`sdd/traces/_schema.yml`](../traces/_schema.yml)) models step-level reads but not the messy aggregate signals (review iteration, discovery cascades, ripple omissions). Research docs are point-in-time snapshots per [`sdd/000-process.md`](../000-process.md) § Document types.

**Decision this research is meant to inform.** Before any aggregator-driven workflow change is built on this data, two questions need empirical grounding: (a) does the trace data have enough fidelity to the work that actually happens for aggregator outputs to be trustworthy? (b) if not, can the schema be extended to carry the missing signals without bloating? The downstream programme, using the data to drive doc, process, and agent-behaviour changes, depends on both answers being yes. This research investigates (a) empirically and proposes a minimal-bloat answer to (b).

---

## 2. Survey: Three-Phase Empirical Investigation

Three phases, each blind to the next, to keep early-phase intuitions from biasing later evidence.

### 2.1 Phase 1: Pure data analysis

**Pattern.** Compute distributions, phase sequences, file rank-frequency, co-occurrence clusters, read-type by phase, section-string patterns from the 39 trace YAMLs directly. Doc content is not consulted in this phase (that is Phase 2); the § 1 three-class typology is applied for grouping.

**How it works.** Aggregation over ~280 step references across 39 traces:

- *File rank-frequency.* Six files account for 151 reads out of ~280 (≈ 54%): [`sdd/CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) (41), [`sdd/000-process.md`](../000-process.md) (28), [`sdd/TESTING.md`](../TESTING.md) (24), [`sdd/DESIGN.md`](../DESIGN.md) (22), [`CHANGELOG.md`](../../CHANGELOG.md) (19), [`CLAUDE.md`](../../CLAUDE.md) (17). Long tail of 29 files cited 1–3 times.
- *Top-6 split by class.* Five of the top six are process authorities; the sixth ([`CHANGELOG.md`](../../CHANGELOG.md)) is a log artifact. The spine therefore mixes "rules I must obey" with "stub I must write" at roughly 80/20. Aggregator code that ranks "files agents stall on" should keep the two apart: log artifacts cannot be improved by rewriting the doc, only by changing whether a stub is needed (the audience-derived CHANGELOG rule in § 2.4 does exactly this).
- *Notable absences from the top tier.* [`CONTRIBUTING.md`](../../CONTRIBUTING.md) and [`FEATURES.md`](../../FEATURES.md) sit in the long tail despite being authoritative. CONTRIBUTING.md is contributor / release process, and the 39 sampled items are library and infra work; no release-flow trace exists in the unreleased section yet, so the absence is expected. FEATURES.md is auto-generated and the inventory it holds (capabilities, extras) is derived from specs and code; agents reach for the specs directly, not the projection. Both absences are evidence that traces follow source-of-truth, not derived presentations.
- *Phase-vocabulary instability.* Seven phases appear in ≥ 25% of traces (orient, implement, verify, tests, fix, spec, docs); ten more appear ≤ 2 times. Outliers (`spec_review`, `reproduce`, `classify`, `wire`) suggest authors reach for new phase IDs when the standard set does not capture the work shape.
- *Read-type by phase.* `orient` reads are 87% gate; `verify` reads are 100% verify; `implement` reads are 78% reference. The `orient → middle → verify` envelope is stable.
- *Section-string convention.* 19% of section references use the "X / Y" form. All of them are ripple-check table row pointers. Outside the ripple-check table this pattern does not appear.
- *Jaccard co-occurrence clusters.* Two arcs emerge: a doc-framework cluster (BK-167 family, BK-171, BK-178, ID-177) sharing the authoring/process docs; and an async-Azure cluster (BK-173, BK-174, BUG-189–194) sharing the backend / WriteResult / Azure specs.

**Trade-offs.**

- Pro: reveals structural facts that are robust regardless of doc content; cheap to compute.
- Con: cannot say whether the structure matches what the work actually required, only what was anticipated.

### 2.2 Phase 2: Cross-check against the real docs

**Pattern.** Validate Phase 1's data-only claims against the actual content of [`sdd/`](..) and [`CLAUDE.md`](../../CLAUDE.md).

**How it works.** The six-file spine survives scrutiny: [`CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) carries the ripple-check table and is the most cross-cited file in the repo; [`000-process.md`](../000-process.md) § Rules rule 6 contains the canonical bug-fix pipeline that traces cite verbatim 14 times; [`TESTING.md`](../TESTING.md) § Test Subpackage Placement and § Rules are the authoritative references and traces treat them as gates accordingly. One Phase-1 claim partially failed: the "doc-framework cluster" splits into two sub-clusters under closer reading: pure content edits (BK-178 RST roles) versus framework rollout (BK-167 family). Jaccard distance did not distinguish them because both touch the same authority docs.

A secondary finding from this phase: a paragraph-level enumeration of [`CONTRIBUTING.md`](../../CONTRIBUTING.md) against [`sdd/`](..) surfaced that the "Authoritative Document Format" section is placement guidance and belongs in [`sdd/AUTHORING.md`](../AUTHORING.md), not in CONTRIBUTING.md. Carrying the section in CONTRIBUTING.md is one of two reasons CONTRIBUTING.md does not appear in the rank-frequency spine: where it does carry rule-defining content, the rule already lives elsewhere; for the rest, it is a contributor-onboarding doc that backlog traces do not consult. Not in scope to relocate as part of this research, but recorded so a future authoring-framework cleanup has a starting point.

**Trade-offs.**

- Pro: catches data artefacts (a hot file in the data might be hot because authors paraphrase it, not because the doc is authoritative).
- Con: still measures the trace data against the docs, not against the work the docs are meant to support.

### 2.3 Phase 3: Trace vs merged PR (n=9)

**Pattern.** For nine sampled merged PRs spanning iteration-cost regimes (high ≥ 11 commits, medium 4–8, low 1–2), compare the trace's reconstructed reads to the PR's actual files, commits, review rounds, and follow-up items. Since traces are fresh-agent retrospectives over the merged record, the gap between trace and PR measures specifically what the retrospective agent flattened away, not what the implementing agent forgot to log.

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
† Reviews = count of GitHub formal review-submission events (from `gh pr view --json reviews | length`), distinct from the `review_rounds` field in the trace files, which counts review-driven fix commits. The two numbers measure different things; BK-174's row shows Reviews=8 while its trace records `review_rounds: 3`.

Five patterns the trace schema could not model emerged:

- *Trace verbosity does not predict iteration cost.* ID-178 had the longest trace (18 steps) and merged in one commit; ID-176 had one of the shortest traces and required eleven commits.
- *Single-commit is not always simple.* ID-178 trace anticipated six files; the PR touched nineteen: proxy wrapper, two extension files, graph regen, an example, `backlogid.json`.
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

Trace authors mark `CHANGELOG [Unreleased]` as a `verify` read in 31/39 traces (79%). The 9-PR sample matches this rate: 7/9 touched CHANGELOG. The two that skipped (BK-179 fixture registry, BK-187 lint scope) were both pure tooling/infra work. Since CHANGELOG is a log artifact (§ 1), the `verify` read here is "did I add my stub?", not "what rule governs me?". The pre-BK-193 schema offered no way to distinguish stub-required from stub-skipped reads; the audience field added in § 4.1 closes that gap by deriving the requirement.

**Trade-offs.**

- Pro: ground truth, what the work actually required.
- Con: nine-trace sample only; covers iteration-cost regimes but not every item-type slice.

### 2.4 Audience-taxonomy survey

Phase 3 motivated a follow-on survey. The data source is [`sdd/BACKLOG-DONE.md`](../BACKLOG-DONE.md) § Unreleased: 39 entries, each describing one shipped backlog item. The file is a log artifact (§ 1), not a process authority, but it is the only place where every closed item carries a written rationale, so it serves as the empirical sample for "what is each change *for*?".

| Audience | Items (n=39) | Count | CHANGELOG? |
|---|---|---|---|
| `user.api` | BK-176, ID-178, BUG-194, BUG-192, BUG-190, BUG-189, BK-168 | 7 | Yes |
| `user.api_docs` | BK-174, BK-173 | 2 | Yes |
| `user.site` | BUG-188, BUG-187, BUG-186, BK-170 + 2 secondary | 4+2 | Yes |
| `user.discoverability.llm` | ID-176 | 1 | Yes |
| `user.discoverability.human` | (none in unreleased) | 0 | Yes |
| `contributor.process` | BK-167, BK-167b, BK-165, BK-175, ID-175 | 5 | Yes¹ |
| `contributor.tooling` | BK-187, ID-177, BK-169, BK-167a + 1 secondary | 4+1 | — |
| `infra.test` | 13 items | 13 | — |
| `infra.ci` | BK-183 | 1 | — |
| `internal.style` | BK-178 | 1 | — |

¹ `contributor.process` triggers a CHANGELOG entry only when the change introduces a new framework, spec, or ADR; routine process edits (audit reports, template additions) do not.

Three gray-case splits drove the taxonomy:

- BK-174 vs BK-178: both docstring edits, but BK-174 adds new `Raises:` info (`user.api_docs`, CHANGELOG Yes) while BK-178 just swaps RST roles for double-backticks (`internal.style`, CHANGELOG `—`).
- BK-168 vs BK-172: both pyarrow work, but BK-168 lifts the user-facing pin (`user.api`) while BK-172 reroutes tests to MinIO so the lift is safe (`infra.test`).
- ID-176 vs BK-187: both candidates for "not user-facing", but context7 is outside-package presentation users (or their LLMs) reach the package through (`user.discoverability.llm`, CHANGELOG Yes), while lint scope is contributor-only (`contributor.tooling`, CHANGELOG `—`).

**Sample skew.** 13 of 39 items are `infra.test` and `user.discoverability.human` has zero unreleased examples (reserved for symmetry with `.llm`). The taxonomy is best-grounded for slices with multiple items; the gray-case splits above stress-test the boundaries that did appear. Slices with zero or single examples carry no empirical grounding for boundary disputes.

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
| Field count | 5 top-level + 4 step | 11 top-level + 5 step |
| Authoring discipline (records actual, not ideal) | not stated | tightened in schema description |

The extended schema costs six new top-level fields and one new step-level field. Each closes a specific signal-loss observed in Phase 3 or in the audience survey. No field invents structure not already present in the empirical evidence.

Cross-phase consistency check: Phase 1's "CHANGELOG is a near-universal verify gate" claim (79% of traces) is consistent with Phase 3's actual hit-rate (78%), but only the audience taxonomy explains *which* 22% correctly skip it (pure `contributor.tooling`, `infra.test`, `infra.ci`, `internal.style`). The check is methodologically load-bearing: had Phase 3's PR-actual rate diverged sharply from Phase 1's trace-claimed rate (say 50% vs 79%), Phase 1's spine claim would have been falsified and the audience taxonomy would have lacked an empirical anchor.

---

## 4. Recommendation

The substrate question (§ 1) was answered in two schema-extension waves shipped under BK-193: the full set of fields and the accepted / rejected proposals are summarised in § 3's right column and recorded in [`sdd/BACKLOG-DONE.md`](../BACKLOG-DONE.md). The recommendation below is forward-looking.

### 4.1 Quick wins

Two on-thesis actions:

- **(in this PR) Live-trace authoring discipline.** A new "Trace authoring (mandatory)" section in [`CLAUDE.md`](../../CLAUDE.md) instructs every session in this repo to maintain `sdd/traces/<id>-<slug>.yml` as work proceeds, not after merge. This is the directly on-thesis recommendation: the substrate (§§ 1–3) only carries honest signal when authoring is live; Phase 3 showed retrospective traces sanitise away the discovery cascades and surprising ripples the schema was designed to capture. Without this prompt, every future trace continues to be fresh-agent reconstruction and the schema additions cannot pay back.
- **(next PR) BK-194: Ripple-check rewrite into two presentations.** Compact "Quick reference" index at the top of [`sdd/CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) for pre-work scanning; detailed checklist below for verify-end and reviewer use. Two presentations, one data source. Addresses the 3/9 sampled PRs in § 2.3 that missed ripples because the table was treated as closing-only. Surfaced by Phase 3 as a specific action; ships with the first live-authored trace and so doubles as the substrate's proof case.

### 4.2 Mid-term

Two ideas held without priority until conditions justify promotion:

- **ID-179: Trace schema validator** (`scripts/check_traces.py` wired into `hatch run lint`). Promote to BK-prefix when trace authoring volume justifies enforcement.
- **ID-180: Stable HTML-anchor IDs across non-spec docs under `sdd/`.** Promote once a trace aggregator exists or once the first heading-text drift breaks a trace reference.

### 4.3 Long-term: evidence-based improvement of the full authoritative-doc structure

This is the benefit the substrate was built for, and the only reason the schema effort is justified. Once enough live-authored traces accumulate, the aggregate signals — `outcome: unclear | misleading` clustered per section, `surprising_ripples` recurring on a path, co-read graphs revealing implicit coupling, `review_rounds` spiking per `audience` slice — should drive concrete restructuring of the full authoritative-doc landscape from § 1: [`CLAUDE.md`](../../CLAUDE.md), [`CONTRIBUTING.md`](../../CONTRIBUTING.md), all seven `sdd/` framework docs ([`AUTHORING`](../AUTHORING.md), [`DOCUMENTATION`](../DOCUMENTATION.md), [`CONTENT-RULES`](../CONTENT-RULES.md), [`000-process`](../000-process.md), [`DESIGN`](../DESIGN.md), [`TESTING`](../TESTING.md), [`CLAUDE-REFERENCE`](../CLAUDE-REFERENCE.md)), the ripple-check table, plus the specs / ADRs / RFCs. Where the data says a section confuses, rewrite. Where surprising ripples recur, add a ripple-check row or consolidate the missing concept into the right authority doc. Where co-reads cluster across audience slices, the docs are coupled and should either be linked or merged. Where review-round spikes correlate with an audience, that audience needs a pre-review gate.

The result: an authoritative-doc structure that evolves on evidence rather than intuition. That is the workflow-improvement programme the schema work was the precondition for.

Enabling tooling (one line): `scripts/trace_aggregate.py` to compute the cross-trace metrics above; until it exists, every analysis is hand-rolled (as this research was).

**Anti-metric.** `len(steps)` per trace is not a useful signal. Phase 3 (§ 2.3) showed trace verbosity does not predict iteration cost: ID-178 had the longest trace (18 steps) and merged in one commit, ID-176 had one of the shortest (4 steps) and required eleven commits of editorial pushback. Aggregator code that rank-orders traces by step count will surface the wrong items as "complex".

### 4.4 Settled decisions and known limitations

Closed during this research and the interview that produced § 4.1 / 4.2 / 4.3, recorded here so they are not re-opened as questions:

- *9-PR sample only.* Phase 3 covered iteration-cost regimes (1 to 22 commits) but not every audience slice. Known limitation; revisit if a counter-example surfaces.
- *Review-driven phases not modelled as schema enum.* `rebase_fix`, `address_review_thread`, `regenerate_artefacts` are real patterns in commit history but already captured by `discovery_followups`, `review_rounds`, and step-level `outcome`. Adding enum values would invite mechanical tagging.
- *No `content_churn` flag.* PR #579 is the single observation; one data point is not a pattern. Revisit if a second example surfaces.
- *Rejected schema additions (from the schema-review wave).* `effort: 1-5` step scoring (subjective, rots across authors; pain signal already at PR level); separate `reason:` field per step (overlaps with `extract:`); step-reuse tracking as schema field (reframed as aggregator metric). All three covered structurally by the fields that did ship.
- *Phase 1 and 2 aggregator scripts not retained.* The scripts that produced this doc's distributions were prototyped under `tmp/` and discarded; a future revisit will need to re-derive them from the trace data. Acceptable cost because the trace data is stable and the headline findings are anchored in PR-level evidence (§ 2.3) rather than in the aggregator output.

### 4.5 Method provenance

All evidence derives from:

- 39 trace files under [`sdd/traces/`](../traces/) (committed in PR #608 and the per-item follow-ups: BK-176, BK-179, BK-184, BK-187, BK-188–190, BUG-182, BUG-186–194, ID-175–178).
- Merged PRs #579, #582, #590, #591, #592, #597, #604, #606, #607 fetched via `gh pr view --json files,commits,reviews`.
- [`sdd/BACKLOG-DONE.md`](../BACKLOG-DONE.md) § Unreleased for the audience-taxonomy derivation.

Phase 1 and 2 aggregator scripts were prototyped under `tmp/` during the investigation; they are not retained because the findings they produced are now in this doc and the trace data is stable enough for re-derivation.
