# RFC-0019: Two-speed test gate with a rule-based selector

## Status

Draft, 2026-10-03. Tracked as **BK-403**; it also sets the design for BK-404
(local target) and ID-266 (CI lane). Nothing below is built. Phase 0
(§ Roadmap) decides whether the rest is built at all.

## Management Summary

**Run only the tests a change can reach while a PR is being worked on, and the
full gate rarely: at least once, on the head that is meant to merge, and
before that only when the author or a reviewer asks for it.** Today both gates
run everything on every push. The selector that picks the tests is a committed
rule set, not a runtime coverage map, and it runs the full suite whenever it
cannot place a change.

- **Every PR push, including each review and fix round:** the fast lane. Lint,
  typecheck and the selected tests, on every supported interpreter.
- **On request, and always on the merge head:** the existing full gate,
  unchanged, whenever a head is marked `merge-candidate`. The final head must
  carry a full run; the author or a reviewer may also mark an earlier head when
  a full run is useful, for example after a risky round.
- **After merge:** the existing `ci-full.yml` backstop, unchanged.

**What it costs today.**

- `hatch run all` runs all 11,932 Stage-1 tests whatever the diff touched;
  tests are 532 s of its 666 s ([audit-022](../audits/audit-022-gate-speed-strategies.md)
  § H1, per-member timing).
- `ci.yml` ran the full gate 8 times on PR #1054 in under two hours
  (audit-022 § M1, `list_workflow_runs` on its head branch). Most pushes in a
  `/ship` loop are review rounds on an open PR, so a trigger based on draft
  state would not reach them.

**Why rules and not a coverage map.** The `pytest-testmon` PoC
([research](../research/research-bk-403-testmon-poc.md)) found two blockers
that belong to the mechanism, not to selection:

- it missed the known failing test on 7 of 13 seeded changes: non-Python
  inputs, a package `__init__.py`, and source read as text (Appendix B, rows
  marked **no**);
- it discards its map on any change of Python patch version or package minor
  version (Appendix C), which makes it unusable across CI legs.

Rules see what a tracer cannot, depend only on the diff and the repository,
and can explain every test they pick.

**What the decision guards.**

1. The full gate stays the only merge barrier, enforced by branch protection on
   the exact head.
2. A selected run never claims the 95% coverage floor.
3. The selector fails open: unknown path, selector error, or a selection too
   large to save time runs the full suite.
4. The existing change-class filter (docs, formal, TLA, hooks) stays the first
   axis; a change with no code part runs the same jobs in both lanes and needs
   no merge-candidate mark.
5. Nothing is switched on before it has been measured: Phase 0 validates on
   seeded changes and historical PRs with a stop criterion fixed in advance,
   and the CI lane runs in shadow mode before it decides anything.

## Motivation

**The cost is in the loop before merge, and the existing mechanisms do not
narrow it.** The repo already narrows CI by file class (`CODE_PAT`,
`DOCS_PAT`, `FORMAL_PAT`, `TLA_PAT`, `HOOKS_PAT`, `.github/workflows/ci.yml`
`setup`) and by tier ([ADR-0043](../adrs/0043-tiered-ci-gate-derived-interpreter-set.md)).
Neither narrows by what a code change can reach: any `src/` or `tests/` edit
sets `code=true`, and `code` starts 15 jobs (`grep -c "outputs.code == 'true'"`
over `ci.yml`, `tooling-tests` counted once).

**Three lessons shape the design.**

1. **Selection by coverage map failed on this repo** (§ Management Summary).
   Its blind spots are exactly the path classes a written rule can name.
2. **Draft state is the wrong switch.** `/ship` and `/fix-pr` push most of
   their rounds after the PR is open for review, so a draft-only fast lane
   saves little. What matters is whether a head is meant to merge.
3. **`/ship` needs the full interpreter matrix per round.**
   `.claude/skills/ship/SKILL.md` § Close each round records an
   interpreter-specific red that only the matrix showed. The fast lane keeps
   every interpreter and narrows tests, not legs.

## Proposal

### D1. Two lanes, switched by a merge-candidate signal

**Every PR push runs the fast lane; the full lane runs on a head marked
`merge-candidate`, and any push clears the mark.** Draft state plays no role.
The mark is a request for a full run, not a promise that the head is final: it
is required on the merge head (D2) and allowed on any earlier head the author
or a reviewer wants checked in full, so the full gate runs at least once per PR
and otherwise rarely.

