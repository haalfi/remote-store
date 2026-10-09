# BK-414 — Sessions reach one backlog item or reference section by grep and slice
<!-- doc: repo-only -->

## Evidence (2026-10-09)

**Corpus.** The Claude Code session transcripts of this repo's project and
worktree directories: 97 `*.jsonl` files, subagent transcripts included, about
30 days of sessions (older ones are pruned). Every `tool_use` naming the target
file was counted. A Read's result was mapped to a section by matching each
returned line against the current `CLAUDE-REFERENCE.md` text, so a read taken
under an older layout lands on the section it actually returned.

**`CLAUDE-REFERENCE.md`:** 24 Reads in 15 sessions, all with `offset`/`limit`,
median 80 lines returned; 29 Greps, all `output_mode: content`.

| Section a Read mostly returned | Reads |
|---|---|
| PR validation gates | 10 |
| Pre-work index | 4 |
| Branch freshness check | 3 |
| Detailed checklist | 3 |
| Interview mode | 2 |
| GitHub PR I/O split | 2 |

Ripple-check rows are 7 of the 24. The most frequent Grep looks up the anchor
pair `branch-freshness` and `pr-validation-gates`, which `/pr`, `/fix-pr` and
`/rvw-pr` cite: 6 calls (4 as `branch-freshness|pr-validation-gates`, 2 as `id=`
forms), plus 3 that combine one of the two with other terms.

**Backlog files.** Reads: `BACKLOG.md` 33 sliced, 0 whole; `BACKLOG-DONE.md` 24
sliced, 0 whole; dossiers 16 sliced, 19 whole. Greps (66), classified by pattern:

| File | by ID | heading / outline | free text |
|---|---:|---:|---:|
| `BACKLOG.md` | 8 | 8 | 16 |
| `BACKLOG-DONE.md` | 7 | 11 | 3 |
| `sdd/backlog/` | 2 | — | 11 |

Five of the dossier text Greps are the local-machine-reference PR gate, not
lookups. The `BACKLOG-DONE.md` outline Greps (`^## `) locate `Unreleased` or
`Decided against`.

**Sizes** (current files, tokens at chars / 3.5): an open item median 576 chars
(max 785); a done entry median 792 (p90 3082, max 13211); a dossier median 3094
(p90 7090); `wc -l` gives `BACKLOG.md` 952 lines and `BACKLOG-DONE.md` 13967, so an
80-line slice is about 1.4k and 1.6k tokens. `CLAUDE-REFERENCE.md` anchored
sections: `branch-freshness` ~290, `local-toolchain` ~140,
`github-pr-io-split` ~930, `interview-mode-wiring` ~1.1k, `pr-validation-gates`
~1.7k, `pre-work-index` ~3.4k, `detailed-checklist` ~8.7k tokens.

