# BUG-291 — A single-extra dispatch can still close the rolling drift issue on one extra's evidence
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`drift_report.decide` refuses to close on a run that did not cover both lanes,
and its comment gives the reason: *"a single-lane dispatch has not seen what
the other lane would have found, and a closed issue is not recoverable the way
a rewritten body is."* That argument is about **narrowing**, and the guard
implements only the lane half. `_lanes_present(reports) != set(LANES)` is
blind to the *extras* narrowing, so `extra: s3, lane: all` — a real
`workflow_dispatch` input combination — reaches the close with one extra's
reports and closes the issue, discarding the scheduled run's findings for the
other thirteen.
**Measured on both sides**, so it is pre-existing rather than introduced with
the support-window work: a one-extra, both-lane, all-clean run at
`origin/master` and at this item's filing head both print
`(dry run — would close the issue titled '[drift-guard]': all clear in both
lanes)`. BUG-282 covers the sibling hazard — that such a dispatch *rewrites*
the body from its slice — and this is the same narrowing reaching the other,
unrecoverable outcome.
**Why it stayed hidden:** `main` computes `unnarrowed = set(lanes) ==
set(LANES) and bool(expected) and set(expected) == set(list_extras())` and
hands it to the window state, but the close guard never sees it. So the issue's
survival of a narrowed dispatch currently depends on whether an interpreter
happens to be past its support window, which is an unrelated calendar fact.
**Scope when picked up:** give the close the same `unnarrowed` test the window
signal already uses, pin it in both directions (a full clean run still closes;
a one-extra clean run leaves), and reconcile the three layers that describe the
verdict — `drift-guard.yml`'s header and step comment, the drift-guard runbook
in `sdd/CI-OPERATIONS.md`, and `.claude/skills/drift/SKILL.md` — since all
three currently say "all clear and an open issue exists → close".

## Correction, 2026-09-28

The quoted reason is in `scripts/drift_report.py`'s module docstring
(`:41-43`); the comment inside `decide` (`:1138-1143`) makes the same argument
in other words. The guard reads `covered = _lanes_present(reports)` then
`if covered != set(LANES)` (`:1144-1145`), not the one-line form quoted.
`decide` now names this item at `:1156-1161`, and `unnarrowed` (`:1729`) also
feeds the feedstock signal (`:1755`). A test pins today's close on a one-extra
run: `tests/scripts/test_drift_report.py::…::test_a_narrowed_run_with_a_registered_crossing_still_closes`
asserts `decide(reports, {}, ["s3"], …)[0] == "close"` and passes
(`hatch run python -m pytest tests/scripts/test_drift_report.py -k
test_a_narrowed_run_with_a_registered_crossing_still_closes`), so the fix
changes that test rather than only adding one. Of the three layers, only
`drift-guard.yml:562`'s step comment states the close rule in those words;
`sdd/CI-OPERATIONS.md:107-110` and `.claude/skills/drift/SKILL.md:78` state it
in substance, and the workflow header (`:112-116`) states only the rewrite
hazard (`rg -n -i 'close|all clear|cleared'` over the three). Found by the ADR-0040 § 5 conversion.