| Lane | Trigger | Runs | Coverage floor |
| --- | --- | --- | --- |
| Local fast | before every push | lint, typecheck, selected tests | — |
| Local full | recommended before marking a merge candidate; not enforced | `hatch run all` | — |
| CI fast | `opened`, `synchronize`, `reopened` | lint, typecheck, selected tests on every interpreter | — |
| CI full | `merge-candidate` label added | today's `ci.yml` | yes |
| Post-merge | master push | `ci.yml` full, `ci-full.yml` | yes |

The local fast target is the gate for every round push. `hatch run all` keeps
its meaning as the full local check; running it before marking a merge
candidate catches a red full run locally instead of in CI, but the CI full lane
is the enforced barrier.

### D2. The merge barrier is a commit status only the full lane posts

**Branch protection requires a status that a successful full run posts on the
PR's head commit; no other path can produce it.** A required *job* is not
enough: GitHub reports a required job skipped by its `if:` as passing, so a fast
run, or a run started by an unrelated label, would satisfy a required `gate` job
it skipped.

- The full lane's last step posts commit status `merge-gate: success` on
  `github.event.pull_request.head.sha` (`statuses: write`). Not on `github.sha`:
  on a `pull_request` event that is the synthetic merge commit of
  `refs/pull/<n>/merge` (which is why `setup` uses it only for the diff), and
  branch protection evaluates statuses on the head, so a status there would
  never be seen. On a master `push`, `github.sha` is the head. The fast lane
  never posts the status.
- A push creates a new head without that status, so merge is blocked until the
  full lane has passed on exactly that head. This holds by construction and
  needs no clean-up.
- Branch protection moves from the `gate` job to the `merge-gate` status. The
  `gate` job stays as the full lane's aggregator; the fast lane reports
  `gate-fast`, which is not required.
- **Fork PRs cannot merge on their own.** On a fork `pull_request` event,
  `GITHUB_TOKEN` is read-only whatever `permissions:` asks for, so no lane can
  post `merge-gate` on a fork head. To merge a fork PR, the maintainer pushes
  its head to a branch in this repository and merges from a PR on that branch,
  which runs the normal lanes. A `pull_request_target` or `workflow_run`
  follow-up that posts the status is rejected: it would give a write token to a
  workflow that acts on untrusted code. Forks are rare in this
  single-maintainer repo, so the manual path is enough.

### D3. Lane mechanics in `ci.yml`

**`setup` decides the lane from the event, and clearing the label on push makes
"add the label" the single action that requests a full run.**

- **Triggers:** `pull_request` with `types: [opened, synchronize, reopened,
  labeled]`. A `labeled` event for any other label runs nothing beyond `setup`,
  and must not cancel anything (next bullet).
- **Clearing:** on `synchronize`, `setup` removes `merge-candidate` if set
  (`pull-requests: write`). Events caused by `GITHUB_TOKEN` start no workflow,
  so this cannot loop. The step is skipped when the head repository is not
  this one (`github.event.pull_request.head.repo.full_name !=
  github.repository`). A fork's read-only token would otherwise fail `setup`,
  and with it `gate-fast`.
- **Concurrency:** the per-PR group with `cancel-in-progress`
  (`ci.yml` `concurrency`) stays for pushes and `merge-candidate`: adding the
  label cancels a fast run on the same head, and a push cancels a full run and
  clears the label. A `labeled` event for **any other label** gets a group of
  its own, so it cannot cancel a running full lane: the group expression
  appends `github.run_id` when `github.event.action == 'labeled'` and
  `github.event.label.name != 'merge-candidate'`. Without it, a bot or manual
  label would cancel the full run while `merge-candidate` stays set, and
  nothing would re-trigger it. Concurrency is workflow-level and evaluated
  before any job, so a job-level `if:` cannot prevent this.
- **Master push:** always the full lane, as today.
- **Who sets the label:** the maintainer, by hand. A skill change that has
  `/ship` set it at its close is outside this RFC (§ Open Questions 4); the
  fast-lane saving on round pushes does not depend on it.

### D4. Two axes: the class filter picks jobs, the selector picks tests

**The existing class filter keeps deciding which jobs exist; the selector only
refines what runs inside `code` jobs and never turns on a job the filter turned
off.**

- **Lanes collapse without code.** When `code=false` (docs, formal, TLA or
  hooks only), both lanes run the same jobs. That run counts as full and posts
  `merge-gate` directly, so a docs PR needs no label.
