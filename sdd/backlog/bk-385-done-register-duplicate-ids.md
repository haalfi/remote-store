# BK-385 — The duplicate-ID gate cannot see the done register, where a collision would be permanent
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`_duplicate_ids` reports one ID on two **open** headers; `BACKLOG-DONE.md` is
not read, and `_extract_ids` collapses a repeat there exactly as it did on
the open side before `BK-383`.
**The path is reachable and is the ordinary shape, not an exotic one.** Two
branches mint one ID and each *closes* its item before merging — which is what
a `/ship` delivery does at the close. Neither ID is ever open, so the
open-versus-open rule sees nothing and the open-versus-done comparison sees
nothing either, and the register keeps two distinct completed items under one
ID with nothing reporting it. The open-side collision, by contrast, is loud
the moment either branch rebases.
**Why it was not simply widened under BK-383.** `_duplicate_ids` already takes
`status_chars`, so `_duplicate_ids(done_text, "x")` is the entire code change —
it was written, run, and reverted. Measured: it fails on **four** pairs already
in the register — `BK-001` (audit workflow / Azure backend), `BUG-001`,
`BUG-144`, and `BK-167b`, whose second header is the sanctioned `(partial)`
split shape rather than a collision at all. Derivation:
`python scripts/gen_backlogid.py --check` with that one line restored. The
first three are genuine ID reuse from before the discipline existed, inside
released sections; renumbering them would falsify the release record, and a
gate that ships with an exemption list on its first run is fighting its
subject.
**So the decision this item carries is what to do about the four**, and the
options are not equal. Grandfathering by ID has repo precedent (audit-014's
allow-list) and costs one entry per pair plus a justification. Exempting the
`(partial)` shape by rule is cleaner but reaches only `BK-167b`. Narrowing the
check to the `## Unreleased` section alone would catch every *future*
collision at the point it lands and leave released history untouched, which is
the option this item should price first — nothing in the register's older
sections can collide again.
**Exit criteria:** either the done register is checked, with the four resolved
by whichever mechanism is chosen and that choice recorded here; or the gap is
accepted with its reason, and `gen_backlogid.py`'s stated bound is the durable
record of it.

## Re-measured, 2026-09-28

Holds. From `scripts/`, `python -c "import gen_backlogid as g;
print(sorted(g._duplicate_ids(g.BACKLOG_DONE.read_text(), 'x')))"` prints
`['BK-001', 'BK-167b', 'BUG-001', 'BUG-144']`; none sits under `## Unreleased`,
so narrowing the check to that section would land green today. Found by the ADR-0040 § 6 conversion.

## Resolved, 2026-10-02

Checked, with a wider live region than `## Unreleased`. The region is
everything above the first `## v<digit>` heading, so `Absorbed` and `Decided
against` count too. A pair fails when one of its headers is in that region,
which also catches a new close reusing a released ID. Re-derived before
choosing: the same `_duplicate_ids` call printed the same four IDs, and a
section-tagged walk of the file's headers placed all eight below the first
`## v` heading. The latest of them is `BK-167b`, under `## v0.25.0`.
`TestCheck::test_stated_bound_a_pair_wholly_in_released_history_is_not_reported`
is the re-runnable form. So the four pass by rule and no exemption list
exists. The release record is their Rule 6 register.
