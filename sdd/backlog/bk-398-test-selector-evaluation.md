# BK-398 — No change-scoped test selector has been chosen for this suite; one of three candidates is measured
<!-- doc: repo-only -->

Filed from [audit-022](../audits/audit-022-gate-speed-strategies.md), proposal
P1. The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence (by reference)

- **Why a map is wanted:** audit-022 § H1, its local-gate member table and its
  per-area worker-second table. The figures live there and are not copied here.
- **Which mechanisms fit:** § H1's mechanism table. Runtime coverage sees the
  fixture-registry wiring that conformance uses; every row is blind to source
  read as text (`scripts/gen_features.py`, `scripts/check_test_placement.py`).
- **Tool maturity:** § H1's PyPI release table, dated 2026-10-03.
- **The fail-open rule:** § H1, "Either way, the fail-open rule". It names the
  path classes that must select the full suite whatever the map says.

## Prescription (advisory)

Evaluate `pytest-testmon`, `pytest-tia` and `pytest-impact` against the full
Stage-1 suite as the control group, per audit-022's P1 row. The criteria:

- time saved;
- missed failures, on the seeded changes listed under audit-022's "P1's seeded
  changes" (a single miss makes that path class fail open, or rejects the tool);
- operating cost, including the two open interactions § H1 names: `xdist` and
  `pytest-cov`, which both instrument through coverage.py;
- **portability (§ M1):** whether a map built on one run and interpreter
  selects correctly on another. ID-266 needs this answered before it can
  choose a map transport.

If no tool passes, the fallback is a declared table in the style of
`scripts/drift_smoke_map.py`, which needs a drift check under
[`DRIFT-RULES.md`](../DRIFT-RULES.md).

**Whatever wins never asserts the coverage floor**: § H1, "What must stay
full".

**Consumers:** BK-399 (the local target) and ID-266 (the CI draft lane) both
need this item's verdict.

## Progress

- **2026-10-03, `pytest-testmon`:** viable with fail-open rules, one map per
  interpreter. Seeds, timings, the four fail-open classes and the two
  repo defaults that disable it are in
  [`research-bk-398-testmon-poc.md`](../research/research-bk-398-testmon-poc.md).
  `pytest-tia` and `pytest-impact` are still to run against the same seeds.
