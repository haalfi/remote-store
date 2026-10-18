# ID-150 — Revisit informational `verify-tla` CI status (2026-10-19)
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

First revisit ticket for the informational `verify-tla` job landed under
ID-147 on 2026-04-19. Per [`sdd/formal/README.md` § Authoring rules](../formal/README.md#authoring-rules) (3),
the status is revisited every 6 months or every 10 spec amendments touching
TLA-backed sections (whichever first). At the revisit, record one of:
**promote** (check caught a real regression — add to the gate's `needs`),
**remove** (no catches, no active modules — drop the job), or **re-defer**
(still useful but no catch yet — open the next revisit ticket). A calendar
without a ticket is the same as no calendar, which is why this item exists.
**Exit criteria:** decision logged in the ticket's close note; if re-deferred,
the successor ticket is linked here; if promoted, `verify-tla` joins the
`gate.needs` list in `.github/workflows/ci.yml` and the caveat in
`sdd/formal/README.md` is updated.

## Correction, 2026-09-28

The body misquotes its authority. `sdd/formal/README.md:187-197`, rule 3, reads
"every 6 months, or after every 10 spec amendments, whichever first", with no
"touching TLA-backed sections", and sets the promote bar at "a real regression
on a production branch". `verify-tla` is still outside `gate`'s `needs`
(`.github/workflows/ci.yml`), and `rg -i 'verify-tla'` over `sdd/` and
`CHANGELOG.md` records no catch. The spec-amendment count since 2026-04-19 was
not derived here. Found by the ADR-0040 § 6 conversion.

## Revisit, 2026-10-18: re-deferred

Decision: **re-defer**; successor **ID-270**, due 2027-04-19, or after 10
amendments to TLA-backed sections, or with the first bridged TLA+ module,
whichever first. Derivations, run on master at `e9580cf`:

- **What runs.** `ci.yml` `verify-tla` runs TLC on `MC3` (`EXTENDS Observer`)
  against the seven invariants in `MC3.cfg`, which model spec 019's dispatch
  (OBS-003, OBS-009). No lifetime is modelled (`sdd/formal/tla/` holds
  `MC3.tla`, `MC3.cfg`, `Observer.tla`).
- **Why no catch can come.** Nothing replays the model against
  `ext/observe.py`, and `TLA_PAT` only matches `sdd/formal/tla/`, the tlc
  scripts and `ci.yml`. A code regression never reaches the check, so rule
  3's "catches a real regression" bar cannot be met as the job stands.
- **Catches.** None (`hatch run backlog-find verify-tla`; the CHANGELOG
  mentions only ID-147's landing). The one red stretch was the job itself,
  broken from #460 until #544 (2026-04-28) by em dashes and a pre-release
  jar.
- **Cost.** Run 39100922614 (`32a5653`): `verify-tla` green in 9 s.
- **Cadence.** `git rev-list --count --no-merges --since=2026-04-19 HEAD --
  <paths>` gives 2 commits on `sdd/formal/tla/` and the tlc scripts, 144 on
  `sdd/specs/`, and 5 on spec 019 plus `ext/observe.py`, #460 itself among
  them. The literal "10 spec
  amendments" fired in April without anyone acting on it. Rule 3 now counts
  amendments to TLA-backed sections.

Why not promote: gating the job without a bridge proves only that the model
agrees with itself; under RFC-0022 D5 it governs no clause either way. Why not
remove: D4 and D5 make TLA+ the lifetime source, and BK-455 may add a TLA+
model for the `Session` close/run race. RFC-0022 Open Question 3 records the
rule: a TLA+ module gates from the PR that adds its bridge. RFC-0019's
`merge-gate` job set (its open question 6) is unchanged, because the status
did not change. It carries to ID-270.
