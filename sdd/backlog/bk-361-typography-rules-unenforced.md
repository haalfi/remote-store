# BK-361 — Typography rules are asserted in `CLAUDE.md` and enforced by nobody
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

[`CLAUDE.md` § Response style](../../CLAUDE.md#response-style) states four
typography rules: em dashes used sparingly, never `--` as an em dash
substitute, `—` as the table N/A value rather than `--` or `No`, and a closed
list of contexts where `--` survives. Nothing checks any of them.
`scripts/check_tla_no_emdash.py` is the nearest thing and reads only
`sdd/formal/tla/**/*.tla`, so it reaches none of the prose the rules govern.
The promise this sits under is the one at stake: an authority doc asserting a
convention the corpus does not follow misleads the next person who reads it as
a description of the corpus.

**Measured over the 318 tracked `.md` files** (`git ls-files '*.md'`, scanned
with fenced blocks and HTML comments stripped and the rule's own exemption
list applied):
- **9 uses of `--` or `---` as an em dash, across 7 files.** Three are in
  user-facing pages: `docs-src/guides/backends/sql-query.md`,
  `docs-src/guides/glob-pattern-matching.md`, and
  `docs-src/reference/api/backends/sql-query.md`.
- **73 table cells reading `No` or `no` where the rule requires `—`, across 17
  files.** Twelve sit in three specs — `014-pyarrow-filesystem-adapter.md`,
  `031-ext-dagster.md`, `045-write-result.md` — and those are capability
  tables, the exact shape the rule names.
- **23 numeric ranges written `192--214`, across 4 files.** Left unclassified
  on purpose: the exemption covers spaced spec-ID ranges, and whether an
  unspaced line-number range is the same thing is a decision this item does
  not pre-make.

**Two of the four rules are mechanical; two are not.** The `--` substitute and
the table N/A value have exact definitions. "Sparingly" has no threshold, and
measuring one first shows why inventing it would fail: per-file em dash density
across the 51 `sdd/research/` records over 500 words runs from 0.3 to 40.9 per
1000 words, a 136× spread over files nobody has called wrong. Scope a first
pass to the two absolute rules and leave density review-enforced.

**Constraints for whoever implements this.** A line-based scanner over-reports:
the scan above produced one false positive at `sdd/BACKLOG-DONE.md:3560`, where
a backtick span wraps two lines and hides a CLI flag from a per-line filter.
Multi-line backtick and comment handling is a requirement, not a refinement.
The exemption list is a closed set living in `CLAUDE.md`, so the check either
reads it there or restates it — the second is a second description and is what
[`DRIFT-RULES.md`](../DRIFT-RULES.md#rules) governs, which applies here in full
because this adds a cross-artifact check. And note the wiring trap BK-333
documents: a checker reading `.md` under `sdd/` must reach a gate that an
`sdd/`-only diff actually triggers, which is the failure `check_tla_no_emdash`
already demonstrates.

**Open question:** whether the 73 cells and 9 substitutions are corrected in
the same change or baselined the way `check_formal_trace` baselines its two
known gaps. The corpus fix is the larger half of the effort, and it is the half
that decides whether the gate can land green.

## Correction, 2026-09-28

The corpus is 399 tracked `.md` files now (`git ls-files '*.md'`), not 318.
Re-counted by a scratch pass over them (fences, HTML comments and inline code
stripped; table separators, `--8<--` and spaced spec-ID ranges skipped): 9
`--`/`---` em-dash uses in 7 files and 73 `No` table cells in 17 files, both
as stated. "Nothing checks any of them" overstates: two generator tests pin
`—` cells in generated tables (`tests/scripts/test_render_sdd_indexes.py`,
`tests/scripts/test_gen_features.py`); no checker scans prose. The "23 numeric
ranges" figure names no pattern and was not reproduced, and the
`BACKLOG-DONE.md:3560` false positive has moved. Found by the ADR-0040 § 6 conversion.
