# Research: a local gate on the change since the last green run
<!-- doc: repo-only -->

**Date:** 2026-10-11
**Backlog items:** BK-403, BK-404
**Status:** Answered: **adopted as `hatch run fast`, everywhere a skill ran
`hatch run all`, as an experiment to inspect in use** (§ Revisit). Point-in-time
snapshot per [`sdd/000-process.md` § Document types](../../000-process.md#document-types).
Every script and result file named below sits beside this report.

## Question

Phase 0 ([report](../bk-403-phase-0/report.md)) stopped a selector that judged
each PR's whole diff: 72.6% of code PRs fell back to the full suite. Can a
selector judged on each gate run's diff, with the bar *net time saved* rather
than zero misses, make the local gate cheap enough to run on every round?

## Answer

**Yes on this history: replayed per commit, it runs the full suite on 8.2% of
gate runs, and the modelled gate costs a third of running `all` every time.**
The maintainer set the bar before the build: misses are allowed, because CI's
full gate runs on every PR push and catches them one round later.

| Unit | Units | Full suite | Median modelled gate | Sum vs `all` every time |
| --- | --- | --- | --- | --- |
| One gate run per commit | 1,099 | 90 (8.2%) | 48.4 s | 33.0% |
| One gate run per PR (Phase 0's unit) | 155 | 37 (23.9%) | 49.0 s | 45.4% |

Derivation: `replay.py 2026-08-09 results/replay.jsonl` over the 155 PRs merged
since 2026-08-09 (`gh pr list --search "merged:>=2026-08-09"`), their branch
commits from `refs/pull/*/head`, then `summarize.py results/replay.jsonl`. The
full gate is 206.7 s, one measured run of each `all` member on the Windows dev
box (`replay.py` `STEP_SECONDS`). Phase 0's 72.6% is a different window and rule
set, so the table compares units, not selectors.

**The unit is what changed the answer.** A review round edits a few files, so
it narrows even when the PR as a whole touched `pyproject.toml` or a base module.
Those were the two largest causes of falling back to the full suite in Phase 0.

**What still runs everything, per commit** (`summarize.py`, first reason per
unit): `pyproject.toml` dependency or pytest keys 19, `_stream.py` 14, a
selection above half the suite 13, `_backend.py` 12, `_errors.py` 7,
`_cassettes.py` 5. Every `src/` module the root conftest or the fixture
registry imports is full, and those are honest: any test can break.

## What was built

`scripts/fast_gate.py`, `hatch run fast`. Its docstring holds the rules; the
ideas, each measured above or below:

- **Diff against the last green run.** The working tree, untracked files
  included, against the tree of the last passing run in this checkout,
  recorded in the git directory. A rerun with nothing changed runs nothing.
- **Member routing.** The cheap members always run; `typecheck`,
  `examples`, `notebooks` and `docs-build` (17.8 s) run only for paths they
  read. Local failures concentrate in the always-on members: of 95 `hatch run
  all` calls in the week of local transcripts that survived (2026-10-04 to
  10-11), 27 failed, and about 25 of those failed in a generator or lint check,
  not in a test (`gen_graph --check` 8, `check_capability_parity` 5,
  `gen_graph_viz --check` 4, `gen_backlogid --check` 4, ruff 3; a transcript
  scan, not committed).
- **Failure history.** The tests that failed last run are always added.
- **Self-calibrating estimate.** CI's `.test_durations_pass1` has no
  `tests/scripts/` entries, which are 146.7 of 755.3 summed seconds locally
  (`junit_times.py` over one Stage-1 run). The gate records its own JUnit
  timings per run and prefers them.

**One real round** on this branch, after the first green run: `pyproject.toml`
script keys, the gate itself and its tests changed; it selected
`tests/scripts/` and ran every non-test member in 85.4 s, of which the tests
took 43.2 s (2,320 passed). `all` on the same tree is about 207 s.

## Worker count

**12 workers is the fastest measured, and more is slower** (`time_workers.py 8
12 14 16`, one Stage-1 run each, no coverage, 20 logical CPUs):

| Workers | Wall |
| --- | --- |
| 8 | 171.3 s |
| 12 | 144.0 s |
| 14 | 148.1 s |
| 16 | 151.4 s |

The floor is not the tests: 755.3 summed seconds over 12 workers is 63 s, and
collecting the Stage-1 suite alone takes 26.2 s in one process, a cost every
worker pays. The maintainer set `RS_TEST_WORKERS=12`; the launcher's default
(14 on this box) is unchanged.

## Revisit

The maintainer chose `fast` everywhere to try it and inspect. What to inspect:

- **Misses**: a PR push whose `fast` run was green and whose CI run went red
  on a Stage-1 test failure. Each one is the path whose rule to widen.
- **Time saved**: gate wall time per round against the 206.7 s of `all`.

Misses the rules accept by design: a test that reads a changed file as text
without importing it, an import spelled as a string, and a session hook in a
conftest below the root.
