# Research: RFC-0019 Phase 0, does a rule-based selector earn its build?
<!-- doc: repo-only -->

**Date:** 2026-10-04
**Backlog items:** BK-403, BK-404, ID-266
**Status:** Answered: **stop for the D5 selector; RFC-0019 stays Draft**. Point-in-time snapshot per [`sdd/000-process.md` § Document types](../../000-process.md#document-types). It runs the Phase 0 row of [RFC-0019 § Roadmap](../../rfcs/rfc-0019-two-speed-test-gate.md#roadmap) against targets the maintainer fixed before the run ([`plan.md`](plan.md), commit `3bac9c4e7`). Every script and result file named below sits beside this report, and the rule sets were frozen at commit `482d07add` before either replay ran.

## Question

Under the precision rule set (RFC-0019 D5 layers 1 to 4), would typical
code diffs here select few enough tests, safely enough, to justify building
the selector (Phase 1)?

## Answer

**Stop, for the selector as D5 designs it. Typical code diffs still run the
full suite, so it misses both fixed thresholds.** The motivation is
unaffected; what the run shows is where a better idea has to cut (§ Why typical
diffs fall back to FULL).

| Fixed target (precision rule set) | Target | Measured | Met |
| --- | --- | --- | --- |
| Median wall-clock share | ≤ 50% | **100%** | — |
| FULL-fallback rate | ≤ 30%, stop above 50% | **72.6%** (77 of 106) | — |
| Reader inventory, two-method agreement | 0 unresolved one-method readers | 0 (35 investigated and added) | Yes |
| Seeds | 0 misses, every pinned mode met | 26 of 26 pins met; 20 of 20 known failures confirmed | Yes |
| Historical misses, deterministic and selector-reachable | 0 | 1 on the frozen table, plus 3 runs D7 counts as defects for lack of evidence | — |

Both stop conditions fire independently (`summarize_h.py results/h_replay.jsonl`):
the median wall-clock share exceeds 50%, and the FULL rate exceeds 50%. The
miss policy's fix-and-rerun step was not performed: a rerun cannot move the
FULL rate or the saving, which decide the stop on their own.

**The stop is not an artifact of the coarsest rows.** A post-hoc sensitivity
run (`sensitivity.py`, *not* a verdict input) takes `pyproject.toml` script
and lint-config edits and every `.github/**` edit outside `ci.yml` and
`.github/actions/` out of the FULL row. The FULL rate falls only to 54.7% (58
of 106) and the median wall-clock share stays at 100%.

**What does narrow, narrows well.** Of the 29 diffs the precision rule set
selected, the median selects 19.3% of tests, and 12 of the 29 run under 2% of
the suite's estimated time (`h_replay.jsonl`, precision rows with mode
SELECTED). Selection is sound where it applies; it applies to too few diffs.

## Why typical diffs fall back to FULL

**Most code PRs here touch a file that every test depends on, or a project
file D5 treats as global.** D5's FULL row alone fires on 59 of the 106. Per
PR, every FULL reason that fired (`summarize_h.py`, `full_reasons_any`;
`.github/**` and `pyproject.toml` counted from `h_replay.jsonl`'s reasons; a
PR can carry several):

| Reason | PRs |
| --- | --- |
| D5's FULL row: `pyproject.toml` | 39 |
| D5's FULL row: `.github/**` (`ci.yml` in 20 of them) | 32 |
| `src/` module reaching `tests/conftest.py` (`_store.py`, `_memory.py`, `_stream.py`) | 14 |
| `src/` module reaching fixture infrastructure (`_backend.py`, `aio/_async_backend.py`, `_cassettes.py`) | 13 |
| `scripts/<x>.py` with no `tests/scripts/test_<x>.py` | 7 |
| Unmatched code-class path | 6 |
| Core module (every backend reaches it) | 6 |
| Package `__init__.py` | 5 |
| Shared fixture infrastructure edited directly | 3 |
| Conftest with a session-wide hook | 1 |

- **The layer-2 FULLs are honest.** `_backend.py` and `aio/_async_backend.py`
  are the base classes every backend and the fixture registry import; the root
  `conftest.py` builds its shared fixtures from `_store.py` and `_memory.py`.
  A change there can break any test. No precision layer can narrow them.
- **`src/` diffs narrow least.** 24 of the 41 PRs touching `src/` fall back
  to FULL under precision, and their median wall-clock share is 100%; the
  pilot falls back on all 41, by construction (D5).
- **The pilot narrows almost nothing:** 100 of 106 PRs FULL. It is reported,
  not judged (RFC § Roadmap, Phase 0 exit).
- **D5 read literally falls back on all 106.** 97 of the 106 code PRs also
  change a non-code file (`sdd/traces` in 91), and D5 sends every unmatched
  path to FULL. The maintainer chose readers-from-inventory for non-code
  paths before the run (plan.md); this table uses that choice.

