# Audit 022 — Gate speed: what to run, and when

**Date:** 2026-10-03
**Scope:** The local pre-commit gate (`hatch run all`) and the per-PR `ci.yml`
gate at `d74445c`. The question is strategic: which work each gate should run
at which point of a change's life, not how to make a single test faster.
`ci-full.yml`, `drift-guard.yml` and `mutation.yml` are in scope only as the
backstop a narrower gate would lean on.
**Predecessors on the same gates:**
- [audit-017](audit-017-dev-process-gate-topology.md) R3: one definition of
  "what validates a change", and at most one thin fast-iteration target.
- BK-271 (`sdd/BACKLOG-DONE.md`): the `/pr` gate composes `all` for code
  diffs and `lint` + `docs-gate` otherwise, and mints no new target.
- [audit-018](audit-018-ci-operations.md): the scheduled guards'
  notification surfaces. It does not cover the durations duty.

P2 and P5 below are weighed against these.
**Method:**
- **CI figures** are per-job timings from the Actions `list_workflow_jobs` API,
  for two runs on PR #1054 (BL-011):
  - the `pull_request` run
    [37028529993](https://github.com/haalfi/remote-store/actions/runs/37028529993),
    a code-changing push and the PR gate this audit is about;
  - the master-push run
    [37030933567](https://github.com/haalfi/remote-store/actions/runs/37030933567),
    used only where L3 contrasts the two.
- **Local figures** come from a Python 3.13 venv on a 4-core container:
  - Stage-1 runs at `-n 4`, with per-test times from `--junitxml`
    (`junit_duration_report=total`, setup and teardown included), aggregated by
    test path.
  - Collection counts come from `pytest --collect-only`.
  - The coverage-core comparison ran Stage 1 twice, with `COVERAGE_CORE=ctrace`
    and `=sysmon`, and compared each file's `executed_lines` in the two JSON
    reports.

This is a **report-only** audit; nothing was modified. The proposals are
advisory.

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low.

---

## Summary

**Both gates run the whole suite on every change, at every stage of the
change.** That is the right policy for the last gate before `master` and the
wrong one for the loop that precedes it.
- **Locally,** `hatch run all` runs all 11,932 Stage-1 tests whatever the diff
  touched.
- **In CI,** every push to a PR starts the full gate, including each `/ship`
  review-round push. Run 37028529993 lists 29 jobs in the jobs API: 28 ran,
  and `verify-tla` was skipped (no TLA path changed).

The repo already narrows by *file class* (`CODE_PAT`/`DOCS_PAT`/`FORMAL_PAT`/
`HOOKS_PAT`) and by *tier* (Stage 1 versus Stage 2,
[ADR-0043](../adrs/0043-tiered-ci-gate-derived-interpreter-set.md)). It never
narrows by *what the change can reach*.

The proposed shape is two speeds:
- **While work is in progress,** gates run only what a **dependency map** says
  the diff can affect.
- **Once, before merge,** the full gate runs as the safety net.

`ci-full.yml` stays as it is, the post-merge backstop.

| ID | Finding | Gate |
| --- | --- | --- |
| H1 | No change-scoped selection: every run pays for the whole suite | local + CI |
| M1 | Every in-progress PR push runs the full pre-merge gate | CI |
| M2 | Shard timings cover 70% of the tests the primary shards split | CI |
| L1 | Coverage runs on the slow tracer where sysmon is available | local + CI |
| L2 | One PII regex is quadratic and costs 157 s of a local run | local |
| L3 | The PR gate's critical path waits 30 s for a runner slot | CI |

---

## 🔴 High

### H1 — No change-scoped selection

**Neither gate can run less than the whole suite for a small diff.** The suite's
layout makes a map from changed paths to affected tests unusually cheap to
build, and the backstops that would make a narrow in-progress gate safe already
exist.

**Tests are most of the local gate.** Each of the ten members of `hatch run all`
(`pyproject.toml:563`) was timed separately with `uvx hatch run <member>`, in
order, on the same container:

| Member | Wall | Share |
| --- | --- | --- |
| `test-cov-s1` | 532 s | 80% |
| `typecheck` | 44 s | 7% |
| `docs-build` | 39 s | 6% |
| `lint` | 19 s | 3% |
| `examples` | 15 s | 2% |
| `preflight` | 9 s | 1% |
| the other four | 8 s | 1% |
| **Total** | **666 s** | |

`test-cov-s1` goes through `scripts/run_tests.py`, which caps xdist workers
(BK-277): 2 workers on this 4-core container, from `floor(4 × 0.75) − 1` in
`compute_workers`. That explains why it takes 532 s here against the 310 s of the
`-n 4` runs below. The non-test members together are 134 s, so they are not
worth a strategy of their own; this audit's selection question is about the
test member.

What one local Stage-1 run spends, by test area (`-n 4`, worker-seconds from
the JUnit report, 11,932 tests, 721 s total):

| Area | Tests | Worker-s |
| --- | --- | --- |
| `tests/backends/conformance/` | 4,649 | 185 |
| `tests/backends/fixtures/` | 210 | 160 |
| `tests/backends/sftp/` | 557 | 148 |
| `tests/scripts/` | 2,064 | 107 |
| `tests/backends/s3/` | 400 | 43 |
| everything else | 4,052 | 78 |

Two observations show how much a map would select away, and where it must not:

- **Conformance is parametrized by backend.** The 4,649 conformance tests split
  by the backend name in their test id:

    | Backend | Tests |
    | --- | --- |
    | `memory` | 775 |
    | `s3` | 727 |
    | `local` | 563 |
    | `azure` | 556 |
    | no backend id | 548 |
    | `sftp` | 364 |
    | `s3_pyarrow` | 353 |
    | `sqlblob` | 349 |
    | `graph` | 212 |
    | `sqlquery` | 146 |
    | `http` | 56 |

    A change to `backends/_sftp.py` reaches the `sftp` column plus
    `tests/backends/sftp/`. It does not reach the nine other named backend
    columns.
- **`tests/scripts/` is 2,064 tests (17%), but it is not unreachable from
  `src/`.** It reaches `src/` in two ways:
    - **By import.** `tests/scripts/test_gen_features.py` imports
      `remote_store._retry`, `remote_store.backends._http`,
      `remote_store.backends._s3_base` and `Store`.
    - **By reading source as text.**
        - `scripts/gen_features.py:259` reads `src/remote_store/_registry.py` with
          `read_text`, and `test_gen_features.py` drives it.
        - `scripts/check_test_placement.py:104` AST-walks
          `src/remote_store/backends/_*.py` when the module is loaded, and
          `test_check_test_placement.py` loads it. That test file's own
          `remote_store` imports sit inside string fixtures; its real imports are
          `ast`, `importlib.util`, `sys` and `pathlib`.

    A `Grep` for `remote_store` over `tests/scripts/` matches 21 files. That
    counts text occurrences, not dependent files. So a map has to place these per
    test file, not exclude the directory. The `ci.yml` comment above
    `tooling-tests` ("not remote_store") makes the same wrong claim.

**Which selection mechanism fits this repo.** Selection tools differ in where
their map comes from: runtime coverage, the git diff, static imports, or a
build graph. Two facts about the repo decide among them:
- **Conformance is wired at runtime.** Conformance tests reach a backend through
  the fixture registry (`tests/backends/fixtures/`, `all_fixtures()`), not by
  importing it. An import or diff map sees every conformance test depend on
  every backend, or on none of them.
- **It is one package.** `git ls-files` shows one library `pyproject.toml` (plus
  the `examples/medallion_dagster/` sub-project) and 68 `.py` files under
  `src/`. A package or build graph has one node to invalidate, so it selects
  everything.

| Mechanism | Examples | Fit here |
| --- | --- | --- |
| Runtime coverage | `pytest-testmon`, `pytest-tia`, coverage.py contexts with a small selector | Sees the registry wiring and the `tests/scripts/` imports. Blind, like every other row, to source read as text (`gen_features.py`, `check_test_placement.py`), because a tracer records executed lines, not file reads. Needs a periodically refreshed map |
| Git diff, fixture-aware | `pytest-impact` | Fixture- and conftest-aware by its own description; whether that reaches registry-built parameters is untested |
| Git diff, file-level | `pytest-picked` | Misses the registry wiring by construction; usable only as a local convenience |
| Static import graph | `grimp`, `ast` | Same blind spot as file-level diff for conformance |
| Declared table | in the style of `scripts/drift_smoke_map.py`'s `SMOKE_TARGETS` | Explainable and reviewable, but drifts like any hand table; needs a drift check under `sdd/DRIFT-RULES.md` |
| Package or build graph | Pants, Bazel, Nx, Turborepo | One package, so no selection; see Not proposed |

How mature each tool is decides how far it can be trusted. The PyPI JSON API
gave the following on 2026-10-03:

| Project | Releases | First → last release | Latest |
| --- | --- | --- | --- |
| `pytest-testmon` | 95 | 2015-06 → 2025-12 | 2.2.0 |
| `pytest-picked` | 10 | 2018-05 → 2024-11 | 0.5.1 |
| `pytest-tia` | 2 | 2026-06 → 2026-06 | 1.1.1 |
| `pytest-impact` | 1 | 2026-07 → 2026-07 | 0.1.0 |
| `python-tia` | 1 | 2018-09 → 2018-09 | 0.0.0 |

A long release history is not evidence of correctness on this repo. The
evaluation in P1 measures that. Open interactions to verify there:
- the runtime tools against `xdist`;
- the runtime tools against `pytest-cov`, since both instrument through
  coverage.py;
- non-Python inputs. `git ls-files tests` lists 485 files that are not `.py`.
  478 of them are cassettes (`Glob` `tests/**/cassettes/**/*.yaml`), 2 are
  `.gitkeep`, and 5 are other data and docs.

Either way, the **fail-open rule** is what keeps it safe. Anything the map
cannot place must select the full suite:
- `conftest.py`, `tests/_helpers.py`, and fixtures;
- `_store.py` and the other core modules every backend passes through;
- `pyproject.toml`, dependency files, and CI files;
- any `src/` change while a test that reads source as text is in the suite.
  Today those are `test_gen_features.py` and `test_check_test_placement.py`.
  Either a declared entry maps them, or they always run.

The `tests/scripts/` case shows the rule has to hold for a directory as well as
for a file: a directory is excluded only when nothing in it reaches the change.

**What must stay full.** The 95% coverage floor is a whole-suite property, so a
selected run must never assert it. It belongs to the pre-merge full run (M1)
and to `test-cov-strict`.

---

## 🟠 Medium

### M1 — Every in-progress push runs the pre-merge gate

**CI makes no distinction between "still working" and "about to merge".**
`ci.yml` triggers on every `pull_request` push. `cancel-in-progress` limits the
waste to superseded runs. It does not narrow what a run does.

Evidence from two PRs:
- **PR #1054 (BL-011):** 8 completed CI runs, all full and all green, between
  14:04 and 15:52 on 2026-10-02 (`list_workflow_runs` on its head branch). Each
  run took between 5 m 15 s and 6 m 16 s (`run_started_at` to `updated_at`).
  The last one only added a trace, but `setup` diffs the whole PR against its
  base, so the change class never drops back to docs-only.
- **PR #1058 (BK-397):** runs 4962, 4963, 4965 and 4966 within 20 minutes on
  2026-10-03, two of them cancelled.

The two-speed shape uses only primitives a personal account has; ADR-0043's
reversal clause names merge-queue capacity as missing. **The PR's draft state is
the single selector:**

- **Draft PR: in-progress lane.** Lint, typecheck, and the H1 map-selected
  tests on every supported interpreter (see the `/ship` constraint below). The
  tier is set per leg:
    - **Non-primary legs:** Stage 1, selected. No Docker.
    - **Primary leg:** Stage 2, selected, with `prepare-images`. It keeps the
      live backends, which ADR-0043 makes the per-PR carrier of the live-backend
      guarantee.

    Dropping the primary to Stage 1 would be cheaper, but a round touching
    `_s3.py` or `_sftp.py` would then see only moto or in-process SFTP until the
    close. That trade is the ADR's to make, not a default.
- **Non-draft PR: pre-merge lane.** This covers every non-draft PR, including
  one opened as non-draft and one converted from draft. It runs the current
  full `ci.yml` gate, including the coverage floor.
- **Post-merge:** `ci-full.yml` as today.

**The merge invariant needs two `ci.yml` changes.** The invariant is that
nothing merges without one full green run on the final head. Today it does not
hold under this selector:
- **Conversion runs nothing.** `ci.yml:6-7` declares `pull_request` without
  `types:`, so only `opened`, `synchronize` and `reopened` fire it. Converting a
  draft to ready with no new push starts no run. The last check on the head is
  then the draft lane's.
- **The fix has two parts:**
  - add `ready_for_review` to `types:`;
  - make branch protection require a check that only the full lane produces.
    If the draft lane also reports a job named `gate`, a selected run satisfies
    protection.

A later push to a non-draft PR fires `synchronize` and re-runs the full lane.

**The draft lane also needs a map in CI, and that is the hardest part.** The
runtime-coverage selectors H1 rates as fitting build their map from a full run
and keep it in a data file (for `pytest-testmon`, `.testmondata`). A draft-lane
job on a fresh runner has no such file. Three things have to be settled:
- **Who produces it:** the last full lane, or `ci-full.yml` on master.
- **How it reaches the PR run:** a cross-run artifact fetch or a cache, with a
  fail-open fallback to the full suite when it is missing or stale.
- **Whether one map serves all interpreters:** a map built on the primary has
  to be shown valid for the 3.11, 3.12 and 3.14 legs, or each leg needs its own.

Without these, a draft lane can only fail open to the full suite, which is
today's gate. A declared table needs none of them, since it is committed with
the code.

**`/ship` constraint.** `/ship` is the main source of in-progress pushes, but
the selector does not reach it today, and narrowing it naively would undo a
measured fix:
- **It never sees a draft.** `/pr` opens PRs through `create_pull_request` with
  no draft flag (`.claude/skills/pr/SKILL.md` step 6), and `/ship` reviews that
  open PR. P3 saves nothing for `/ship` unless `/pr` opens a draft and `/ship`
  marks it ready at its close.
- **It relies on the full interpreter matrix per round, deliberately.**
  `.claude/skills/ship/SKILL.md` § Close each round records CI going red on a
  rebase and staying red across four rounds. The failure was
  interpreter-specific, and only the local gate was being read. A primary-only
  draft lane would bring that blind spot back, which is why the draft lane above
  keeps every interpreter.
- **P2 has the same dependency.** `/ship` runs `hatch run all` before every
  push. A selected local target saves nothing in that loop unless `/ship` uses
  it for rounds and keeps `all` for its close.

### M2 — Shard timings cover 70% of the tests the primary shards split

**`pytest-split` balances on stale data.**
- **Timed:** `.test_durations_pass1` holds 7,612 entries
  (`len(json.load(...))`), none under `tests/scripts/`.
- **Collected:** the population the primary shards split was measured with
  `pytest --stage=2 --ignore=tests/scripts --deselect …TestCommittedCassettePIISweep --collect-only`.
  It collected 11,116 tests. 10,799 remain after dropping the `sftp_docker`
  ids, which xdist workers filter out.
- **Overlap:** 7,560 of those 10,799 (70%) have an entry. 52 entries name tests
  that no longer exist.
- **Effect:** unknown tests are weighted by the average. In run 37028529993 the
  two primary shards took 229 s and 200 s as jobs.

Caveat: the collection ran locally without the Stage-2 services. CI's set may
differ by the live-only fixtures.

ADR-0043 keeps the refresh as a manual duty (§ Consequences, "Unchanged
duties"; runbook in `sdd/CI-OPERATIONS.md` § Durations-refresh). The committed
file is deliberate. It is in `CODE_PAT` (`ci.yml:53-56`, a BK-319 review fix),
so a refresh or a truncated write re-runs the gate, and every run's shard split
can be reproduced from its commit.

A fix should keep that property. `ci-full.yml` already runs the full suite on
every master push. It can regenerate the durations there and open a refresh PR
when they drift past a threshold, which `CODE_PAT` then gates like any other.

The alternative, PR shards fetching durations from the last `ci-full.yml` run,
is rejected for two reasons:
- **Cost:** it needs a cross-run artifact lookup and a token in every shard job,
  plus a fallback when there is no run.
- **Reproducibility:** two runs of one commit could shard differently, and a
  bad artifact would fail every shard with no PR that introduced it.

---

## 🟡 Low

### L1 — Coverage runs on the slow tracer

**On Python 3.12+, `COVERAGE_CORE=sysmon` removes almost all coverage
overhead with identical results.** Local Stage 1 at `-n 4` measured:

| Coverage | Wall time |
| --- | --- |
| none | 251 s |
| default core | 310 s |
| `sysmon` | 250 s |

Covered lines were 10,805 under both cores, and 0 files differed in
`executed_lines`.

This applies to every job that feeds the coverage floor, found by grepping
`--cov` in `ci.yml`:
- `test-primary` (line 327);
- `test-primary-sftp` (line 371);
- `test-cassette-pii` (line 400), which carries L2's 160 worker-seconds;

and locally to `test-cov-s1`. `test-cov-branch` is
outside the gate, and branch coverage under sysmon needs its own check before it
is used there.

### L2 — A quadratic PII regex dominates the local run

**`bare email address` in `tests/backends/fixtures/_cassettes.py:180` costs
157 of the 160 worker-seconds of `TestCommittedCassettePIISweep`.**
- **Cause:** the pattern `[A-Za-z0-9._%+-]+@…` restarts at every character of
  long base64 runs.
- **Fix:** a leading `(?<![A-Za-z0-9._%+-])` lets a match start only at a run
  boundary.
- **Measured:** the anchored form took 0.14 s and gave identical verdicts on all
  478 committed cassette files (359 azure, 119 graph) and on three seeded
  probes.

CI already isolates the sweep in `test-cassette-pii`. Locally it runs inside
every `all`. This is a defect, not a strategy; it is listed so the follow-up has
its evidence.

### L3 — The PR gate's critical path waits 30 s for a runner slot

**On a `pull_request` run, the 20-job cap delays the critical path by about
30 s.**
- **In run 37028529993:** `prepare-images` finished at +42 s, and
  `test-primary (1)` started at +72 s and ended at +301 s. `gate` ended at
  +326 s.
- **The cap was full.** Sampled every 2 s from +40 s to +68 s, using each job's
  `started_at`/`completed_at` across every run in the repo that overlapped the
  window:

  | Holder | Slots |
  | --- | --- |
  | this run's `ci.yml` jobs | 17–18 |
  | CodeQL `Analyze (Python)`, started by the same `pull_request` event (run 37028529838) | 1 |
  | another PR's `verify-formal` (run 37028178879), until +70 s | 1 |
  | **Total** | **19–20** |

  The 19s are the second or two between one job ending and the next starting.
  So one slot went to a different PR's run: contention across PRs, not only
  within a run. The cap is per account, and other repos' runs, which this audit
  cannot see, may add to it.
- **Why it waits:** first-in, first-out queuing behind jobs that queued
  earlier.
  - `test-primary` needs `prepare-images` (`ci.yml:286`), so it can only queue
    from +42 s.
  - By then the jobs that need only `setup` had queued at +30 s. The six short
    jobs (`package`, `notebooks`, `typecheck` ×2, `pyarrow-major-check` ×2, 18
    to 50 s each) started at +32 to +34 s.
  - Slots freed after +42 s went first to longer jobs queued ahead of it:
    `test (3.12, 2)` at +45 s, `verify-formal` at +53 s, `test (3.14, 1)` at
    +63 s.
  - `test-primary (1)` got a slot at +72 s, when `pyarrow-major-check` and
    `typecheck (3.11)` finished.

The 30 s is a ceiling on what any reordering can recover. Ordering alone cannot
start `test-primary*` first: the other jobs would have to be gated behind a job
that finishes after `prepare-images`, and that delays them.

**The master-push figure is not this finding.** On the master push
37030933567, `test-primary (1)` waited from +42 s to +160 s. Three other
workflows held slots for that commit: `ci-full.yml` (four `test-full` jobs for
the whole window), CodeQL and Docs. A `pull_request` run does not start
`ci-full.yml`. Master-push contention is weighed against `ci-full`'s jobs, not
against `ci.yml`'s short ones.

---

## Not proposed

**The rejected options either add parallelism without reducing work, or select
by a graph this repo does not have.** The parallelism limits are ADR-0032's
measurements, which ADR-0043 adopts as its evidence: the suite is CPU-bound and
slot-limited.

- **More xdist workers or another `--dist` mode.** `-n 8/12` was no faster than
  `-n auto`.
- **Thread-based test execution, or free-threaded CPython.** It does not help a
  CPU-bound pytest suite under the GIL. A free-threaded build fits a separate
  thread-safety lane, not gate speed.
- **More CI shards.** These compete for the same 20 slots as L3. Sharding the
  live-backend tier re-pays fixture setup.

Two selection options are also not proposed, for reasons of fit rather than
parallelism:

- **A build or package graph (Pants, Bazel, Nx, Turborepo).** These tools
  select by invalidated target or package. This repo has one library package,
  so the graph has one node to invalidate. Getting per-file selection would
  mean modelling every module as a target, a migration away from the hatch
  tooling, to gain what a coverage map gives inside pytest. Nx and Turborepo
  are also JS/TS-first. Revisit if the repo splits into packages.
- **`python-tia`.** A single 0.0.0 release in 2018.

## Proposals (advisory)

**P1 to P3 carry the strategy, which is to run less while work is in progress;
P4 to P7 are independent and smaller.** None of them lifts the full pre-merge
run or the coverage floor.

| # | Proposal | Addresses | Notes |
| --- | --- | --- | --- |
| P1 | Evaluate selectors before choosing one: `pytest-testmon`, `pytest-tia` and `pytest-impact`, with the full suite as the control group. The criteria are time saved, missed failures, and how hard the tool is to run. The test cases are seeded changes that use known blind spots (see below). A further criterion is whether the map can be produced on one run and consumed by another, on another interpreter (M1) | H1 | Whichever wins stays fail-open, including for `tests/scripts/`; a declared table is the fallback if none passes |
| P2 | One thin `hatch run` target that runs map-selected tests, used for in-progress rounds; `all` stays the pre-push gate | H1 | The "one thin target" audit-017 R3 allowed, and a third branch for BK-271's `/pr` gate. The coverage floor is never asserted on a selected run. It saves nothing in `/ship` unless `/ship` uses it for rounds (M1), and only the test share of `all` is at stake (see the `all` timing) |
| P3 | Two-speed `ci.yml`: a draft PR runs the selected lane on every interpreter (Stage 2 on the primary), a non-draft PR runs the full gate | M1 | A new ADR amending ADR-0043. It needs: `ready_for_review` in `types:`; a required check only the full lane produces; a CI map source and transport (M1); and `/pr` and `/ship` changed to open as draft and mark ready at close |
| P4 | Gate the setup-only CI jobs behind `prepare-images` so `test-primary*` queue first | L3 | Recovers at most 30 s and delays the gated jobs; measure before adopting |
| P5 | `ci-full.yml` regenerates durations and opens a refresh PR when they drift | M2 | Keeps the committed file and its `CODE_PAT` gating; turns the manual duty into an automated PR |
| P6 | `COVERAGE_CORE=sysmon` on `test-primary`, `test-primary-sftp`, `test-cassette-pii` and `test-cov-s1` | L1 | Switch all four together, then re-measure covered lines on CI |
| P7 | Anchor the email PII regex | L2 | Bug-fix protocol: failing timing test first |

**P1's seeded changes.** Each one is a one-line change that makes a known test
fail, and a selector passes only if it selects that test:

- **`tests/conftest.py`:** the stage option or hypothesis profile.
- **A fixture in `tests/backends/fixtures/`:** registry-built conformance
  parameters.
- **A core module every backend passes through:** for example `_path.py` or
  `_errors.py`.
- **A package `__init__.py` re-export.**
- **A `src/` module read by a `tests/scripts/` test:** `_registry.py` through
  `gen_features.py`.
- **A committed cassette `.yaml`:** the PII sweep and replay tests.
- **`pyproject.toml`:** addopts, a pin.
- **A generated artifact:** `FEATURES.md`, the graph data.

A single miss on a seeded change means the selector fails open for that path
class or is rejected.
