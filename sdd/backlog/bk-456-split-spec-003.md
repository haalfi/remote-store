# BK-456 — Spec 003 is too long to keep free of contradictions, so it is split
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** The maintainer, during PR #1159 (BK-449): spec 003
is "much too long to be maintained and kept correct with no inconsistencies and
contradictions". The scope and shape below are the maintainer's choices,
recorded in `sdd/decisions/062e5181-cc50-5b17-963f-e9da78bad8ee.jsonl` ("When
should spec 003 be split?": "Separate PR after BK-449"; "Which split shape
should the work follow?": "By layer, 4 files").

**Section sizes.** Not kept current here, since every edit to the spec moves
them (the dated figures below are a measurement, not a reference):
re-run `rg -n '^##+ ' sdd/specs/003-backend-adapter-contract.md` before
planning and take each section's size as the gap to the next heading. At
PR #1159 the four largest were BE-021 Error Mapping, BE-029 Root Path, BE-032
The Store Tree on the Kernel and BE-033 Interaction Protocol on the Kernel,
then BE-030, BE-008 and BE-031; the CAP- sections and most BE- operation
sections are short.

**The ripple.** `git grep -l "003-backend-adapter-contract"` outside
`sdd/decisions`, `sdd/traces` and `sdd/research` names the files that cite the
spec: specs, RFCs, ADRs, the custom-backend guide, `scripts/gen_graph.py` and
`scripts/gen_protocol_diagram.py`, `src/` modules and
`docs-src/_data/graph/graph.json`. `git grep -l
"003-backend-adapter-contract.md#"` narrows them to anchored links. Run both
before planning: the split must move every anchor a section takes with it.

**Order.** After the status-out step below (which needs no ADR), BK-457's ADR
first (the maintainer's choice, same decision log: "ADR first, then BK-456"),
then this split, then a prune of each new file against that ADR.

**Spec 003 measured against RFC-0022, 2026-10-18** (PR #1160, at master
`32a5653`). The four largest sections held 1,417 of the file's 2,197 lines
(heading-to-heading gaps, Python regex `^#{2,3} `, the last section closed at
`wc -l`). Backlog IDs occur 84 times, 38 distinct (`\b(?:BK|BUG|ID)-\d+`);
"not yet" occurs 10 times case-sensitive, 11 ignoring case. An agent's
line-range classification, not re-derivable by a command, put these ranges in
history, measurement and coverage narrative ("Known divergences … what ships
today", test tallies, "this clause used to …"): BE-021 lines 941 to 1037 and
1061 to 1216, BE-029 lines 139 to 157, 193 to 217, 295 to 339 and 386 to 426.
It put these in prescribed mechanism (named helpers, call order, probe
sequences): lines 219 to 232, 289 to 293, 489 to 513, 670, 789 to 835, 1262 to
1270, 1613 to 1641 and 1869 to 1951. The contradictions found are BUG-337.

**Prescription** (advisory):

- **Status out first, before the ADR.** Moving project status, history and
  measurement out of the spec into the owning dossiers and traces needs no
  new rule (`CONTENT-RULES.md` Rules 1 and 4 already ask it), shrinks what
  the split moves, and keeps the split PR a pure move. One PR, no clause
  reworded; what leaves names its new home.
- **Split by kind.** Decided 2026-10-19 (ADR-0048, decision log
  `sdd/decisions/d8d56944-7c57-56f1-9c46-bc7c6222fa45.jsonl`): by kind of
  truth, interface contracts as the second cut, which replaces the four-file
  layer split the bullets below still describe. A candidate cut, recorded at
  orient: 003 keeps the single-call contract (CAP, the operation sections,
  BE-031) with its outcome tables and error precedence; keys and paths
  (BE-029, BE-030, BE-032's encoding) and error mapping (BE-021) become
  function specs; BE-033 with BE-020's close the lifetime spec; BE-028 and the
  profiles an environment spec. Re-derive against the sections before the
  split PR.

- Move only in the split PR: no clause is reworded there, so its review is a
  check that text moved whole (a per-section diff of old against new is the
  gate). The prune against BK-457's ADR follows, a file per PR.
- 003 keeps Overview, Capabilities (CAP-001 to CAP-007), the Backend ABC
  operations and Concurrency (BE-028). New specs: error mapping (BE-021), root
  path (BE-029), and the contract kernel (its intro and BE-030 to BE-033). IDs
  keep their BE- prefix, so test markers, Dafny `@spec` tags and
  `check_spec_marks.py` need nothing.
- `scripts/gen_protocol_diagram.py`'s `SPEC` path follows BE-033; the
  generated block moves with it.
- Open: the new spec numbers, and whether the kernel file splits further once
  it stands alone.
