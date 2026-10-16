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
`SIM`, `TCH`, `PT`, and no `PLE`.

Measured 2026-10-16: twelve probe files, each holding one character inside a string literal
(written with `chr()`), checked with `ruff check --isolated --select PLE` and then with
`--select RUF001,RUF002,RUF003`:

| Character | `PLE` | `RUF001` |
|---|---|---|
| zero-width space U+200B | PLE2515 | — |
| NUL, backspace, ESC | PLE2514, PLE2510, PLE2513 | — |
| right-to-left override U+202E | PLE2502 | — |
| line separator U+2028, paragraph separator U+2029, no-break space U+00A0 | — | yes |
| BOM U+FEFF mid-file, ZWJ U+200D, ZWNJ U+200C, word joiner U+2060 | — | — |

So ruff alone misses U+2028, the character behind the recorded incident, unless `RUF001`–`003`
are on, and those fire 37 times on the repo today (`ruff check src/ tests/ examples/ scripts/
--select RUF001,RUF002,RUF003 --statistics`), nearly all on `×` and `–` in prose. A scan of
2213 tracked-tree text files for the 21 code points in the plan below found 2 hits, both
deliberate: a ZWSP in `scripts/check_rst_roles.py:5` that breaks the RST-role pattern in its own
docstring, and two NBSPs in `tests/scripts/test_check_dafny_oracle_fresh.py:320`, test data for
"bash does not split on NBSP".

## CRLF cost

Measured 2026-10-16 on `sdd/process-budget.json` (bytes saved, rewritten with CRLF, restored):
`git status --porcelain` printed ` M`, `git diff --stat` printed nothing but git's "CRLF will be
replaced by LF" warning, and `check_process_budget.py` still passed. `.gitattributes` sets
`* text=auto eol=lf`, so a commit normalises the file. The cost is a tree that reads dirty with
no diff, which fails `/pr` Step 1's clean-tree pre-check and adds the path to `fast`'s changed
set.

## Hatch `{args}`

In `[tool.hatch.envs.default.scripts]`, Grep
`^[a-z][a-z0-9-]* = ["'](python|pytest|ruff|mypy|mkdocs|bash|pre-commit) ` gives 89 single-line
entries; the same pattern with `.*\{args\}` appended gives 30, so 59 lack it. Most do so by
design, such as every `*-check` alias. Array-form scripts are outside this count.

The rule in the plan below reads only aliases of the exact shape `python scripts/X.py`, with
or without ` {args}`. Measured 2026-10-16 with `tomllib` over
`[tool.hatch.envs.default.scripts]`: 21 such aliases forward `{args}`, 54 string entries have
another shape (pinned arguments, several commands, no Python), and 10 drop `{args}` while the
script's source contains `argparse` or `sys.argv`: `check-no-tracker-refs`,
`check-backend-order`, `check-ripple-parity`, `check-conda-recipe-pins`, `gen-conda-feedstock`,
`check-breaking-migration-link`, `check-custom-backend-guide`, `check-traces`,
`check-changelog-unreleased`, `check-no-retrospective`. That substring test is coarser than the
rule's; step 4 re-derives the list.

## Plan

Decided 2026-10-16 (dialog in `sdd/decisions/c29e9ca6-10af-44f2-86cd-e1db3fe67d75.jsonl`). One
script, `scripts/check_repo_traps.py`, runs three rules in one pass and declares three
`Drift-gate::` blocks without `entrypoint:` (the multi-block shape `gen_gate_inventory.py`
accepts for a single-pass script). It is wired into `lint` in `pyproject.toml`.

1. **Invisible characters, a rule.** Over `git ls-files` (skip a file that does not decode as
   UTF-8, and the `binary` patterns in `.gitattributes`), fail on any of these 21 code points,
   naming file, line, column and the `\N{…}` spelling to use instead: U+0000, U+0008, U+001A,
   U+001B, U+00A0, U+200B, U+200C, U+200D, U+2028, U+2029, U+202A–U+202E, U+2060,
   U+2066–U+2069, U+FEFF (a leading BOM included). No exemption list: rewrite the two existing
   hits as `\N{ZERO WIDTH SPACE}` and `\N{NO-BREAK SPACE}`, then confirm `check_rst_roles.py`,
   the `no-rst-roles` pre-commit hook and `test_check_dafny_oracle_fresh.py` still pass. Do not
   enable `PLE`: it would be a second driver for a subset of this rule.
2. **`write_text` without `newline=`, a rule.** AST over `scripts/**/*.py`: fail on any call
   whose function is an attribute named `write_text` and that passes no `newline` keyword. Add
   `newline="\n"` to all 14 calls in the table above. No allowlist: on an untracked target the
   argument is harmless, so the rule never has to guess what is tracked. Bounds to state:
   `open(..., "w")` and `Path.open("w")` are not checked, and neither are files outside
   `scripts/` (BUG-327 owns `sdd/*.py` scope).
3. **Hatch `{args}`, a pair.** Parse `[tool.hatch.envs.*.scripts]` with `tomllib`. For each
   string entry that is exactly `python scripts/X.py`, fail if `X.py` takes options (its AST
   holds an `add_argument(` call or reads a `sys.argv` subscript or slice) and the entry lacks
   ` {args}`. Pinned-argument, multi-command and array-form entries are exempt by their shape;
   state that bound. The script governs, the alias follows.
4. **Fix the aliases.** Re-derive the failing list with the rule itself, and add ` {args}` to
   each alias it names, after checking that the script's options make sense from the command
   line.
5. **Tests**, in `tests/scripts/test_check_repo_traps.py`: per rule, one passing and one failing
   fixture, plus the stated bounds. Build every invisible-character fixture with `chr()` or
   `\N{…}`, never the four-digit `\u` form, which tool parameters decode into the raw
   character. Mutation-check each rule by deleting its condition and watching its failing
   fixture pass.
6. **Ripples:** regenerate `sdd/GATE-INVENTORY.md` (`gen_gate_inventory.py`), check the
   `{args}` pair against `sdd/DRIFT-RULES.md` (claim space, declared authority, stated bounds),
   then close BK-444 with its trace. No CHANGELOG entry: the audience is `contributor.tooling`
   and `internal.style`.

**Built 2026-10-16. Where the build departs from the plan above:**

- Rule 1 reads `git ls-files --cached --others --exclude-standard`, not `git ls-files` alone,
  so a new file is checked before its first `git add`.
- The script is also wired into `docs-gate` as `check-repo-traps`: rule 1 reads `sdd/` and
  `docs-src/`, which reach CI through `DOCS_PAT` alone. Decision in
  `sdd/decisions/cbdb79c5-8b32-4b68-9b25-5092ca7d0ce1.jsonl`.
- Rule 1 names the `\N{…}` spelling for a `.py` file only. In any other file `\N{…}` is not an
  escape, so the message says to remove the character (PR #1152 review).
- Rule 1 skips `sdd/decisions/`, the one exemption the plan's "No exemption list" did not
  foresee: `scripts/record_decision.py` stores dialog payloads with `ensure_ascii=False`, so a
  log may hold a raw U+2028 that no edit may remove. Decision in the same log.

Step 4's rule named the same 10 aliases the substring test above did.