The cost the selector would save is also smaller than the full suite
suggests. The universe's estimated Stage-1 test time is 319.8 s
(`universe.py`), and the share figures above are shares of that.

## What the run found in RFC-0019 itself

**Five defects or gaps in the RFC, each found by running it; they hold
whatever is decided about building.**

1. **D5 has no rule for non-code paths in a code diff.** "Anything unmatched
   → FULL" plus a `.py`-only layer 4 makes 106 of 106 PRs FULL. Resolved for
   this run by the maintainer (layer 4 over every file a test reads, directory
   scans included); an amendment would state it.
2. **D5's always-run set contradicts D7's e2e-only seed.** "A dynamic import
   whose target is not a literal puts the file in an always-run set for every
   code change" makes `test`, `test-primary` and, through an unrestricted
   conformance file, `test-cross-platform` run on every diff, so D7's
   empty-survival seed for an e2e-only edit cannot pass. All 9 such files
   import names that are literals in the same file, or third-party modules.
   This run scoped the set to diffs touching `src/` (interpretation I7).
3. **`tooling-tests` can practically never be skipped for a `.py` edit.**
   `test_check_rst_roles.py`, `test_check_no_retrospective.py` and
   `test_check_spec_marks.py` read every module under `tests/`, `examples/`
   and `src/` (layer-4 table, `readers.json`), so D6's empty-survival case
   for that job exists only for non-Python edits such as a cassette.
4. **D7's escape classes have no home for a cross-test resource leak.**
   Two red runs (BUG-210) failed with unraisable `ResourceWarning`s whose
   victim test depends on garbage-collector timing; the leaking tests were
   selected. No D7 class fits, so D7's rule counts each as a selector defect.
5. **D7's coverage cross-check would flag finalizers as missing rules.**
   In 10 of the 17 selected `src/` diffs, coverage charged lines of a changed
   module to tests the selector skipped. Every one is a finalizer or a
   background thread from an earlier test running during a later one:
   `SFTPBackend.__del__` (8 diffs), the async Azure backend's `__del__` and
   its helper, and the sync adapter's `_drain_tasks` (`oversel_explain.py`).
   A cross-check without a finalizer filter would report these as gaps.

The D4 audit (below) is a sixth finding, already anticipated by the RFC.

## Consequences for the dependent items

**The D5 selector is not built as designed; the motivation stands, so RFC-0019
stays Draft and the three items stay open, waiting for a better selection
idea.**

- **BK-403:** open, with a narrower question. A coverage map failed its PoC,
  and this run stops the D5 rule set on this repository's diff mix. A next idea
  has to remove the FULL fallback where it comes from. That means
  `pyproject.toml` and `.github/**`, which fire on 59 of the 106 PRs, and the
  base modules every test reaches. Narrowing the two coarsest rows alone is
  not enough: the sensitivity run still falls back on 54.7%.
- **BK-404 (local fast target):** open, blocked on BK-403. A local target over
  this selector would run the full suite on about 7 of 10 code diffs.
- **ID-266 (CI fast lane):** open, blocked on BK-403 for the same reason. The
  `merge-candidate` lane mechanics (D1 to D3) are untouched by this run.
- **Meanwhile:** the selection-free track (BUG-301, BK-401, BK-400) shortens
  the full gate that every PR pays at least once, at no risk of skipping a
  test.

---

## Appendix A: method

- **Populations** (plan.md): H, the 106 code PRs of 182 squash-merged since
  2026-07-04 up to `d306e0223` (`count_code_prs.py 2026-07-04 d306e0223`);
  R, all 194 red `ci.yml` `pull_request` runs `gh run list` returned
  (`fetch_red.py 200`), of which 69 still had logs (the other 125 returned
  HTTP 410); S, 26 seeds.
- **Selector:** `selector.py` (stdlib only), reading every file from the
  commit under test through `p0tree.py`. Variants `pilot` and `precision`;
  `precision-literal` is D5 as written. Interpretations I1 to I7 are stated
  in its docstring.
- **Shares** (`metrics.py`, `universe.py`): 11,943 Stage-1 node ids from one
  `pytest --collect-only --stage=1`; 6,936 carry a measured duration in
  `.test_durations_pass1`, the rest take their file's mean or the global
  median. Fixture allowlists apply to conformance node ids by parametrize id.
  16 precision rows select a test file that no longer exists and take the
  median per-file count and time.
- **Host:** the Windows 11 dev box, Python 3.13, the worktree's hatch env.

## Appendix B: seeds (`seeds.py --confirm`, `results/seeds.jsonl`)

