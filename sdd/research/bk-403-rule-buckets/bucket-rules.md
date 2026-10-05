# Research: path buckets as an alternative selector to RFC-0019 D5
<!-- doc: repo-only -->

**Date:** 2026-10-05
**Backlog items:** BK-403, BK-404, ID-266
**Status:** Proposal, **unmeasured**. A rule set agreed in a maintainer
interview, kept as the alternative to the D5 selector that
[Phase 0](../bk-403-phase-0/report.md) stopped. Nothing here is built or
replayed.

## Question

Can a coarse, path-bucket rule set narrow local test runs (and CI runs while a
PR is not marked `merge-candidate`) where D5's precision rule set fell back to
FULL?

## Answer

**Unknown until replayed, and Phase 0's own data caps the expected gain.**
The buckets go further than Phase 0's post-hoc sensitivity run, which already
relaxed `pyproject.toml` script and lint edits and `.github/**` outside
`ci.yml` and still fell back to FULL on 54.7% of PRs (report § Answer,
`sensitivity.py`). Beyond that run, the buckets:

- take every `.github/**` edit, `ci.yml` included, off the local FULL path (Q11);
- split the rest of `pyproject.toml` by section, including coverage config and
  single-extra floors (Q2, Q6, Q12);
- send a `scripts/<x>.py` with no mapped test to `tests/scripts/` instead of
  FULL, a reason that fired on 7 PRs (Q1);
- narrow backend-only and backend-subset `src/` edits by grep (Q3, Q13).

They do **not** narrow the base modules behind Phase 0's other large FULL
reasons (`_backend.py`, `_store.py`, `_memory.py`, fixture infrastructure;
report § Why typical diffs fall back to FULL). So the replay may well still
miss the 30% target; what it can show is how far below 54.7% the extra cuts
reach.

The merge barrier is unchanged: the full gate on the merge head
(RFC-0019 D1, D2), and a selected run never asserts the coverage floor (D8.2).

## Rule set

Each changed path takes the first row it matches, so a specific row sits above
any broader row covering the same paths. A diff spanning several rows runs
their union.

| Change | Runs | Q |
| --- | --- | --- |
| `scripts/run_tests.py` | FULL | 1 |
| `scripts/**` | all of `tests/scripts/` | 1 |
| `pyproject.toml`, `tomllib` parse of old and new equal | lint only | 2 |
| `pyproject.toml`, ruff / mypy / hatch-script / coverage sections | lint, typecheck, `tests/scripts/` | 6 |
| `pyproject.toml`, `[tool.pytest.*]` or test dependencies | FULL | 6 |
| `pyproject.toml`, one extra's dependency floor | that extra's backends' Q3 set, on a fresh min-deps env; otherwise left to CI | 12 |
| One backend's own `src/` module | conformance on that backend's fixtures, `tests/backends/<backend>/`, e2e, examples, and every test file naming the module (import or string literal, by grep over `tests/`) | 3 |
| `src/` helper imported by a known subset of backends | union of those backends' Q3 sets; importers found by grep over `src/`, function-local imports included, `_registry.py` excluded | 13 |
| Other `src/` | FULL | — |
| `sdd/formal/**` | `tests/scripts/`, the doc checks, formal verification, `tests/backends/dafny/`; the generated `MemoryBackend-py/` must be regenerated first | 4, 5 |
| `.claude/**`, `sdd/**`, `docs-src/**` | `tests/scripts/` and the doc checks | 4 |
| Test file only | that file and the tests that import or read it as text | 8 |
| `conftest.py` | every test under its directory | 8 |
| Cassettes | `tests/backends/<backend>/`, conformance on that backend's replay fixtures, the PII sweep | 9 |
| `examples/notebooks/**` | notebooks job | 10 |
| `examples/**` | examples job, `tests/test_examples.py`, `tests/test_snippets.py`, `tests/backends/conformance/test_examples.py` | 10 |
| `.github/**` | locally lint and `tests/scripts/`; the PR needs a full CI run | 11 |
| Anything unmatched | FULL | 15 |

Cross-cutting rules:

- **Cassette tests** (replay tests and the PII sweep) are skipped unless the
  change reaches a cassette backend (Azure, Graph) through `src/`, or touches
  cassettes or cassette fixtures (Q7).
- **Cut-off:** FULL if any row is FULL, or the union exceeds about 50% of the
  estimated wall-clock time from `.test_durations_pass1` (Q14).
- **Mechanism:** one committed, stdlib-only script holds the table, prints
  `--explain` per selected test, and runs FULL on anything unmatched. Agent
  judgment never picks the bucket (Q15).

## Open edges

- Readers of a script that sit outside `tests/scripts/` (Q1).
- Tests that read `pyproject.toml` as raw text (Q2).
- Where "shared backend helper" ends and "core module" begins (Q3, Q13); D5's
  core-module list from Phase 0 (`derive_lists.py`) is the natural boundary.

## Backlog coverage (estimate, not measured)

Derivation: titles of the 85 open entries in `sdd/BACKLOG.md` on master
`669eccf` (Grep `^- \[[ ~]\]`), each sorted into a row by its title alone,
no dossier read. Roughly 85% fall under an agreed row and 60 to 65% would
get a narrowed run. FULL remains for shared `src/` modules (error types,
store facade, glob, the RFC-0017 kernel items), pytest config, test
dependencies and `run_tests.py`.

## How this was derived

A maintainer interview on 2026-10-05: the maintainer asked Q1 to Q7, Claude
asked Q8 to Q15, each answered in one sentence and confirmed or corrected by
the maintainer. Claude's only sources were RFC-0019 and the repository's file
tree; no file contents, measurements or Phase 0 results were read before the
answers. Every row is therefore a reasoned rule, not an observed one.

## Next step

Replay this rule set with Phase 0's harness (`replay_h.py`,
`summarize_h.py`, `seeds.py`) on the same 106 code PRs and the same seeds,
against the same targets in [`plan.md`](../bk-403-phase-0/plan.md). That
gives a like-for-like comparison with the stopped D5 selector.
