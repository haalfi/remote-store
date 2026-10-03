# Research: pytest-testmon on the full Stage-1 suite

**Date:** 2026-10-03
**Backlog items:** BK-398
**Status:** PoC complete for `pytest-testmon` only. Point-in-time snapshot per [`sdd/000-process.md` § Document types](../000-process.md#document-types). It measures [audit-022](../audits/audit-022-gate-speed-strategies.md) proposal P1 for one tool; the driver that produced every seed row is [`research-bk-398-testmon-poc.py`](research-bk-398-testmon-poc.py).

## Verdict

**Viable with fail-open rules, for one interpreter at a time.** Every seed
whose cause was a Python function or module that ran under a test was
selected, at between 0.9% and 54% of the serial control's wall time. Every
seed whose cause was not was missed. The misses fall into four path classes
that a wrapper can recognise before testmon runs; those classes must select
the full suite. A map does **not** carry across interpreters: on any other
Python, testmon discards it and runs everything. That is safe, but saves
nothing, so ID-264's CI lane needs one map per interpreter leg.

Two defaults in this repo stop testmon from working at all, and both are
silent or confusing:

- `pyproject.toml`'s `addopts` passes `-m 'not live'`, and testmon turns
  selection off whenever `-m` is used. The run header says "selection
  automatically deactivated because -m was used", then runs every test.
  `--testmon-forceselect` restores selection.
- On Python 3.14, coverage 7.16 defaults to the `sysmon` core, which cannot
  switch the per-test contexts testmon relies on. Coverage warns, and this
  repo's `filterwarnings = error` turns the warning into an INTERNALERROR
  before the first test. `COVERAGE_CORE=ctrace` works.

## Method

- **Tree:** a detached worktree at `12f8043` under `./tmp/`. Venvs per
  interpreter via `uv`, with `-e ".[dev]"` and `pytest-testmon==2.2.0`
  (coverage 7.16.2, pytest-xdist 3.8.0, pytest-cov 7.1.0). Nothing was added
  to `pyproject.toml` or `ci.yml`.
- **Host:** the 4-core container audit-022 used.
- **Interpreters:** 3.11.15, 3.12.3 and 3.13.14. For 3.14, `uv python install
  3.14` offered only 3.14.0rc2.
- **Every run** is `pytest --stage=1 -p no:benchmark`, from the worktree.
- **Repeats:** each timing is a single run, so treat differences of a few
  seconds as noise.

## Control and map build (3.13)

| Run | Command (extra flags) | Result | Wall |
| --- | --- | --- | --- |
| Control, serial | none | 10,998 passed, 932 skipped, 45 deselected, 2 xfailed | 551.3 s |
| Control, xdist | `-n 4` | 10,998 passed, 932 skipped, 2 xfailed | 204.0 s |
| Map build, xdist | `--testmon -n 4` | same counts | 218.0 s |
| No-change rerun | `--testmon-forceselect` | 0 run, 11 deselected | 2.2 s |

- **What the map holds.** Read-only `sqlite3` queries on the built map give
  11,932 `test_execution` rows, 10,143 `file_fp` rows and 96,468 test-to-file
  links, in an 8,798,208-byte file (`ls -l`).
- **Coverage.** No non-`.py` file appears in `file_fp`
  (`count(distinct filename) where filename not like '%.py'` returns 0).
- **Building under xdist works.** It cost 14 s over the xdist control on this
  run, and the no-change rerun shows the map is complete.
- **The deselected count.** The rerun's "11 deselected" is the tests left
  after testmon skips collecting unchanged files.

## Seeded changes (3.13, map from the xdist build)

Each row is a one-line edit confirmed to fail its named test with testmon off,
then a serial `--testmon-forceselect` run on a fresh copy of the map. The wall
share is against the 551.3 s serial control. Command:
`python sdd/research/research-bk-398-testmon-poc.py 3.13 <map> all`.

| Seed | Edit | Known test selected? | Tests run | Wall (share) | Class if missed |
| --- | --- | --- | --- | --- | --- |
| `conftest.py`, helper body | `RestrictedBackend` keeps every capability | yes | 32 | 5.2 s (0.9%) | — |
| `conftest.py`, module level | hypothesis `dev` profile `deadline=0.01` | yes | 11,932 | 758.6 s (138%) | — |
| fixture factory | `memory.py`'s `_factory` returns `None` | yes | 322 | 13.4 s (2.4%) | — |
| `fixtures.toml` | `live_opt_in_env` added to `[fixture.memory]` | **no** | 0 | 2.2 s | non-Python input |
| core module | `_path.py` stops rejecting NUL | yes | 4,404 | 296.3 s (53.7%) | — |
| package `__init__.py` | `"Store"` → `"Store2"` in `__all__` | **no** | 0 | 2.3 s | module with no function in the map |
| `_registry.py` via `gen_features.py` | single-quoted `register_backend('memory', …)` | **no** | 0 | 1.9 s | source read as text |
| backend module via `check_test_placement.py` | `class MemoryBackend: ...` appended to `_azure.py` | **no** | 825 | 36.4 s | source read as text |
| committed cassette | an email comment appended to one Azure cassette | **no** | 0 | 1.9 s | non-Python input |
| `pyproject.toml` pin | `httpx` extra loses `<1.0` | **no** | 0 | 1.9 s | non-Python input |
| backend module constant | `_sftp.py`'s `_PEM_SEPARATOR` shortened | yes | 1,199 | 205.4 s (37.3%) | — |
| backend function body | `_sanitize_pem` joins with `\r\n` | yes | 3 | 4.8 s (0.9%) | — |

Reading the table:

- **The module-level conftest edit.** It selects every test, because all
  11,932 tests depend on `conftest.py`. It ran slower than the control
  because 20 hypothesis tests failed and shrank.
- **The `__init__.py` miss was not on audit-022's expected list.** The map
  holds no row for `src/remote_store/__init__.py` (`file_fp` count 0). That
  module is only imports and `__all__`; no function in it runs under a test.
  A module-level edit in a file that does have recorded functions *is* caught
  (the `_sftp.py` constant row), so the blind spot is files that are
  module-level only.
- **`fixtures.toml` was also not on the expected list.** It is the registry's
  data input (`tests/backends/fixtures/_loader.py`), so the audit's fixture
  class splits in two. Python fixture code is selected; its TOML data is not.
- **The placement-AST seed.** The 825 tests it ran are those that import
  `_azure.py`. The test that walks the file as text is not among them.

## xdist, pytest-cov, portability

- **xdist:** the map builds under `-n 4` and is reused by serial runs. The
  portability runs below selected under `-n 4` as well.
- **pytest-cov:** testmon's `--help` says collection is "forced" off under
  coverage. It was not, with pytest-cov 7.1 on 3.13. A probe over
  `tests/test_path.py` and `tests/test_errors.py` wrote the same map with and
  without `--cov=remote_store`: 77 executions, 87 fingerprints and 308 links
  each. Selection under `--cov` works. The report then measures only the
  selected run (15% total on a no-change run), which confirms that a selected
  run must never assert the coverage floor.
- **Portability:** the 3.13 map was copied and the `_sftp.py` function-body
  seed run on each interpreter with `POC_EXTRA="-n 4"`.

  | Interpreter | Tests run | Wall | Note |
  | --- | --- | --- | --- |
  | 3.11.15 | 11,932 (full) | 256.0 s | map discarded |
  | 3.12.3 | 11,932 (full) | 237.5 s | map discarded |
  | 3.14.0rc2 | 0 | 19.6 s | INTERNALERROR under default `sysmon` |
  | 3.14.0rc2, `COVERAGE_CORE=ctrace` | 11,850 (full) | 195.9 s | map discarded; 15 failed, 8 errors |

  - **Why the map is discarded:** `testmon/db.py`'s
    `fetch_or_create_environment` starts a new environment when either the
    full Python version (`3.13.14`) or the installed-package string
    (major.minor per package) differs. It then deletes the old one: the 3.11
    copy afterwards held only `environment_id` 2, with all 11,932 executions.
    A map shared between interpreters is overwritten, not extended.
  - **The 3.14 failures are not testmon's.** A testmon-free control on
    3.14.0rc2 (`-n 4 -p no:testmon`) gave 14 failed and 8 errors. Four are
    `test_bench_report.py` hitting an argparse help-format `ValueError` in the
    rc's stdlib; the rest are pydantic (`_eval_type() got an unexpected keyword
    argument`) and dagster paths. The seeded run added only the seed's
    failure.

## Fail-open rules

A selected run must run the full suite when the diff touches:

1. **Any tracked non-`.py` file.** This covers `fixtures.toml`,
   `backends.toml`, cassettes, `pyproject.toml`, and lock and CI files. The
   map has no row for any of them, so testmon cannot select for them.
2. **A `.py` file with no `file_fp` row in the map.** That covers `__init__.py`
   re-export modules and new files. The rule is checkable from the map itself.
3. **Any `src/` file, for the two text-reading test files.** These are
   `tests/scripts/test_gen_features.py` and `test_check_test_placement.py`.
   They are always added to the selection: the audit's declared entry, not
   the full suite.
4. **A map from another environment.** testmon already fails open here, at
   full cost.

## Next step

- **The other tools.** Run `pytest-tia` and `pytest-impact` against the same
  seeds. The driver takes the same seed table; only the selected-run command
  changes. A declared table stays the fallback for classes 1 and 3.
- **For BK-399:**
  - a wrapper that applies rules 1 to 3 to `git diff --name-only`, then calls
    `--testmon-forceselect`;
  - the map stored locally, per interpreter.
- **For ID-264:**
  - one map per interpreter leg;
  - a cache key that includes the full Python version and the resolved
    package set, since CI's `uv pip install` is unpinned and a minor-version
    bump discards the map;
  - `COVERAGE_CORE=ctrace` in any job that runs testmon.
- **For BK-401:** its move to `sysmon` and testmon cannot share a job.
