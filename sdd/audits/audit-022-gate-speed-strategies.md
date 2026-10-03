# Audit 022 — Gate speed: what to run, and when

**Date:** 2026-10-03
**Scope:** The local pre-commit gate (`hatch run all`) and the per-PR `ci.yml`
gate at `d74445c`. The question is strategic: which work each gate should run
at which point of a change's life, not how to make a single test faster.
`ci-full.yml`, `drift-guard.yml` and `mutation.yml` are in scope only as the
backstop a narrower gate would lean on.
**Method:** CI figures are per-job and per-step timings of run
[37030933567](https://github.com/haalfi/remote-store/actions/runs/37030933567)
(BL-011, the latest code-changing master push), read through the Actions
`list_workflow_jobs` API. Local figures come from a Python 3.13 venv on a
4-core container: Stage-1 runs at `-n 4`, with per-test times from
`--junitxml` (`junit_duration_report=total`, setup and teardown included) and
aggregated by test path. Collection time comes from `pytest --collect-only`. The
coverage-core comparison ran Stage 1 twice, with `COVERAGE_CORE=ctrace` and
`=sysmon`, and compared each file's `executed_lines` in the two JSON reports.
This is a **report-only** audit; nothing was modified. The proposals are
advisory.

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low.

---

## Summary

**Both gates run the whole suite on every change, at every stage of the
change.** That is the right policy for the last gate before `master` and the
wrong one for the loop that precedes it. Locally, `hatch run all` runs all
11,932 Stage-1 tests whatever the diff touched. In CI, every push to a PR,
including each `/ship` review-round push, starts the full 29-job gate. The
repo already narrows by *file class* (`CODE_PAT`/`DOCS_PAT`/`FORMAL_PAT`/
`HOOKS_PAT`) and by *tier* (Stage 1 versus Stage 2, ADR-0032). It never
narrows by *what the change can reach*.

The proposed shape is two speeds. While work is in progress, gates run only
what a **dependency map** says the diff can affect. Once, before merge, the
full gate runs as the safety net. `ci-full.yml` stays as it is, the post-merge
backstop. A secondary finding is that the per-PR gate has drifted from the 257 s
ADR-0032 measured to 435 s. Most of the gap is queueing, not test time (H2).

| ID | Finding | Gate |
| --- | --- | --- |
| H1 | No change-scoped selection: every run pays for the whole suite | local + CI |
| H2 | The 20-job cap queues the critical-path job for 118 s | CI |
| M1 | Every in-progress PR push runs the full pre-merge gate | CI |
| M2 | Shard timings cover 64% of collected tests | CI |
| L1 | Coverage runs on the slow tracer where sysmon is available | local + CI |
| L2 | One PII regex is quadratic and costs 157 s of a local run | local |

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

Two observations show how much a map would select away:

- **`tests/scripts/` is 2,064 tests (17%) that a `src/` change cannot reach.**
  CI already runs them once, in `tooling-tests`. The local gate runs them on
  every `all`.
- **Conformance is parametrized by backend.** Of the 4,649 conformance tests,
  727 are `s3`, 563 `local`, 556 `azure`, 364 `sftp`, 353 `s3_pyarrow`, 349 `sqlblob`, 212
  `graph`, 146 `sqlquery` and 56 `http` (the backend name in the test id; 775
  `memory` and 548 with no backend id). A change to `backends/_sftp.py` reaches
  the sftp column plus `tests/backends/sftp/`, not the other seven backends.

**Why a static import map is not enough.** Conformance tests reach a backend
through the fixture registry (`tests/backends/fixtures/`), not by importing it,
so an import graph would link every conformance test to every backend. A sound
map has to be either:

1. **Coverage-derived.** Per-test contexts (`coverage run --context=test` or
   `pytest-testmon`) record which source lines each test executed. A test is
   selected when the diff touches a line or file it executed. This is precise,
   needs a periodic full run to stay fresh, and its compatibility with `xdist` has
   to be verified before relying on it.
2. **Declared.** A committed path-to-selection table in the style of
   `scripts/drift_smoke_map.py`'s `SMOKE_TARGETS`. For example `backends/_sftp.py`
   would select `tests/backends/sftp/` plus `conformance -k sftp`, and a file
   under `scripts/` would select its `tests/scripts/test_<name>.py`. Any
   unmapped path selects everything. This is cheap and reviewable, but drifts
   like any hand table, so it needs a drift check under `sdd/DRIFT-RULES.md`.

Either way, the **fail-open rule** is what keeps it safe. Anything the map
cannot place must select the full suite: `conftest.py`, `tests/_helpers.py`,
fixtures, `_store.py` and the other core modules every backend passes through,
`pyproject.toml`, and dependency or CI files.

**What must stay full.** The 95% coverage floor is a whole-suite property, so a
selected run must never assert it. It belongs to the pre-merge full run (M1)
and to `test-cov-strict`.

### H2 — The 20-job cap queues the critical path

**The PR gate's wall clock is set by when `test-primary (1)` gets a runner, not
by how long it runs.** In the measured run, its dependency `prepare-images`
finished at +42 s, but the job started at +160 s, because 29 jobs compete for
20 slots (ADR-0032). It ran 252 s and ended at +412 s; `gate` ended at +435 s.

Timeline (seconds from run creation; job duration, then start → end):

| Job | Duration | Start → end |
| --- | --- | --- |
| `test-primary (1)` | 252 | 160 → 412 |
| `test-primary (2)` | 213 | 115 → 328 |
| `test-primary-sftp` | 172 | 118 → 290 |
| `verify-formal` | 225 | 56 → 281 |
| `test (3.14, 2)` | 186 | 73 → 259 |
| `pyarrow-major-check` ×2, `typecheck` ×2, `package`, `notebooks` | 9–60 each | all started by +95 |

Six short jobs took slots ahead of the three `test-primary*` jobs. Giving the
critical path its slot first (merging the short jobs into one or two, or making
them `needs:` the primary jobs) would let `test-primary (1)` start at about +45 s
and end at about +300 s. This is an estimate from the timeline, not a
measurement.

This also explains the drift from ADR-0032's measured 257 s. The job count has
grown since, while the cap has not.

---

## 🟠 Medium

### M1 — Every in-progress push runs the pre-merge gate

**CI makes no distinction between "still working" and "about to merge".**
`ci.yml` triggers on every `pull_request` push. `cancel-in-progress` limits the
waste to superseded runs. It does not narrow what a run does.

Evidence: PR #1058 (BK-397) produced CI runs 4962, 4963, 4965 and 4966 within
20 minutes on 2026-10-03, two of them cancelled. Each run that survives pays the
full fan-out against the job cap. That fan-out is what H2 shows queueing.

The two-speed shape, using only primitives a personal account has (ADR-0032:
no merge queue):

- **In progress (draft PR, or no `ready` label):** lint, typecheck, and the H1
  map-selected tests on the primary interpreter. That is a handful of jobs.
- **Pre-merge (`ready_for_review`, or a label, or the PR is not a draft):** the
  current full `ci.yml` gate, unchanged, including the coverage floor. Branch
  protection requires its `gate` job, so nothing merges without one full green
  run on the final head.
- **Post-merge:** `ci-full.yml` as today.

The open risk is a push after the full run. A re-push to a ready PR must re-run
the full gate. The `pull_request` `synchronize` event on a non-draft PR does
this naturally, but the policy must be stated so that convenience does not
erode it.

### M2 — Shard timings cover 64% of collected tests

**`pytest-split` balances on stale data.** `.test_durations_pass1` holds 7,612
entries (`len(json.load(...))`), while Stage 1 collects 11,932. That is 64%
coverage, and unknown tests are weighted by the average. In the measured run the
two primary shards took 213 s and 172 s for the pytest step.

ADR-0032 records the refresh as a manual duty (`sdd/CI-OPERATIONS.md`
§ Durations-refresh). A strategic fix is to let `ci-full.yml`, which already
runs the full suite on every master push, publish fresh durations as an
artifact, and have the PR shards consume the latest one. The duty becomes a
pipeline instead of a reminder.

---

## 🟡 Low

### L1 — Coverage runs on the slow tracer

**On Python 3.12+, `COVERAGE_CORE=sysmon` removes almost all coverage
overhead with identical results.** Local Stage 1 at `-n 4` measured 251 s
without coverage, 310 s with the default core, and 250 s with sysmon. Covered
lines were 10,805 under both cores, and 0 files differed in `executed_lines`.
This applies to `test-primary*` (3.13) and `test-cov-s1`. `test-cov-branch` is
outside the gate, and branch coverage under sysmon needs its own check before it
is used there.

### L2 — A quadratic PII regex dominates the local run

**`bare email address` in `tests/backends/fixtures/_cassettes.py:180` costs
157 of the 160 worker-seconds of `TestCommittedCassettePIISweep`.** The pattern
`[A-Za-z0-9._%+-]+@…` restarts at every character of long base64 runs. A
leading `(?<![A-Za-z0-9._%+-])` lets a match start only at a run boundary. It
took 0.14 s and gave identical verdicts on all 478 committed cassette files
(359 azure, 119 graph) and on three seeded probes. CI already isolates the sweep
in `test-cassette-pii` (98 s step). Locally it runs inside every `all`. This is
a defect, not a strategy; it is listed so the follow-up has its evidence.

---

## Not proposed

- **More xdist workers or another `--dist` mode.** ADR-0032 measured the suite
  as CPU-bound; `-n 8/12` did not help.
- **Thread-based test execution, or free-threaded CPython.** It does not help a
  CPU-bound pytest suite under the GIL. A free-threaded build fits a separate
  thread-safety lane, not gate speed.
- **More CI shards.** These hit the same 20-job cap as H2. Sharding the
  live-backend tier re-pays fixture setup (ADR-0032).

## Proposals (advisory)

| # | Proposal | Addresses | Notes |
| --- | --- | --- | --- |
| P1 | Dependency map with fail-open rule, plus a drift check | H1 | Decide coverage-derived versus declared first; both stay fail-open |
| P2 | `hatch run` target that runs map-selected tests; `all` keeps the full run for the pre-push moment | H1 | The coverage floor is never asserted on a selected run |
| P3 | Two-speed `ci.yml`: draft runs the selected lane, ready runs the full gate | M1, H2 | ADR amending ADR-0032; the full gate stays required for merge |
| P4 | Consolidate short CI jobs so `test-primary*` start first | H2 | Lowers job count independently of P3 |
| P5 | `ci-full.yml` publishes durations; PR shards consume them | M2 | Retires the manual refresh duty |
| P6 | `COVERAGE_CORE=sysmon` on 3.12+ coverage runs | L1 | Re-measure covered lines on CI before switching |
| P7 | Anchor the email PII regex | L2 | Bug-fix protocol: failing timing test first |
