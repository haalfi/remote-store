# RFC-0016: `BACKLOG.md` as an index, item detail in dossiers

## Status

Draft. Tracked as **BK-365**, whose exit criterion this answers for
`sdd/BACKLOG.md`; `BACKLOG-DONE.md` is out of scope (§ Open Questions 4). If
accepted it graduates to a new ADR carrying the structure's rationale (D4), and
to rewrites of `sdd/BACKLOG.md` § How this file works, `000-process.md`
§ Backlog, `AUTHORING.md` § Directory defaults and `CLAUDE.md` § Backlog.

**Date:** 2026-09-24. Every figure below is pinned to `e5fb4a8` and comes from
`python sdd/rfcs/rfc-0016-measure.py --at e5fb4a8`, committed beside this file.
The file changes on every merge: re-run rather than quote.

## Summary

`sdd/BACKLOG.md` is read by every session that picks, files or closes work, and
at `e5fb4a8` it is ~51k tokens and 3,013 lines — longer than one default `Read`,
so no session sees all of it. 83% of it is item bodies written as evidence
dossiers. This RFC makes the file an **index**: rules of about forty lines, one
Promise per section, and per item a header, an attribute line and a diagnosis of
at most six lines. Everything else an item carries moves **verbatim** into a
per-item dossier under `sdd/backlog/`, read only by the session working on it.
The structure's rationale moves to an ADR, `Closes when` is removed, and a gate
holds the shape.

## Motivation

**Where the length is.** Character split by region, from the script:

| Region | Characters | Share |
|---|---|---|
| § How this file works (rules) | 11,221 | 5% |
| Section preambles (Promise + Closes when + notes) | 24,427 | 12% |
| Item bodies, 67 items | 168,752 | 83% |
| **Total** | 204,413 (~51k tokens at 4 chars/token) | |

Per section, median/max item-body lines: § 1 34/122, § 2 23/40, § 3 20/54,
§ 4 28/70, § 5 26/67, § 6 40/131. **66 of 67 items exceed eight lines.**
BK-365 measured the trend: median words per item doubled, 145 → 290, in seven
weeks.

**Three kinds of content share one file, and only one is read by everyone.**

