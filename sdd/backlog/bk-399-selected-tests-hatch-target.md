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
    definition of "what validates a change". Its allowance is conditional:
    "If a lighter gate is wanted for fast iteration, document one thin target
    and have both skills call it — but only one", where the two skills are
    `/pr` and `/fix-pr`. This item would spend that allowance, so it owes an
    answer for `/fix-pr`, which pushes during review rounds, as well as for
    `/ship`.
  - BK-271 (`BACKLOG-DONE.md`): the `/pr` gate composes `all` for code diffs
    and `lint` + `docs-gate` otherwise, and mints no new target. A selected
    target is a third branch beside those two, used for rounds only; it does
    not replace either.

## Prescription (advisory)

One `hatch run` target that runs the map-selected tests from BK-398's winning
selector, for in-progress rounds. `all` stays the gate before a PR is opened
and before `/ship`'s close push. Before a round push, the target replaces
`all`; which skills run it there (`/ship`, `/fix-pr`) is the index's open
decision.

- **Depends on BK-398:** no map, no target.
- **Never asserts the coverage floor:** a selected run cannot measure a
  whole-suite property (audit-022 § H1, "What must stay full").
- **Saves nothing on its own:** `/ship` runs `all` before every push today.
  The target pays off only in a skill that runs it before round pushes and
  keeps `all` for its close (audit-022 § M1, "`/ship` constraint"). Whichever
  skills the open decision picks, their edits are in this item's scope, not a
  follow-up.
- **Shares `.claude/skills/ship/SKILL.md` with ID-264**, whose `/ship` edit
  marks a draft PR ready at the close. Sequence the two edits together.
- Inherits the fail-open rule from BK-398: an unplaceable path selects the
  full suite.