- **Locally the same split.** The `/pr` mechanical gate already composes
  `all` for code diffs and `lint` + `docs-gate` otherwise
  ([PR validation gates](../CLAUDE-REFERENCE.md#pr-validation-gates)); the
  fast target replaces only the code branch.
- **One classifier, later.** The class patterns move from `ci.yml`'s bash into
  the selector in Phase 4, once the selector is proven, so path classification
  has one home (§ Roadmap).

### D5. The selector: four layers, fail open

**Input is the diff from the merge base to HEAD (plus the working tree
locally); output is either `FULL` with a reason, or pytest arguments and
per-job flags with the rule behind each.** It is static: no test run, no
installed environment, no cached state, so one result serves every interpreter
leg. It is computed once in `setup`.

**Composition.** Layer 1 classifies each changed path; layers 2–4 then expand
the result and are always unioned, never skipped:

- If any changed path classifies as FULL, the result is FULL.
- Otherwise each path contributes its layer-1 selection, and every changed
  path, whatever its row, also contributes its layer-4 readers.
- A `src/**` path contributes its layer-2 importers, and a backend module adds
  its layer-3 backend filter.
- The union is checked against the cut-off below.

1. **Path classes**, first matching row per path. A committed table in the
   style of `scripts/drift_smoke_map.py`'s `SMOKE_TARGETS`:

   | Path class | Layer-1 selection |
   | --- | --- |
   | `tests/conftest.py`, `tests/_helpers.py`, `pyproject.toml`, `.python-version`, `.test_durations_pass1`, `.github/**`, `scripts/run_tests.py` | FULL |
   | Core modules every backend passes through (the list is part of the table) | FULL |
   | `src/remote_store/backends/_<x>.py` | none of its own; layers 2 and 3 |
   | Other `src/**/*.py` | none of its own; layer 2 |
   | `tests/**/test_*.py` | that file |
   | Cassettes under `tests/**/cassettes/<backend>/` | that backend's replay tests and the PII sweep |
   | `fixtures.toml`, `tests/backends/fixtures/<backend>.py` | that backend's conformance and `tests/backends/fixtures/` |
   | `tests/backends/fixtures/_cassettes*.py` | `tests/backends/fixtures/`, the replay backends' conformance, and the `test-cassette-pii` job |
   | `examples/notebooks/**` | no tests; the `notebooks` job |
   | Other `examples/**` | no tests; the `examples` job |
   | `tests/scripts/run_examples.py`, `tests/scripts/run_notebooks.py` | the `examples` or `notebooks` job, plus layers 2 and 4 for tests that import or read them |
   | `scripts/<x>.py` | `tests/scripts/test_<x>.py` |
   | Generated artifacts (`FEATURES.md`, graph data) | their generator and check tests |
   | Anything unmatched | FULL |

2. **Static import graph.** An `ast`-built reverse graph from each `src/`
   module to the test files that import it, through `tests/` helpers too.
   This covers leaf `src/` code.
3. **Backend axis.** A change to `src/remote_store/backends/_<x>.py` limits
   conformance to backend `<x>` and adds `tests/backends/<x>/`. The filter
   goes through the fixture registry (`fixture_params` honours an allowlist),
   not `-k`: `-k s3` also matches `s3_pyarrow` and `s3_boto3`, which
   `SMOKE_TARGETS` already works around.
4. **Text readers.** A generated table maps source globs to the tests that read
   them as text, for `src/`, `tests/` and `scripts/` alike. It extends
   `sdd/research/bk-403-testmon-poc/srcreads.py`, which covered `src/` only, to readers of
   `tests/` and `scripts/` files. Examples: `test_large_payload_guard.py`
   parses `conformance/**/test_*.py`, and `test_registry.py` reads
   `conformance/**/*.py` (research Appendix D). A conformance test edit
   therefore also selects those readers.

**Cut-off:** a selection above a threshold share of the suite runs FULL; above
it, selection saves too little to be worth the risk. Phase 0 sets the number.

### D6. Job selection inside `code`

**Each `code` job that runs fixed targets is a named target set: it runs in the
fast lane only when the selector reaches one of its targets, and runs whenever
a target cannot be placed.** The rules below apply only to non-FULL
selections, because a FULL result (D5) runs every job. A trigger path must
therefore be a layer-1 row that is not FULL, and a `code` path: a rule naming a
FULL path such as `pyproject.toml`, or a non-`code` path such as `packaging/`
(`DOCS_PAT` only), would never fire.

| Job | Fast-lane rule |
| --- | --- |
| `lint`, `typecheck` | always |
| `test`, `test-primary` | selected tests |
| `tooling-tests` | selected `tests/scripts/` tests |
| `test-primary-sftp` | selection holds `sftp_docker` tests |
| `test-cassette-pii` | a cassette or `_cassettes*.py` row in layer 1 |
| `pyarrow-major-check` | selector reaches its test files (`ci.yml` job steps) |
| `test-cross-platform` | selection holds an `os_sensitive` test (static marker scan, module-level `pytestmark` included) |
| `e2e` | selector reaches `tests/e2e/` |
| `examples` | an `examples/**` path outside `examples/notebooks/`, `tests/scripts/run_examples.py`, or a `src/` module an example imports |
| `notebooks` | an `examples/notebooks/**` path, `tests/scripts/run_notebooks.py`, or a `src/` module a code cell imports |
| `package` | a `src/` file added, deleted or renamed (wheel contents); `pyproject.toml` is FULL and so already runs it |
| `coverage-gate` | full lane only |
| `prepare-images` | a job that needs it runs |

`gate-fast` aggregates like today's `gate`: passed or skipped counts, but
`setup` must succeed, so a selector error can never pass silently.

### D7. Keeping the rules honest

**A rule table drifts, so three independent checks hold it against reality,
none of which selects anything.**

1. **Seed tests.** The PoC's 13 seeds, plus seeds for text readers and the D6
   job rules, become unit tests of the selector. Each asserts that the
   selection *contains* the known failing test. They compute selections only
   and run in seconds.
2. **Coverage cross-check**, a drift check under
   [`DRIFT-RULES.md`](../DRIFT-RULES.md). A scheduled `ci-full.yml` job records
   coverage contexts for one full run; for each `src/` file the tests that
   executed it must be a subset of what the selector picks for that file. A
   test outside it is a missing rule. Runtime data checks the rules here and
   never selects, so the testmon portability limit does not apply.
3. **Escape log.** Each full run compares its failures with the fast selection
   for the same head. A failing test the fast lane skipped is an escape, and is
   reported.

### D8. Invariants

**Five properties hold in every phase; a change that breaks one is out of scope
for this RFC.**

1. Nothing merges without a successful full run on the final head (D2).
2. A selected run never asserts the coverage floor.
3. Fail open: an unplaceable path, a selector error, or a selection over the
   cut-off runs FULL, and the run log says why.
4. Every selected test can be traced to the rule that picked it (`--explain`).
5. A selection depends only on the diff and committed files.

## Roadmap

**Five phases, each with an exit criterion fixed before it starts; Phase 0 can
stop the whole effort.**

| Phase | Goal | Deliverables | Exit |
| --- | --- | --- | --- |
| **0. Validate** | Prove rules plus a static graph are correct and worth it, before production code | Throwaway selector under `sdd/research/`; extended text-reader scan; seed run through the PoC driver; replay of historical PR diffs (selected share per diff); replay of past red CI runs, including auxiliary jobs (was the failing test or job selected?); prototypes of the marker scan and notebook import parsing | 0 seed misses, 0 historical misses, and a median selected share below a target set before the run. **Stop** if typical diffs select close to the full suite |
| **1. Develop** | Production selector and the local lane | ADR for the local part; selector with rule table, graph, backend axis, reader table and per-job flags; registry allowlist; seed unit tests; coverage cross-check job; local fast target. BK-404 stays open until its skill edits land (Open Questions 4) | Seeds green in CI; cross-check reports no gap on master |
| **2. Shape** | Local pilot, tune rules | Fast target used for real rounds; escape log of fast against the later full result; rule tuning | A pilot length fixed beforehand with 0 escapes; cut-off and core list settled by measurement |
| **3. CI shadow** | Validate the CI lane without risk | Fast lane computes and logs its selection while the full lane still runs on every push; escapes compared automatically | A shadow period fixed beforehand with 0 escapes; time saved measured |
| **4. Finalize** | Switch it on and make it maintainable | ADR amending ADR-0043; `ci.yml` triggers, label clearing, `gate-fast`, `merge-gate` status; branch protection moved to `merge-gate`; classifier migration with a history replay proving identical class outputs; runbook in `sdd/CI-OPERATIONS.md`; BK-403 closed. ID-266 stays open until its skill edits land (Open Questions 4) | Verified on a real PR: label → full → `merge-gate` on the head SHA; push → label cleared → merge blocked; unrelated label → no status, and a full run already in progress is not cancelled |

The selection-free speedups (BUG-301, BK-401, BK-400) are a separate track.
They make the full lane cheaper, which every PR still passes at least once.

## Alternatives Considered

**Every rejected option either selects with a mechanism this repo defeats, or
switches lanes on a signal that misses the review loop.**

- **Runtime coverage map (`pytest-testmon`).** Measured and rejected for
  selection (§ Management Summary). Kept as a drift oracle in D7.
- **`pytest-tia`, `pytest-impact`.** Not run. Both are runtime or diff tools
  with one or two releases (audit-022 § H1 PyPI table) and share the blind
  spots D5 layer 1 exists for. Phase 0 can run them through the same driver if
  the rule-based selector misses its exit.
- **Build or package graph (Pants, Bazel).** One library package means one node
  to invalidate (audit-022 § Not proposed).
- **Draft state as the switch.** Rejected: review rounds happen on open PRs
  (Motivation, lesson 2).
- **Full lane on approval.** Approvals here come from bots and one maintainer,
  and a push after approval needs a new approval to reach full.
- **Required `gate` job instead of a status.** Rejected: a skipped required job
  passes protection (D2).
- **Primary interpreter only in the fast lane.** Rejected: loses the
  interpreter-specific reds `/ship` relies on (Motivation, lesson 3).

## Impact

**No public API, runtime behaviour or user documentation changes; the impact is
on CI configuration, contributor tooling and two process records.**

- **Public API / backwards compatibility:** none.
- **CI:** `ci.yml` triggers, `setup`, per-job conditions, a new status; branch
  protection settings (outside the repo) move to `merge-gate`.
- **Tooling:** a selector script, a local hatch target, a registry allowlist in
  `tests/backends/fixtures/registry.py`.
- **Process:** an ADR for the local part (Phase 1) and one amending ADR-0043
  (Phase 4); `sdd/CI-OPERATIONS.md` runbook; a second departure from
  [audit-017](../audits/audit-017-dev-process-gate-topology.md) R3's "one thin
  target", after BK-271's, argued in the Phase 1 ADR.
- **Ripples to carry when built:** the ripple-check row "Test whose subject is
  outside `src/` or `scripts/`" gains the selector's rule table as a second
  place to update; a new path class needs a selector rule as well as a
  `CODE_PAT` entry until Phase 4 merges the two.

## Open Questions

1. **Primary leg tier in the fast lane.** Stage 2 keeps ADR-0043's per-PR
   live-backend guarantee; Stage 1 is cheaper but leaves `_s3.py` and
   `_sftp.py` rounds on moto and in-process SFTP until the full run.
2. **Cut-off threshold and core-module list.** Set from Phase 0 data, not
   chosen here.
3. **Name of the local target.**
4. **Skill integration.** This covers three changes:
   - `/ship` and `/fix-pr` running the fast target before round pushes;
   - `/ship` setting `merge-candidate` at its close;
   - `/pr` running the fast target instead of `all` before opening a PR.

   These are out of this RFC's scope by the maintainer's choice, but not
   without an owner. The BK-404 and ID-266 dossiers keep them in scope, so both
   items stay open until the edits land. Until then, the label is set by hand,
   and D1's local fast target is used by hand.
5. **Late failures.** The full run now comes at the close, so a failure the
   selector did not reach shows one round later than today. The escape log
   measures how often.
6. **`verify-tla` is not in `gate`'s `needs`** (`ci.yml` `gate` job), so a red
   TLA check does not block merge today. Confirm that is intended before the
   Phase 4 ADR, since D4's lane collapse covers TLA-only diffs.

**Decided while drafting** (maintainer, 2026-10-03): rules plus static graph
over a coverage map; the merge-candidate signal over draft state or approval;
auxiliary jobs get their own path rules rather than always or never running;
the class patterns move into the selector in Phase 4, not Phase 1; running
`hatch run all` before marking a merge candidate is recommended, not required.

## References

- [audit-022](../audits/audit-022-gate-speed-strategies.md): findings H1, M1, L1–L3, proposals P1–P7.
- [research-bk-403-testmon-poc.md](../research/research-bk-403-testmon-poc.md): seeds, portability, text readers.
- Dossiers: [BK-403](../backlog/bk-403-test-selector-evaluation.md),
  [BK-404](../backlog/bk-404-selected-tests-hatch-target.md),
  [ID-266](../backlog/id-266-two-speed-ci-gate.md).
- [ADR-0043](../adrs/0043-tiered-ci-gate-derived-interpreter-set.md): tiered CI gate.
- [`DRIFT-RULES.md`](../DRIFT-RULES.md): rules for D7's cross-check.
