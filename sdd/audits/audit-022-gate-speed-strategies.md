# Audit 022 — Gate speed: what to run, and when

**Date:** 2026-10-03
**Scope:** The local pre-commit gate (`hatch run all`) and the per-PR `ci.yml`
gate at `d74445c`. The question is strategic: which work each gate should run
at which point of a change's life, not how to make a single test faster.
`ci-full.yml`, `drift-guard.yml` and `mutation.yml` are in scope only as the
backstop a narrower gate would lean on.
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
  review-round push. Run 37028529993 ran 28 jobs, with 1 skipped.

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
  `src/`.**
  - `tests/scripts/test_gen_features.py` imports `remote_store._retry`,
    `remote_store.backends._http`, `remote_store.backends._s3_base` and `Store`.
  - It also drives `scripts/gen_features.py`, which reads
    `src/remote_store/_registry.py`.
  - `test_check_test_placement.py` imports `remote_store` at module level.
  - A `Grep` for `remote_store` over `tests/scripts/` matches 21 files.

  So a map has to place these per test file, not exclude the directory. The
  `ci.yml` comment above `tooling-tests` ("not remote_store") makes the same
  wrong claim.

**Why a static import map is not enough.** Conformance tests reach a backend
through the fixture registry (`tests/backends/fixtures/`), not by importing it,
so an import graph would link every conformance test to every backend. A sound
map has to be either:

1. **Coverage-derived.** Per-test contexts (`coverage run --context=test` or
   `pytest-testmon`) record which source lines each test executed. A test is
   selected when the diff touches a line or file it executed.
   - It is precise, and would pick up the `tests/scripts/` dependencies above
     on its own.
   - It needs a periodic full run to stay fresh.
   - Its compatibility with `xdist` has to be verified before relying on it.
2. **Declared.** A committed path-to-selection table in the style of
   `scripts/drift_smoke_map.py`'s `SMOKE_TARGETS`.
   - For example, `backends/_sftp.py` would select `tests/backends/sftp/` plus
     `conformance -k sftp`.
   - Any unmapped path selects everything.
   - It is cheap and reviewable, but drifts like any hand table, so it needs a
     drift check under `sdd/DRIFT-RULES.md`.

Either way, the **fail-open rule** is what keeps it safe. Anything the map
cannot place must select the full suite:
- `conftest.py`, `tests/_helpers.py`, and fixtures;
- `_store.py` and the other core modules every backend passes through;
- `pyproject.toml`, dependency files, and CI files.

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
  tests on the primary interpreter. That is a handful of jobs.
- **Non-draft PR: pre-merge lane.** This covers every non-draft PR, including
  one opened as non-draft and one marked `ready_for_review`. It runs the current
  full `ci.yml` gate, unchanged, including the coverage floor. Branch protection
  requires its `gate` job, so nothing merges without one full green run on the
  final head.
- **Post-merge:** `ci-full.yml` as today.

The open risk is a push after the full run. A re-push to a non-draft PR must
re-run the full gate. The `pull_request` `synchronize` event on a non-draft PR
does this under the selector above, but the policy must be stated so that
convenience does not erode it.

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
duties"; runbook in `sdd/CI-OPERATIONS.md` § Durations-refresh). A strategic fix
lets `ci-full.yml`, which already runs the full suite on every master push,
publish fresh durations as an artifact. The PR shards then consume the latest
one, and the duty becomes a pipeline instead of a reminder.

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

This applies to `test-primary*` (3.13) and `test-cov-s1`. `test-cov-branch` is
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
  +326 s. At most 19 `ci.yml` jobs ran at once, computed from each job's
  `started_at`/`completed_at`.
- **Who held the slots:** the short jobs `package`, `notebooks`, `typecheck` ×2
  and `pyarrow-major-check` ×2 (18 to 50 s each) started at +32 to +34 s, ahead
  of the three `test-primary*` jobs.

Ordering or merging those short jobs, as in P4, would save at most the 30 s
wait.

**The master-push figure is not this finding.** On the master push
37030933567, `test-primary (1)` waited from +42 s to +160 s. Three other
workflows held slots for that commit: `ci-full.yml` (four `test-full` jobs for
the whole window), CodeQL and Docs. A `pull_request` run does not start
`ci-full.yml`. Master-push contention is weighed against `ci-full`'s jobs, not
against `ci.yml`'s short ones.

---

## Not proposed

**The rejected levers all add parallelism to a suite that is CPU-bound and
slot-limited, so none of them changes how much work a gate does.** The
constraints are ADR-0032's measurements, which ADR-0043 adopts as its evidence.

- **More xdist workers or another `--dist` mode.** `-n 8/12` was no faster than
  `-n auto`.
- **Thread-based test execution, or free-threaded CPython.** It does not help a
  CPU-bound pytest suite under the GIL. A free-threaded build fits a separate
  thread-safety lane, not gate speed.
- **More CI shards.** These compete for the same 20 slots as L3. Sharding the
  live-backend tier re-pays fixture setup.

## Proposals (advisory)

**P1 to P3 carry the strategy, which is to run less while work is in progress;
P4 to P7 are independent and smaller.** None of them lifts the full pre-merge
run or the coverage floor.

| # | Proposal | Addresses | Notes |
| --- | --- | --- | --- |
| P1 | Dependency map with fail-open rule, plus a drift check | H1 | Decide coverage-derived versus declared first; both stay fail-open, including for `tests/scripts/` |
| P2 | `hatch run` target that runs map-selected tests; `all` keeps the full run for the pre-push moment | H1 | The coverage floor is never asserted on a selected run |
| P3 | Two-speed `ci.yml`: a draft PR runs the selected lane, a non-draft PR runs the full gate | M1 | A new ADR amending ADR-0043; the full gate stays required for merge |
| P4 | Start `test-primary*` before the short CI jobs | L3 | At most about 30 s on a PR run |
| P5 | `ci-full.yml` publishes durations; PR shards consume them | M2 | Retires the manual refresh duty |
| P6 | `COVERAGE_CORE=sysmon` on 3.12+ coverage runs | L1 | Re-measure covered lines on CI before switching |
| P7 | Anchor the email PII regex | L2 | Bug-fix protocol: failing timing test first |
