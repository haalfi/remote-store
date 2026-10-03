# BK-399 — The local gate runs every test for every diff, with no selected target for in-progress rounds
<!-- doc: repo-only -->

Filed from [audit-022](../audits/audit-022-gate-speed-strategies.md), proposal
P2. The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence (by reference)

- **What is at stake:** audit-022 § H1's table of `hatch run all`'s members.
  Only the `test-cov-s1` share can shrink; the other members are not this
  item's.
- **Prior decisions this must be weighed against:**
  - [audit-017](../audits/audit-017-dev-process-gate-topology.md) R3: one
    definition of "what validates a change", and at most one thin
    fast-iteration target. This item would spend that allowance.
  - BK-271 (`BACKLOG-DONE.md`): the `/pr` gate composes `all` for code diffs
    and `lint` + `docs-gate` otherwise, and mints no new target. A selected
    target is a third branch beside those two, used for rounds only; it does
    not replace either.

## Prescription (advisory)

One `hatch run` target that runs the map-selected tests from BK-398's winning
selector, for in-progress rounds. `all` stays the pre-push gate.

- **Depends on BK-398:** no map, no target.
- **Never asserts the coverage floor:** a selected run cannot measure a
  whole-suite property (audit-022 § H1, "What must stay full").
- **Saves nothing in `/ship` on its own:** `/ship` runs `all` before every
  push. The target pays off only if `/ship` uses it for rounds and keeps `all`
  for its close (audit-022 § M1, "`/ship` constraint"). That skill change is
  part of this item's scope, not a follow-up.
- Inherits the fail-open rule from BK-398: an unplaceable path selects the
  full suite.
