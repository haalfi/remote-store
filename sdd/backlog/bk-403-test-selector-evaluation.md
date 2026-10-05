# BK-403 — No change-scoped test selector has been chosen for this suite; one of three candidates is measured
<!-- doc: repo-only -->

Filed from [audit-022](../audits/audit-022-gate-speed-strategies.md), proposal
P1. The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence (by reference)

- **Why a map is wanted:** audit-022 § H1, its local-gate member table and its
  per-area worker-second table. The figures live there and are not copied here.
- **Which mechanisms fit:** § H1's mechanism table. Runtime coverage sees the
  fixture-registry wiring that conformance uses; every row is blind to source
  read as text.
- **Tool maturity:** § H1's PyPI release table, dated 2026-10-03.
- **The fail-open rule:** § H1, "Either way, the fail-open rule". It names the
  path classes that must select the full suite whatever the map says.

**Correction, 2026-10-03.** The rule's last class says of the tests that read
source as text, "Today those are `test_gen_features.py` and
`test_check_test_placement.py`" (audit-022:208). That list is incomplete:
`scripts/gen_graph.py:68-69` runs `read_text` and `ast.parse` on `src/` files
for `tests/scripts/test_gen_graph.py`, and `scripts/check_capability_parity.py:187`
reads `src/remote_store/_capabilities.py` for
`tests/scripts/test_check_capability_parity.py`. This item's evaluation owns
deriving the full set; the two names are not it.

## Prescription (advisory)

Evaluate `pytest-testmon`, `pytest-tia` and `pytest-impact` against the full
Stage-1 suite as the control group, per audit-022's P1 row. The criteria:

- time saved;
- missed failures, on the seeded changes listed under audit-022's "P1's seeded
  changes" (a single miss makes that path class fail open, or rejects the tool);
- operating cost, including the three open interactions § H1 names: the
  runtime tools under `xdist`; the runtime tools against `pytest-cov`, since
  both of those instrument through coverage.py; and non-Python inputs,
  whether the map can record a dependency on a data file at all;
- **portability (§ M1):** whether a map built on one run and interpreter
  selects correctly on another. ID-266 needs this answered before it can
  choose a map transport.

If no tool passes, the fallback is a declared table in the style of
`scripts/drift_smoke_map.py`, which needs a drift check under
[`DRIFT-RULES.md`](../DRIFT-RULES.md).

**Whatever wins never asserts the coverage floor**: § H1, "What must stay
full".

**Consumers:** BK-404 (the local target) and ID-266 (the CI fast lane;
*superseded wording "draft lane"*, RFC-0019 D1) both need this item's verdict.

## Progress

- **2026-10-03, `pytest-testmon`:** selection is not worth adopting now.
  It saves real time only on leaf-code edits, a map does not survive a
  change of interpreter or dependency set, and BUG-301 and BK-401 are
  cheaper with no risk of skipping a test. Question, answer, revisit
  condition and evidence:
  [`research-bk-403-testmon-poc.md`](../research/research-bk-403-testmon-poc.md).
  `pytest-tia` and `pytest-impact` wait for that revisit condition.
- **2026-10-03, RFC-0019:** the PoC's "not now" rejects a coverage map, not
  selection. [RFC-0019](../rfcs/rfc-0019-two-speed-test-gate.md) proposes the
  declared-table fallback above, extended by a static import graph, a
  registry-based backend axis and a generated text-reader table (D5), with
  the coverage map kept only as a drift oracle (D7). Its Phase 0 replaces the
  revisit condition: the selector is built only if it passes Phase 0's exit
  (RFC-0019 § Roadmap), which is not restated here.
- **2026-10-04, RFC-0019 Phase 0: the D5 selector stops; the item stays
  open.** Under the precision rule set, 72.6% of 106 code PRs fall back to
  FULL and the median wall-clock share is 100%, against targets fixed before
  the run (at most 30% and 50%). The reader inventory and the seeds passed: the
  selector is sound where it narrows, and it narrows too few diffs. D5's FULL
  row alone (`pyproject.toml`, `.github/**`) fires on 59 of the 106. RFC-0019
  stays Draft, because the motivation stands and a better selection idea is the
  open work. Question, answer, figures and their derivations:
  [Phase 0 report](../research/bk-403-phase-0/report.md).
