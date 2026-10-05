# Research: path buckets as an alternative selector to RFC-0019 D5
<!-- doc: repo-only -->

**Date:** 2026-10-05
**Backlog items:** BK-403, BK-404, ID-266
**Status:** Proposal, **unmeasured**. A rule set agreed in a maintainer
interview and tightened by the review of PR #1075, kept as the alternative to
the D5 selector that [Phase 0](report.md) stopped. Nothing here is built or
replayed.

## Question

Can a coarse, path-bucket rule set narrow local test runs (and CI runs while a
PR is not marked `merge-candidate`) where D5's precision rule set fell back to
FULL?

## Answer

**Unknown until replayed, and Phase 0's own data caps the expected gain.**
Phase 0's post-hoc sensitivity run relaxed `pyproject.toml` edits under
`tool.ruff`, `tool.mypy`, `tool.bumpversion`, `project.version` and hatch
`scripts`, and `.github/**` edits outside `ci.yml` and `.github/actions/`. It
still fell back to FULL on 54.7% of PRs (report § Answer, `sensitivity.py`).
The buckets relax everything that run relaxed except hatch `test*` scripts,
which invoke the test runner and so stay FULL. Beyond that run they:

- take every `.github/**` edit, `ci.yml` included, off the local FULL path (Q11);
- relax `tool.coverage` and single-extra dependency floors (Q6, Q12);
- send a `scripts/<x>.py` with no mapped test to `tests/scripts/` instead of
  FULL. That reason fired on 7 PRs (report § Why typical diffs fall back to
  FULL, row "`scripts/<x>.py` with no `tests/scripts/test_<x>.py`",
  `summarize_h.py` `full_reasons_any`). A PR can carry several reasons, so 7
  is a ceiling on the gain, not the gain (Q1);
- narrow root docs and other non-code project files, which D5 sent to FULL as
  unmatched (row R5);
- narrow backend-only, backend-subset and `ext/` `src/` edits (Q3, Q13, R4).

They do **not** narrow the base modules behind Phase 0's other large FULL
reasons: `_backend.py`, `_store.py`, `_memory.py`, anything a root conftest
imports, and fixture infrastructure (report § Why typical diffs fall back to
FULL; rows R1 to R3 below). So the replay may well still miss the 30% target;
what it can show is how far below 54.7% the extra cuts reach.

The merge barrier is unchanged: the full gate on the merge head
(RFC-0019 D1, D2), and a selected run never asserts the coverage floor (D8.2).

## Classification

1. **Inputs.** Every change from `git diff --name-status -M` contributes its
   new path and, for a rename or delete, its old path. Importers and readers
   of an old path are computed on the base tree. A deleted or renamed `src/`
   module is FULL.
2. **Paths.** Each path takes the first row of the path table that it
   matches. Rows are ordered specific before broad, so no row is shadowed by a
   broader row above it.
3. **`pyproject.toml`.** Parsed old and new with `tomllib`, flattened to
   dotted keys, and **each changed key** classified by the key table. A
   changed key that matches no row is FULL. A parse failure is FULL.
4. **Union.** The selection is the union over all paths and keys. Any FULL
   wins.
5. **Base layer.** Every non-FULL selection also runs lint,
   `tests/scripts/`, and every reader of every changed path in Phase 0's
   [`readers.json`](readers.json). `tests/scripts/` holds the whole-tree
   readers a name grep misses: `test_gen_graph.py`, `test_gen_features.py` and
   the `test_check_*` directory scanners.
6. **Conftest hits.** When a row's reader search or grep reaches a
   `conftest.py`, the selection widens to that conftest's row.

### Path table