**What the trace tags say** (`hatch run report-trace-outcomes`, 370 traces).
`BACKLOG.md` 35 tags (misleading 31, unclear 4), `CLAUDE-REFERENCE.md` 28
(misleading 8, unclear 20), the two highest. Reading all 63 tags, one is a
navigation failure (bk-328, "find the competing candidates and the next free
ID"). The rest are content: `BACKLOG.md` prescriptions and line references that
had gone stale when trusted (BK-269, BK-271, BK-272, BK-369, BK-331), and
ripple-check rows missing a trigger or disagreeing with `_schema.yml`'s
CHANGELOG rule. A lookup returns the same text, so this item's case is the
search-and-reread cycle, under a ceiling of about 3% of re-read context; the
content defects are owned elsewhere (BK-346 for the ripple-check's blind spots).

## Design (advisory)

Decided in an interview: scope is backlog lookup plus `CLAUDE-REFERENCE.md`
sections by anchor and ripple rows by trigger; shape is a new script sharing the
existing grammars; skills and a `CLAUDE.md` rule point at it; bounds are stated
in the docstring with no `Drift-gate::` block.

### Commands

`scripts/sdd_lookup.py`, read-only, with hatch aliases. Token figures as above.

| Alias | Prints | Tokens per call |
|---|---|---|
| `backlog-show <ID>...` | Every header carrying the ID, in either file, verbatim, after a location line. `--dossier` appends the dossier whole | open ~190; done median ~250, p90 ~900 |
| `backlog-find <regex> [--open\|--done\|--dossiers] [--max 20]` | One line per matching item, not per matching line | ~40 per hit, ≤ 800 at the cap |
| `backlog-outline [--done] [--section <text>]` | `##` headings with item counts; with `--section`, that section's headers | ~120; ≤ 700 for the done register |
| `ref-show <anchor\|heading> [--list]` | The section from its anchor or heading to the next heading of the same level | see the section sizes above |
| `ref-rows <trigger>` | The trigger's Pre-work row and its Detailed checklist rows, verbatim | ~300 typical, ~1.5k worst |

Output shapes:

```text
BUG-276 · open · sdd/BACKLOG.md:128 · § 1. Failures are predictable
- [ ] **BUG-276 — …**
  spec: … · effort: M · audience: user.api
  …
--- dossier (evidence: dated record; prescription: advisory, re-derive before acting) ---
<file>

BK-399 · done · sdd/BACKLOG-DONE.md:4120 · <header title> ⟶ <first matching line>

[pre-work] sdd/CLAUDE-REFERENCE.md:52
<row>
[detailed] sdd/CLAUDE-REFERENCE.md:162-206
<rows>
```

The `--dossier` banner carries `BACKLOG.md` § Item authority to the point of
reading, the one lever the tool has on the misleading tags above.

### Staying correct

- Parses on every call; no cache, no generated copy.
- Item grammar is imported from `gen_backlogid.py` (`_HEADER_RE`, `_sections`,
  `_SEP_RE`), trigger grammar from `check_ripple_parity.py` (`_blocks`,
  `_parse_pre_work`, `_parse_detailed`). Both are gated in `lint` and
  `docs-gate`, so a shape change that breaks the parse fails there first.
- Entries start at `^- \[.\] \*\*`, so the ID-less `- [x] **— …**` entries in
  § Decided against stand alone. `_HEADER_RE` needs an ID and would fold them
  into the entry above, so this one boundary is the tool's own, not imported.
- An unknown key exits 1 and lists the valid keys; never an empty success.
- `tests/scripts/test_sdd_lookup.py`: fixtures, plus one test over the live
  files that every open ID, every anchor and every Pre-work trigger resolves.

### Bounds (for the docstring, DRIFT-RULES Rule 7)

- `show` finds an ID on a header only; a prose mention is reachable by `find`.
- The released duplicate pairs `gen_backlogid.py` tolerates print every header,
  each labelled with its section.
- `ref-show` reaches anchored sections and, by heading text, the unanchored ones.
- `ref-rows` returns table rows, not the paragraphs before a table.
- Verbatim output; no judgement of currency. This tree only, not other branches.
- Not a gate: a wrong answer fails only its own tests. It compares nothing, so it
  carries no `Drift-gate::` block, and its name is outside the prefixes that
  would demand one.

### Pointers

- `CLAUDE.md` § Backlog: one rule, to query one item, entry, dossier or section
  by key, keeping Grep and sliced Read for edits and for whole-file reads a step
  requires.
- Skills: only steps that fetch a single key. Candidates are the references a
  Grep for `CLAUDE-REFERENCE\.md#|BACKLOG(-DONE)?\.md` over `.claude/skills`
  returns (20 in 6 skills on 2026-10-09); each is checked, not swept.

### Not replaced

- The Pre-work index scan before starting and the Detailed checklist at
  verify-end (`CLAUDE.md` principle 2); `ref-show` delivers the same bytes.
- The whole-dossier read at a trace's orient step.
- The whole-file exit gate (ADR-0037).
- The Read the harness requires before any Edit.
- The `rg -n '<ID>'` sweep after absorbing or deciding against an item.
- Minting through `gen-backlogid-check`.

### Acceptance measure

Re-run the transcript count about 30 days after the pointers merge: sliced Reads
and Greps on the three files per session should fall. The tag counts are not
the measure, for the reason in § Evidence.
