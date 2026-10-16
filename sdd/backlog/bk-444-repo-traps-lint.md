# BK-444 — Three repo traps cost sessions retries that a check would catch before commit
<!-- doc: repo-only -->

The derivations behind the index entry, measured 2026-10-16 at the head of PR #1149.

## `write_text` without `newline=`

Grep `\.write_text\(` over `scripts/` gives 20 calls; 6 pass `newline="\n"`
(`gen_backlogid.py`, `gen_adr_digest.py`, `drift_check.py:803`, `gen_sync_kernel.py`,
`gen_python_support.py`, `gen_features.py`). The other 14, by what they write and where
(tracked per `git ls-files`):

| Call | Content | Target | Tracked |
|---|---|---|---|
| `check_process_budget.py:137` | indented JSON | `sdd/process-budget.json` | yes |
| `check_docstring_parity.py:389` | Python source | async twin under `src/remote_store/aio/` | yes |
| `gen_conda_feedstock.py:193` | YAML | `--out`, default `packaging/conda-forge/feedstock/recipe.yaml` | yes |
| `drift_check.py:374` | lock lines | `infra/drift-locks/<extra>.txt` | yes |
| `_dafny_classorder.py:66` | Python source | `sdd/formal/MemoryBackend-py/module_.py` (from `dafny_translate.sh`) | yes |
| `gen_gate_inventory.py:841` | Markdown | `sdd/GATE-INVENTORY.md` | yes |
| `check_dafny_oracle_fresh.py:315` | Python source | rebuilt copy in a work directory | — |
| `check_support_windows.py:180` | TOML | `pyproject.toml` in a work directory | — |
| `drift_feedstock.py:769` | JSON report | `--out` path plus `.tmp` | — |
| `run_mutate.py:98` | indented JSON | `coverage/gremlins/gremlins.json` | — |
| `ship_report.py:601` | Markdown | `--out`, directed to `tmp/` | — |
| `fast_gate.py:605` | one-line JSON | gate state file | — |
| `fast_gate.py:681` | one-line JSON | gate state file | — |
| `run_tests.py:307` | one-line JSON | suite-lock info file | — |

The first six are the trap: on Windows, text mode turns each `\n` into `\r\n` in a tracked
file. The last three hold no newline at all, so a rule requiring `newline=` on every call
would flag them as noise.

## Ruff `PLE`

`select` in `[tool.ruff.lint]` (`pyproject.toml`) names `E`, `F`, `W`, `I`, `UP`, `B`, `BLE`,
`SIM`, `TCH`, `PT`, and no `PLE`. Not yet measured: which `PLE25xx` rules fire on the
invisible characters a tool parameter can decode into source.

## Hatch `{args}`

In `[tool.hatch.envs.default.scripts]`, Grep
`^[a-z][a-z0-9-]* = ["'](python|pytest|ruff|mypy|mkdocs|bash|pre-commit) ` gives 89 single-line
entries; the same pattern with `.*\{args\}` appended gives 30, so 59 lack it. Most do so by
design, such as every `*-check` alias. Array-form scripts are outside this count.
