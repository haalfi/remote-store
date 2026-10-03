# Research: is test selection worth adopting here? (pytest-testmon PoC)

**Date:** 2026-10-03
**Backlog items:** BK-403, BK-404, ID-266
**Status:** Answered for `pytest-testmon`; `pytest-tia` and `pytest-impact` were not run. Point-in-time snapshot per [`sdd/000-process.md` § Document types](../000-process.md#document-types). It measures [audit-022](../audits/audit-022-gate-speed-strategies.md) proposal P1; the driver behind every seed row is [`bk-403-testmon-poc/driver.py`](bk-403-testmon-poc/driver.py).

## Question

Is runtime-coverage test selection worth adopting to speed up in-progress
rounds, locally (BK-404) and in CI (ID-266)?

## Answer

**Not now.**

- **Locally, it saves real time only on leaf-code edits.** Edits to core
  modules or module-level code still run a third to a half of the suite, and
  edits to `conftest.py`, data or config run all of it (§ Why). Tests are 532 s of `hatch run all`'s 666 s (audit-022 § H1), and
  local selection does not shorten CI, which runs the full gate on every PR
  push (audit-022 § M1).
- **In CI, a map is valid only for the interpreter and dependency set it was
  built on.** Any other Python patch version or package minor version
  discards it and runs everything (Appendix C). CI installs unpinned
  (`uv pip install -e ".[dev]"`), and how often a cached map would survive is
  unmeasured.
- **Two selection-free fixes are cheaper and carry no risk of skipping a
  test:**
  - BUG-301 removes 157 of 721 Stage-1 worker-seconds (22%, audit-022 § L2
    and § H1);
  - BK-401 takes the coverage run from 310 s to 250 s at `-n 4` (19%,
    audit-022 § L1).

## When to revisit

Only if, after BUG-301 and BK-401 land, local rounds are still a measured
bottleneck. Run `pytest-tia` and `pytest-impact` against the same seeds then,
not before; the driver takes them by changing only the selected-run command.

## Why

**What selection saves depends on what the change touches, and the large
savings are confined to leaf code.** Wall time of a selected run, as a share
of the 551.3 s serial Stage-1 run, from the seed table (Appendix B):

| Kind of change | Selected run vs. full suite |
| --- | --- |
| Leaf function edit (`_sanitize_pem`, a conftest helper) | 0.9% |
| Fixture factory | 2.4% |
| Backend module-level constant (`_sftp.py`) | 37% |
| Core module (`_path.py`) | 54% |
| `conftest.py` module level | 138% (whole suite, plus failing hypothesis shrinks) |
| Data, config or generated files; a different interpreter | selection is blind or discarded; must run the full suite |

## If it is ever built

**A wrapper around testmon must widen its selection for four path classes
and override two repo defaults.**

- **Full suite** when the diff touches any tracked non-`.py` file, or a `.py`
  file with no row in the map (e.g. a re-export `__init__.py`), or when the
  map comes from another environment.
- **Plus every test that reads a changed `.py` file as text** rather than by
  import. This PoC inventoried only readers of `src/` (Appendix D); tests also
  read `tests/` and `scripts/` `.py` files as text, and those are not
  inventoried. A complete, reproducible inventory is the first task of any
  revisit.
- **Pass `--testmon-forceselect`:** `addopts`' `-m 'not live'` otherwise
  turns selection off with only a header line saying so.
- **Set `COVERAGE_CORE=ctrace`:** on 3.14 coverage defaults to `sysmon`, which
  testmon cannot use, and `filterwarnings = error` turns the warning into an
  INTERNALERROR. BK-401's `sysmon` switch must therefore stay out of any
  testmon job.

---

## Appendix A: method

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

## Appendix B: controls, map build and seeds (3.13)

**The map builds under xdist for about the cost of one parallel run and is
reusable.**

| Run | Command (extra flags) | Result | Wall |
| --- | --- | --- | --- |
| Control, serial | none | 10,998 passed, 932 skipped, 45 deselected, 2 xfailed | 551.3 s |
| Control, xdist | `-n 4` | 10,998 passed, 932 skipped, 2 xfailed | 204.0 s |
| Map build, xdist | `--testmon -n 4` | same counts | 218.0 s |
| No-change rerun | `--testmon-forceselect` | 0 run, 11 deselected | 2.2 s |

Read-only `sqlite3` queries on the built map give 11,932 `test_execution`
rows, 10,143 `file_fp` rows and 96,468 test-to-file links, in an
8,798,208-byte file (`ls -l`). No non-`.py` file appears in `file_fp`
(`count(distinct filename) where filename not like '%.py'` returns 0).

**Seeds.** Each row is a one-line edit confirmed to fail its named test with
testmon off, then a serial `--testmon-forceselect` run on a fresh copy of the
map. "Confirmed" means pytest exited 1 and the named test's own JUnit case
failed; any other exit (collection, usage or internal error, nothing
collected) does not count. `POC_CONFIRM_ONLY=1 python
sdd/research/bk-403-testmon-poc/driver.py 3.13 <map> all` re-ran the
confirmation for all 13 seeds: 13 of 13 confirmed. Shares are against the 551.3 s serial control. Command:
`python sdd/research/bk-403-testmon-poc/driver.py 3.13 <map> all`. The 13
seeds cover all eight of audit-022's P1 seed classes.

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
| generated artifact | `FEATURES.md` generated row: `MemoryBackend` → `MemoryBackendX` | **no** | 0 | 2.8 s | non-Python input |
| backend module constant | `_sftp.py`'s `_PEM_SEPARATOR` shortened | yes | 1,199 | 205.4 s (37.3%) | — |
| backend function body | `_sanitize_pem` joins with `\r\n` | yes | 3 | 4.8 s (0.9%) | — |

- **Module-level conftest:** all 11,932 tests depend on `conftest.py`; the run
  was slower than the control because 20 hypothesis tests failed and shrank.
- **`__init__.py`:** the map holds no row for `src/remote_store/__init__.py`
  (`file_fp` count 0); no function in it runs under a test. A module-level
  edit in a file with recorded functions *is* caught (the `_sftp.py` constant
  row).
- **`fixtures.toml`:** the registry's data input
  (`tests/backends/fixtures/_loader.py`). Python fixture code is selected; its
  TOML data is not.
- **Placement AST:** the 825 tests run are those that import `_azure.py`; the
  test that walks the file as text is not among them.

## Appendix C: xdist, pytest-cov, portability

**xdist and pytest-cov work with testmon; a map does not survive a change of
interpreter.**

- **xdist:** the map builds under `-n 4` and is reused by serial runs and by
  `-n 4` selected runs.
- **pytest-cov:** testmon's `--help` says collection is "forced" off under
  coverage; it was not, with pytest-cov 7.1 on 3.13. A probe over
  `tests/test_path.py` and `tests/test_errors.py` wrote the same map with and
  without `--cov=remote_store`: 77 executions, 87 fingerprints and 308 links
  each. Under `--cov` the report measures only the selected run (15% total on
  a no-change run), so a selected run must never assert the coverage floor.
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
    (major.minor per package) differs, and deletes the old one: the 3.11 copy
    afterwards held only `environment_id` 2, with all 11,932 executions.
  - **The 3.14 failures are not testmon's.** A testmon-free control on
    3.14.0rc2 (`-n 4 -p no:testmon`) gave 14 failed and 8 errors: four
    `test_bench_report.py` argparse help-format `ValueError`s in the rc's
    stdlib, the rest pydantic (`_eval_type() got an unexpected keyword
    argument`) and dagster paths. The seeded run added only the seed's
    failure.

## Appendix D: tests that read source as text

**The text-read set is larger than audit-022's two files, and this PoC did
not finish inventorying it.** What was measured, and what is known to be
missing:

- **`src/` readers, measured.** A scan of the full Stage-1 suite on 3.13 with
  [`bk-403-testmon-poc/srcreads.py`](bk-403-testmon-poc/srcreads.py) recorded 15
  test files that opened a `src/**/*.py` file other than through the import
  machinery. Only the loader's own `get_data` open counts as import, so
  reads by module-level code during collection are kept; reads made by a
  subprocess are not seen. A first scan that excluded any open with
  `importlib._bootstrap` within six frames could drop such reads; re-running
  with the narrower check (10,998 passed, 541.9 s) gave the same 15 files with
  identical per-file counts.
  - **`tests/scripts/` (8), read through the scripts they drive:**
    `test_check_capability_parity.py`, `test_check_docstring_parity.py`,
    `test_check_no_retrospective.py`, `test_check_no_tracker_refs.py`,
    `test_check_rst_roles.py`, `test_check_test_placement.py`,
    `test_gen_features.py`, `test_gen_graph.py`.
  - **Elsewhere, direct reads (2):** `tests/ext/test_contract.py:85,106` and
    `tests/backends/graph/aio/test_utils.py:173` parse or read `src/` source
    themselves.
  - **Elsewhere, unclassified (5):** `tests/aio/test_async_to_sync_adapter.py`,
    `tests/backends/graph/aio/test_auth.py`,
    `tests/backends/s3/test_write_result_pbt.py`, `tests/ext/test_observe.py`,
    `tests/ext/test_otel.py`. Their own source shows no read; the hits likely
    come from library code that renders source (`linecache`,
    `inspect.getsource`), which caches, so which file records the read can
    depend on test order.
- **Non-`src/` readers, not measured.** The scan drops paths outside `src/`.
  Known examples: `tests/backends/conformance/test_large_payload_guard.py:60-63`
  (`ast.parse` on `conformance/**/test_*.py`),
  `tests/backends/fixtures/test_registry.py:696-699` (`read_text` on
  `conformance/**/*.py`), `tests/scripts/test_check_traces.py:450`
  (`rglob("*.py")` over `scripts/`).