| Change | Runs, besides the base layer | Q |
| --- | --- | --- |
| The selector script and its table; `scripts/run_tests.py`; `scripts/gen_split_durations.py` (writes the cut-off's input) | FULL | 1, R6 |
| `.python-version`, `.test_durations_pass1`, `infra/*.py` (`tests/conftest.py` imports `infra._settings`) | FULL | R5 |
| `scripts/dafny_translate.sh`, `scripts/_dafny_classorder.py` | `tests/backends/dafny/` | R6 |
| `scripts/record_cassettes.py` | the cassette set (below) | R6 |
| `scripts/mkdocs_hooks.py` | `docs-gate` | R6 |
| `scripts/**` | nothing more | 1 |
| `pyproject.toml` | per key, see the key table | 2, 6, 12 |
| A package `__init__.py` under `src/` (`remote_store`, `backends`, `aio`, `ext`); a module in Phase 0's core-module list (`derived_lists.json`); a `src/` module imported by `tests/conftest.py`, `tests/aio/conftest.py`, `tests/e2e/conftest.py` or fixture infrastructure (AST scan; today `_store.py`, `_memory.py`, `_capabilities.py` among them) | FULL | R2 |
| A backend source: an entry of `sources` or `async_sources` in `tests/backends/fixtures/backends.toml`, a package directory (`aio/backends/_graph/`) counting as one module | the backend set of **every** backend that lists it: conformance on its fixtures, `tests/backends/<backend>/` where it exists, `tests/e2e/`, the examples job, typecheck, and every test file naming the module or a symbol it exports | 3, R1 |
| A `src/` helper whose reverse-import closure, stopping at hubs, reaches only backend sources | the union of those backends' sets. A closure reaching any non-backend `src/` module is FULL | 13, R1 |
| `ext/<name>.py`, `aio/ext/<name>.py` | `tests/ext/test_<name>.py`, the `tests/aio/ext/` tests naming the module, `tests/ext/test_contract.py` (reads every `ext/` module as text), typecheck | R4 |
| Other `src/` | FULL | — |
| `tests/conftest.py`, `tests/_helpers.py`, `tests/backends/fixtures/` `registry.py`, `_loader.py`, `_state.py`, `_live_env.py`, `_cassette_pytest.py`, `__init__.py`, `_cassettes*.py`, `*.toml` | FULL | R3 |
| `tests/backends/fixtures/<name>.py` (loaded by name from `fixtures.toml`, so a grep finds no importer) | conformance on every fixture id it registers, `tests/backends/fixtures/` | R3 |
| Any other `conftest.py` | every test under its directory; FULL if it defines a session-wide hook (RFC-0019 D5, conftest row) | 8 |
| `tests/backends/cassettes/**` | the cassette set | 9 |
| `tests/**/test_*.py` | that file, plus the tests that import or read it | 8 |
| `sdd/formal/MemoryBackend-py/**` (generated) | `check_dafny_oracle_fresh.py`, which also catches a hand edit; `tests/backends/dafny/`; `docs-gate` | 4, 5 |
| `sdd/formal/**` | formal verification, `check_dafny_oracle_fresh.py`, `tests/backends/dafny/`, `docs-gate`. The selector never regenerates files | 4, 5 |
| `docs-src/reference/api/**` | `docs-gate`, `tests/test_api_coverage.py` | 4, R7 |
| `.claude/**`, `sdd/**`, `docs-src/**` | `docs-gate` | 4 |
| Root `*.md`, `mkdocs.yml`, `codecov.yml`, `.readthedocs.yaml`, `CITATION.cff`, `context7.json`, `.pre-commit-config.yaml`, `packaging/**`, `infra/drift-locks/**`, `benchmarks/**` | `docs-gate` | R5 |
| `examples/notebooks/**` | the notebooks job | 10 |
| `examples/**` | the examples job, `tests/test_examples.py`, `tests/test_snippets.py`, `tests/backends/conformance/test_examples.py`, typecheck | 10, R7 |
| `.github/**` | nothing more locally; the PR needs a full CI run | 11 |
| Anything unmatched | FULL | 15 |

**The cassette set** is `tests/backends/<backend>/` and conformance on the
replay fixtures of each cassette backend (Azure, Graph), plus the PII sweep. It
runs only when a change reaches a cassette backend through `src/`, touches
cassettes or cassette fixtures, or changes a recorder or HTTP-stack dependency
key (`vcrpy`, `httpx`, `aiohttp`, `requests`) (Q7).

### `pyproject.toml` key table

| Changed key | Runs, besides the base layer | Q |
| --- | --- | --- |
| None (old and new parse equal) | lint only | 2 |
| `project.version`, `tool.bumpversion.*` | nothing more | R8 |
| `tool.ruff.*`, `tool.mypy.*`, `tool.coverage.*` | typecheck | 6 |
| `tool.hatch.envs.*.scripts.<name>`, `<name>` not starting with `test` | nothing more | 6 |
| One floor in `project.optional-dependencies.<extra>`, `<extra>` not `dev`, run on a fresh min-deps env | the backend set of that extra's backends; the cassette set for recorder or HTTP-stack packages. Without a min-deps env, FULL | 12, R8 |
| `project.optional-dependencies.dev`; `tool.hatch.envs.*` `features`, `dependencies` and `test*` scripts; `tool.pytest.*`; `build-system`; `project.dependencies`; `project.requires-python`; any other key | FULL | 6, R8 |

### Cut-off and mechanism

- **Cut-off (Q14):** FULL when the selection's estimated time exceeds 50% of
  the full run's estimated time. A test's time comes from
  `.test_durations_pass1`; a test absent from it takes the file's median. A
  missing or unparsable file means FULL. Jobs outside pytest (formal
  verification, notebooks, the examples job, `docs-gate`) carry a fixed cost
  in the table, set from the replay.
- **One committed script (Q15):** stdlib only. It holds both tables and
  logs `path or key → row → reason` for every input, plus `--explain` per
  selected test. `RS_SELECT=full` forces FULL. A `--verify` mode runs the
  selection and FULL on one seed and reports any failure only FULL caught,
  which is also the replay's false-negative measurement. Agent judgment never
  picks a row.

## Open edges

- The fixed costs for jobs outside pytest, and whether the base layer's
  `tests/scripts/` run eats the gain on small diffs. Both are replay outputs.
- `.test_durations_pass1` has no `sftp_docker` entries and goes stale
  (BK-400), so the cut-off underestimates the serial pass.
- `readers.json` needs the freshness check RFC-0019 D7 item 2 describes,
  or the base layer decays.

The two edges the first draft listed are empty, as checked in the review of
PR #1075: no test reads `pyproject.toml` as raw text, and no reader of
`scripts/` sits outside `tests/scripts/`.

## Backlog coverage

Unmeasured; the replay replaces any estimate. The interview's per-title
estimate (85 open entries in `sdd/BACKLOG.md` on master `669eccf`, Grep
`^- \[[ ~]\]`) recorded no enumeration a reader could check, and a backlog
item is not a diff: it ignores the CHANGELOG, trace and dossier edits every PR
carries.

## How this was derived

A maintainer interview on 2026-10-05: the maintainer asked Q1 to Q7, Claude
asked Q8 to Q15, each answered in one sentence and confirmed or corrected by
the maintainer. During the interview Claude's only sources were RFC-0019 and
the repository's file tree, so the Q rows are reasoned, not observed. The
Answer section was written afterwards, from [`report.md`](report.md). Rows
marked R1 to R8 come from the review of PR #1075, which checked the table
against the tree at `9c5087e`.

## Next step

Replay this rule set with Phase 0's harness (`replay_h.py`,
`summarize_h.py`, `seeds.py`) on the same 106 code PRs and the same seeds,
against the same targets in [`plan.md`](plan.md). That gives a like-for-like
comparison with the stopped D5 selector.
