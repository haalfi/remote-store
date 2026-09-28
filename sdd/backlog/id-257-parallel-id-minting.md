# ID-257 — Two sessions working in parallel mint the same backlog ID, and every derivation says both are right
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Reproduced by having happened**: BUG-275's branch minted `BUG-278` for a
cross-backend divergence while a concurrent BUG-274 session minted `BUG-278`
for something else. Neither session was careless — at mint time `master`
carried no 278 in either backlog file, so both computed the same next integer
and both were correct about everything they could see. It surfaced only when
the second branch rebased and `gen-backlogid --check` reported the collision;
one of the two items had to be retired and re-homed after the fact.
**The gap is unmerged branches, not the floor.** `gen_backlogid.py`'s `--check`
already takes `max(BACKLOG-DONE, BACKLOG open)` for its "Next safe IDs" line,
and [§ How this file works](../BACKLOG.md#how-this-file-works) sends an author to that
line — so the documented procedure is sound and was followed. What no
derivation reads is *another branch*, which is where a concurrently minted ID
lives until it merges. An earlier account of this incident inside BUG-275's
trace blamed the floor for reading `BACKLOG-DONE.md` only; that was wrong, and
opening the script is what showed it.
**One real inaccuracy to fix in passing**: the collision message prints
`(floor: sdd/backlogid.json)`, and that file *is* BACKLOG-DONE-only, so an
author who follows the pointer rather than the prose gets a number that may
already be taken.
**The open question is what mechanism**, which is why this is `ID-` and not
`BK-`. Cheapest is a check against the remote — `git ls-remote` plus the
backlog files on each open branch — which costs a network call on a gate that
is currently offline and pure. Alternatives worth pricing against it: minting
from a range reserved per session, deriving the ID from the branch, or
accepting collisions and making the *rebase* the enforcement point, which is
what caught this one and cost only a re-home.
**Filed here rather than as a `BUG-`** because nothing is defective: every
component behaved as specified, and it is the coordination between them that
has no owner. That is this section's promise — the artifacts maintainers
coordinate through say what is actually true — failing across two working
copies rather than inside one.
**A second instance, and it narrows the check's reach.** ID-182's branch
(#998) and BK-378's branch both minted `BK-367`, for unrelated items, from a
`master` whose next safe BK was 367 for each. The rebase reported nothing,
because `gen-backlogid --check` compared open IDs against done ones and two
*open* items sharing an ID passed it, so the duplicate was found by reading
`rg -n 'BK-367' sdd` after the rebase rather than by a gate.
**That half is now built and is no longer this item's**, under
[`BK-383`](../BACKLOG-DONE.md): `_duplicate_ids` reports one ID carried by two
open headers, and `gen-backlogid --check` fails on it. What it does not do is prevent the
mint, which is the open question below and the whole of what remains here —
the gate catches the collision only once both branches have merged, and the
re-home still has to happen by hand.
**A third instance, one week later, on the same branch.** Re-homed to
`BK-368`, that branch waited on review while ID-018's work minted `BK-368`
for the conda-recipe pin gate (#1009) and closed it in the same window. This
one the gate did report, because the other item was done by the time the
branch rebased. Two collisions on one branch in nine days is the rate a
long-lived PR should expect under the current scheme; the item moved to
`BK-378`.