1. *Rules and their reasons.* § How this file works interleaves the operational
   rules (status, admission, completing work) with why each exists: the Icebox's
   abolition, the count of IDs one restructure retired, disclaimers about which
   `DRIFT-RULES.md` obligations do not apply. A decision with its reasons is an
   ADR ([principle 8](../../CLAUDE.md#principles)); the reader filing an item
   needs the rule.
2. *Closure history in section preambles.* § 1's preamble is 1,637 words, most
   of it narrating clauses already met: it names 16 IDs no longer open in the
   file (a set difference of the IDs the preamble cites against the file's open
   headers, run once at the pin) — a copy of
   `BACKLOG-DONE.md` and the traces, and narration where
   [principle 3](../../CLAUDE.md#principles) asks for current state. Meanwhile it
   omits five of the section's sixteen open items (BUG-263, BUG-266, BUG-267,
   BUG-269, BUG-279), so it is neither a closing condition nor a list.
3. *Evidence dossiers as items.* The item-scope rule is "idea +
   decision-relevant constraints + open questions". Items actually carry
   reproduction tables, review-round history and draft fixes (BUG-276, BUG-273).
   That material is valuable to exactly one reader — whoever implements the item.

**Why it grew.** Every structural rule is review-enforced (the file says so,
§ How this file works), so each rule ships with its full argument attached, and
nothing stops an item body growing after it is filed.

## Proposal

### D1. `BACKLOG.md` is an index

Each item is at most **eight lines**: header, attribute line, a diagnosis of at
most six lines stating the observed problem and the open decision, and an
optional `Detail:` link. The diagnosis is the item's durable half
(§ Item authority, kept); the index carries it, the dossier carries its evidence.

Worked example — BUG-276, 82 lines at `e5fb4a8` (header to next header):

```markdown
- [ ] **BUG-276 — A mapped error still reaches the caller with an empty message through five base-class arms**
  spec: ERR-009, AZ-025 · effort: M · audience: user.api
  Five fall-through arms in four files build `RemoteStoreError(str(exc))` from
  exceptions that stringify to `""`, breaking ERR-009; `_errors.py`'s arm is
  shared by all three S3 backends. Open decision: synthesise a fallback message
  or classify the fall-through. The fix deliberately falsifies AZ-025's
  blank-message clause and the test pinning it.
  Detail: [dossier](backlog/bug-276-empty-base-class-message.md)
```

### D2. Item detail lives in a per-item dossier

`sdd/backlog/<id>-<slug>.md`, `<!-- doc: repo-only -->`, created only when an
item needs more than D1 allows. It holds evidence, reproduction, fix options and
open questions — what the implementer reads first, alongside the trace.

- **The path never moves.** On close the dossier stays; the `BACKLOG-DONE.md`
  entry links it. No link breaks on completion.
- **Dossier vs trace.** A dossier is pre-work diagnosis; a trace records the
  work. The trace's orient phase reads the dossier as a gate step.
- **Migration moves, never cuts.** Current bodies move verbatim, so research
  § 9.2's test — "which surviving sentence supplies the reason?" — is answered by
  the dossier for every unit moved. Nothing is removed from an item in D1's
  migration.

### D3. Sections keep a Promise; `Closes when` is removed

A section is a heading and a Promise of at most three sentences
([`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz)'s Kernsatz, applied).
A section **closes when it has no items**; it is then removed, or its Promise is
re-argued with a new item. Cross-section dependencies are stated by ID inside the
dependent item only — today's first half of the rule; its second half (repeat it
in `Closes when`) goes with the field.

Preamble material that is neither the Promise nor a rule moves by kind: closure
narration is deleted (recoverable from `BACKLOG-DONE.md` and the traces, which is
§ 9.2's condition for removal); ordering notes become the order itself;
research qualifications (§ 6's note on research § 9) move to the dossier of the
item they bound.

### D4. The rules header states rules; an ADR states why

§ How this file works shrinks to the operational rules — status legend, entry
shape, admission, ordering, granularity, ID prefixes and assignment, completing
work, and a pointer to `GATE-INVENTORY.md` for what is gated — at about forty
lines. The reasons (promise-sections over topics, no Icebox, retired-ID
registers, tense rule for sweeps) move to a new ADR, which the header links
once. Nothing is lost: each reason moves; none is paraphrased away.

### D5. Gates hold the shape

Under ID-235's structural pass (`gen_backlogid.py --check`, wired into `lint`
and `docs-gate` per BK-333), four rules:

| Rule | Fails on |
|---|---|
| R1 Attribute vocabulary | `effort` outside the legend; an `audience` value outside `sdd/traces/_schema.yml`'s enum |
| R2 Inline item cap | an item longer than eight lines, naming the item and its length |
| R3 Section shape | a section preamble beyond heading, anchor and one Promise paragraph of at most three sentences |
| R4 Dossier link | a `Detail:` link that does not resolve, or a dossier whose header ID differs from the item's |

**R2 and R3 are length rules, and research
[§ 9.1](../research/research-appropriate-level-of-detail.md) says to put none
beside Rule 7.** The disagreement is scoped, not denied: § 9.1 argues against a
*brevity* target, a limit that pushes text shorter. R2 and R3 are **placement**
boundaries. Overflow is moved to its home, not cut, which is § 9's own "move"
outcome and principle 8's "relocate detail that belongs to another layer". The
reader is task-directed (pick, file or close an item), which is § 9.5's
strongest licence. If an item's diagnosis cannot fit six lines, that is Rule 7's
signal that the diagnosis is not yet understood, not a reason to raise the cap.

## Alternatives Considered

- **Trim in place with a line cap, no dossier.** Rejected: it forces cutting
  rather than moving, which research § 9.2 measured as the loss that readers
  do not recover.
- **Use the trace as the dossier.** Rejected: traces are YAML, begin at
  implementation, and a pre-work diagnosis mixed with a work log is two records
  in one.
- **One file per section.** Rejected: it reduces per-read size without reducing
  the total, and it scatters the one view (all open work) the index exists for.
- **GitHub issues.** Rejected: the repo is the source of truth and must read
  correctly offline ([`AUTHORING.md`](../AUTHORING.md)).
- **Move the rationale into `000-process.md`.** Rejected: it grows another
  frequently read file; the rationale is a decision, which is an ADR's job.

## Impact

- **Public API:** none. **Backwards compatibility:** internal process only.
- **Context cost:** estimate, not a measurement — 67 items × ≤ 9 lines (with
  separator) ≈ 600 lines, plus ~40 of rules and ~6 per section, ≈ 680 lines, one
  `Read`. The acceptance run below replaces this estimate with a figure.
- **Ripples:** `CLAUDE.md` § Backlog; `000-process.md` § Backlog;
  `AUTHORING.md` § Directory defaults (new `sdd/backlog/*.md` → repo-only row);
  `CLAUDE-REFERENCE.md` lookup row "Log a bug or improvement idea";
  `sdd/traces/_schema.yml` (dossier as an orient step, if stated there);
  `GATE-INVENTORY.md` (regenerated); `.claude/hooks/backlog-status-brake.sh`
  (unaffected; it keys on headers).
- **Testing:** R1–R4 each with a failing fixture seen red first, per
  `sdd/TESTING.md`.

**Acceptance.** After migration, `rfc-0016-measure.py` reports the file under
2,000 lines and **0** items over eight lines, and `--check` passes R1–R4 on the
tree. Measured again after the next three merged deliveries that file an item: no
item body exceeds the cap without failing the gate.

## Open Questions

1. **The cap values.** Eight lines per item and three sentences per Promise are
   proposals. The acceptance run tests them; move them only on evidence.
2. **`XS` and range values.** Ten items use `XS`, `S/M` or `XS/S`. Either the
   legend gains them, or R1 rejects them and migration normalises.
3. **Release Blockers.** It carries no Promise by design. R3 needs a stated
   exemption, or the section gets a one-line Promise ("nothing ships until
   empty").
4. **`BACKLOG-DONE.md`.** BK-365 names both files. `BACKLOG-DONE.md` is read by
   grep, not whole, so its length costs little context. Out of scope here;
   BK-365 keeps that half open.
5. **Migration vehicle.** One PR for the whole file, or a pilot on § 1 (worst
   case: 1,637 preamble words, max body 122 lines) before the rest.

## References

- Host item: BK-365 (`sdd/BACKLOG.md` § 6); structural lint host: ID-235.
- [`research-appropriate-level-of-detail.md`](../research/research-appropriate-level-of-detail.md)
  § 4, § 9.1, § 9.2, § 9.5.
- [`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz);
  [`CLAUDE.md` principles 3, 4, 8, 9](../../CLAUDE.md#principles).
- Measurement: `sdd/rfcs/rfc-0016-measure.py` (this directory).
