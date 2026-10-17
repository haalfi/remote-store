# BK-456 — Spec 003 is too long to keep free of contradictions, so it is split by layer
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** The maintainer, during PR #1159 (BK-449): spec 003
is "much too long to be maintained and kept correct with no inconsistencies and
contradictions". The scope and shape below are the maintainer's choices,
recorded in `sdd/decisions/062e5181-cc50-5b17-963f-e9da78bad8ee.jsonl` ("When
should spec 003 be split?": "Separate PR after BK-449"; "Which split shape
should the work follow?": "By layer, 4 files").

**Section sizes.** Not copied here, since every edit to the spec moves them:
re-run `rg -n '^##+ ' sdd/specs/003-backend-adapter-contract.md` before
planning and take each section's size as the gap to the next heading. At
PR #1159 the four largest were BE-021 Error Mapping, BE-029 Root Path, BE-032
The Store Tree on the Kernel and BE-033 Interaction Protocol on the Kernel,
then BE-030, BE-008 and BE-031; the CAP- sections and most BE- operation
sections are short.

**The ripple, measured the same day.** `git grep -l
"003-backend-adapter-contract"` outside `sdd/decisions`, `sdd/traces` and
`sdd/research` names 45 files (specs, RFCs, ADRs, the custom-backend guide,
`scripts/gen_graph.py` and `scripts/gen_protocol_diagram.py`, two `src/`
modules, `docs-src/_data/graph/graph.json`). Anchored links
(`003-backend-adapter-contract.md#`) sit in 15 of them. Re-run both before
planning: the split must move every anchor a section takes with it.

**Order.** BK-457's ADR first (the maintainer's choice, same decision log:
"ADR first, then BK-456"), then this split, then a prune of each new file
against that ADR.

**Prescription** (advisory):

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
