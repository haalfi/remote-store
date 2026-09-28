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