**26 seeds, all pinned modes met; all 20 with a known failing test
confirmed failing with the edit applied.** "Confirmed" is the PoC driver's
definition: pytest exits 1 and the known test's own JUnit case fails. The 13
PoC seeds are reused verbatim from
[`bk-403-testmon-poc/driver.py`](../bk-403-testmon-poc/driver.py).

| Seed | Origin | Pilot | Precision | Selected run (precision) |
| --- | --- | --- | --- | --- |
| `conftest-fixture`, `conftest-hypothesis`, `core-path`, `init-reexport`, `pyproject-pin` | PoC | FULL | FULL | — |
| `fixture-factory`, `fixture-toml` | PoC | FULL | SELECTED | 5,151 tests; known test failed |
| `registry-text` | PoC | FULL | SELECTED | 2,525; failed |
| `placement-ast` | PoC | FULL | SELECTED | 7,859; failed |
| `cassette-yaml` | PoC | SELECTED | SELECTED | 5,330; failed |
| `generated-features` | PoC | SELECTED | SELECTED | 383; failed |
| `backend-sftp-const`, `backend-sftp` | PoC | FULL | SELECTED | 7,311; failed |
| `strict-fixture` (`s3_moto.py`, strict cells only) | D7 | FULL | SELECTED | 5,407; failed |
| `test-module-imported` (`test_atomic.py` → `test_async_extended.py`) | D7 | FULL | SELECTED | 1,936; failed |
| `string-import` (`_http.py` via `test_capabilities.py`'s string list) | D7 | FULL | SELECTED | 7,564; failed |
| `example-assertion` | D7 | SELECTED | SELECTED | 214; failed |
| `pii-sweep-edit` | D7 | SELECTED | SELECTED | 174; failed |
| `script-own-test` (+ `test_check_traces.py`) | D7 | SELECTED | SELECTED | 162; failed |
| `registry-consumer` (`azure_replay_hns.py` → `tests/backends/azure/`) | D7 | FULL | SELECTED | 5,626; failed |
| `conftest-session-hook` | D7 | FULL | FULL | mode only, see below |
| 5 job seeds (e2e-only, scripts-only, core test, notebook, package) | D6 | 4 SELECTED, package FULL | SELECTED | job pins only |

- **The pilot's split matches the RFC's hand mapping:** 11 of the 13 PoC
  seeds FULL, the cassette and `FEATURES.md` SELECTED (D7).
- **Narrowing rules decided 15 precision seeds and 5 pilot seeds** (the
  SELECTED rows with a known test); the rest are decided by falling back.
- Selected runs apply no allowlist at run time (that is Phase 1's registry
  work), so their counts are supersets of the selection.
- **Corrections made on the seed set, before the freeze:** the
  session-hook seed is mode-only, because no one-line edit to a session hook
  fails a test cleanly (a raise in `pytest_configure` exits 3, which the
  driver does not count); the `test-module-imported` edit was changed after
  the first one failed nothing; three job pins that expected `tooling-tests`
  absent were wrong (finding 3 above); and a driver bug that passed
  `Class::method` to `-k` was fixed.
- **The committed results come from a rerun on a pristine tree.** The first
  run restored edited files in text mode, which on Windows rewrote their line
  endings, so later seeds ran on a tree that differed in line endings only.
  After a byte-exact fix and a reset, the full confirmation was rerun:
  identical outcome, and the seed worktree was clean afterwards.

## Appendix C: historical replay (`replay_h.py`, `summarize_h.py`)

| Variant | FULL | FULL rate | Median wall share | Mean wall share | Median jobs, SELECTED rows |
| --- | --- | --- | --- | --- | --- |
| Pilot | 100 of 106 | 94.3% | 100% | 94.4% | 4 of 15 |
| Precision | 77 of 106 | 72.6% | 100% | 80.8% | 10 of 15 |
| Precision, D5 literal | 106 of 106 | 100% | 100% | 100% | — |
| S1 sensitivity (post-hoc) | 58 of 106 | 54.7% | 100% | — | — |

Over-selection (`oversel.py`, coverage contexts from one local Stage-1 run
with `--cov-context=test`): over the 17 SELECTED precision diffs touching
`src/`, selected tests are a median 3.0 times the coverage-minimal set
(maximum 17.5). No gap between them is a missing rule (finding 5).

## Appendix D: red-run replay (`replay_r.py`, `r_evidence.py`)

**Precision selects in 72 of 194 red runs; 9 have a candidate miss, each
classified by D7 § Escape log with the evidence that class requires.** Test
ids exist for the 18 of those 72 whose logs survived; the other 54 are
checked at job level. A job alias maps the renamed `pyarrow24-check` to
`pyarrow-major-check`.

| Run | PR | Failure the fast lane would skip | Class | Evidence |
| --- | --- | --- | --- | --- |
| 27841382779 | BK-300 (docs, HNS tests) | `test_http.py::TestGraphSend::test_debug_log_redacts_token`, 3.14 | Environment-only | Only the 3.14 leg failed; the same test failed on unrelated BK-306 the same day; every master `ci.yml` run 2026-06-18 to 21 succeeded |
| 27835426242 | BK-306 | same test, 3.14 | Environment-only | as above |
| 26739651911 | recorder `--node` | job then named `test-primary` | Not a miss | Its failed step was `pytest tests/scripts/ -q`, today's `tooling-tests`, which the selection runs |
| 25933348126, 25932881682 | BUG-210 | unraisable `ResourceWarning` in dagster, s3 and http tests | None fits (finding 4); counts as defect | Same leaking fixture in both runs, disjoint victims; the leaking cells are selected |
| 24666811268, 24666401441 | ID-151 part 3 | `test-cross-platform` (macOS) | **Stale rule, deterministic and selector-reachable** | Conformance then lived in `tests/backends/test_conformance.py`; the rule that turns on the job for `local` fixture cells keys on `tests/backends/conformance/` |
| 24633981966 | ID-151 Dafny part 1 | `e2e` | No evidence; counts as defect | Log 410, no rerun; no static path from the diff to `tests/e2e/` |
| 24610391398 | ID-148 docs ripple | `e2e::test_roundrobin_checksum_and_memory` | Evidence incomplete; counts as defect | Same test failed on unrelated id-146 the same day; master green 2026-04-17 to 20; no unchanged rerun, which D7 requires |

The pilot carries the same candidates except the two BUG-210 runs, BK-306
and ID-151 part 1, which it ran in full.

## Appendix E: reader inventory (D5 layer 4)

**The table passes two-method agreement: no reader is found only
statically, and the 35 found only at runtime were investigated and added.**

- **Runtime half** (`readscan.py`, `run_scans.sh`): three full Stage-1 runs,
  one at a time: default order (153.1 s), and randomised orders with seeds
  20261004 (147.4 s) and 4031 (154.0 s), each 10,968 passed. They found 67,
  68 and 67 readers; the union is 69, so 2 depend on order.
- **Static half** (`staticreads.py HEAD`): 34 readers; 862 call sites stay
  unresolved, nearly all reads of files a test writes under `tmp_path`.
- **Agreement** (`inventory.py`, `results/agreement.json`): 34 found by both,
  0 static-only, 35 runtime-only: 29 direct reads the static folder cannot
  resolve (root paths passed through parameters or loops), 3 `logging`
  source rendering, 2 `src/` code reading files (`_info.py` listing `ext/`,
  the OpenTelemetry SDK), 1 exec'd library frame. All 35 are in the table.
- **Dropped from the table, by rule:** 2,889 cassette reads (owned by their
  layer-1 row), 137 Hypothesis constant-harvesting reads (it reads every
  loaded first-party module), 951 untracked targets, 30 self-reads.
- **Two scanner bugs found on the way, both fixed before the scans that
  count:** paths were lowercased by Windows `normcase`, and a filter dropped
  every module-level read in a test module (the static half's only
  one-method reader exposed it).

## Appendix F: derived lists (`derive_lists.py HEAD`, `derived_lists.json`)

- **Core modules (6):** `_capabilities.py`, `_errors.py`, `_models.py`,
  `_path.py` and `_resolution.py` (every backend reaches them), and `_info.py`
  (import-time effect: assigns `BackendInfo.__doc__`). `_path.py` also has an
  import-time effect. The list is under the plan's soft cap of 15.
- **Rule-table size:** 18 layer-1 rows (D5's table), 6 core modules, and a
  generated layer-4 table of 1,334 read and 85 scan entries. Within the soft
  caps (25 rows, 15 modules); the layer-4 table needs no hand upkeep.

## Appendix G: class-pattern audit (D4; `audit_classes.py`, `results/class_audit.json`)

- **Literal paths:** 36 literal alternatives across the five patterns; 1
  matches no tracked file, `docs-src/reference/FEATURES.md` (BUG-302).
- **Tracked files a test reads that classify outside its jobs:** 824 files in
  2,689 reader pairs. 719 are `docs` only and 57 `docs` and `formal`: a
  docs-only PR changing them runs none of their readers today. 48 match no
  class at all, so a PR touching only them runs no check. Among them are
  `.claude/skills/*`, `.claude/agents/*`, `CONTRIBUTING.md`, `CLAUDE.md`,
  `FEATURES.md` and `infra/drift-locks/*`, all read by `tests/scripts/`
  tests. Whether each moves to a class or is accepted because a `docs-gate`
  check covers it is the maintainer's to decide (D4); this audit only lists
  them.
