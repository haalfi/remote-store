# RFC-0027: Each design session gets its entry's input, and shared decisions a home

## Status

Accepted, 2026-10-27, by the maintainer. Drafted 2026-10-27. Tracked as **BK-494** and **BK-495**. Amends
[RFC-0024](rfc-0024-spec-first-reset.md) in two places: research § 4's S3
allowlist gains the entry's input file (P1), and a shared-decisions file's
definitions join the ground without a formal model, its clauses only under
§ R1, filled only by the flow after a session (P2). Closes [RFC-0026](rfc-0026-operation-catalogue.md) Open Question 1 (P3).
It edits the [ground register](../observe/ground-register.md). The
maintainer's cut into a bare skeleton before `read()` and a later API spec,
with core against extension decided after the sessions, is in decision log
`sdd/decisions/c886d81c-7d81-58f9-bc3d-f11dc7304e4a.jsonl` (2026-10-27);
decisions taken in this RFC's session are in
`sdd/decisions/49c0aa22-502b-5f6c-af5e-2807aaa0ea6d.jsonl`.

## Summary

**Before the first entry's design session, each session reads only its own
entry's notes, and a decision that binds every operation has a named section
to land in.** An entry's input file, `sdd/observe/inputs/<entry>.md`, is
admitted to that entry's session alone, and
[`sdd/observe/shared.md`](../observe/shared.md) defines the subjects every
operation shares and which flow fills each.

## Motivation

RFC-0026 made a catalogue entry the unit of a design session. Two gaps were
left for this step:

- **Per-entry input.** The hook admits a named file whole (S3), so the deep
  research's per-entry notes, or the maintainer's decisions recorded for one
  entry in BK-493's dossier, reach a session only with every other entry's
  notes, and the dossier's with 0.33's surface (RFC-0026 C4).
- **Decisions that bind every operation have no home** (BK-485's dossier; the
  first `/observe` run). RFC-0026 Open Question 1 left open which shared layer
  each lands in. Without a named home, each session would rediscover them, and
  a session that decided one would have nowhere to put it but its own record.

## Proposal

### P1. An entry's input file

S3's allowlist, the ground register plus the files the maintainer names, gains
one file: `sdd/observe/inputs/<entry>.md` of the session's own entry. The hook
admits no other entry's. An input file is never ground and never a register
row: it holds what the entry's session should weigh, such as the comparables'
pitfalls or a maintainer decision taken before the session, and binds nothing
until the session decides. Each section names its source. The deep research's
per-entry notes are copied there from its § 4, which stays as written, a dated
record (`000-process.md` § Document types).

### P2. The shared-decisions file

`sdd/observe/shared.md` joins the ground register as `active` with flow
`shared`, without a formal model, as the catalogue did (RFC-0026 C4). The
exemption covers its definitions only: a clause written into a section joins
the ground under RFC-0024 § R1, once the flow that writes it has its spec and
model accepted, and until then the section holds no clause. Its sections are
Session (design session against caller session), Handle, Lifetime and State,
each naming the flow that fills it. A design session never writes it: the
session records a decision that binds every operation and lists it under Open
items as `shared: <home>`, naming a section, a home the file's Lands elsewhere
table names, or `unhomed`. Where it lands is decided after the session, by the
flow that follows it with the maintainer, as the maintainer's cut puts it
(decision log above): never in a session. A change to ground, a filled
section included, is a reopen under research § 3.

### P3. Open Question 1 of RFC-0026

The shared file's Lands elsewhere table gives each decision Open Question 1
lists, and the three of BK-485's dossier, its home, as the table's rows name
it. RFC-0024 D5 stands:
the error, lifecycle and consistency layers still grow from `read()`; the
table names where.

## Alternatives Considered

Decided in the log above:

- **Input:** one file per entry admitted with no copy, by handing a session a
  section of a named file, which needs the hook to enforce line ranges and
  breaks when the doc is edited; or the mechanism with empty files, the
  maintainer writing each before its session.
- **Home:** a spec numbered 054, which the register's dated rule already gives
  a meaning in older records, and which has no clauses to test; or the file
  without an RFC, which changes what joins the ground with no record that
  binds.
- **Coverage:** the four sections alone, which leaves Open Question 1 partly
  open; or Errors and Consistency as sections too, which D5 says grow from
  `read()`.

## Impact

- **Public API:** none.
- **Backwards compatibility:** none. `/observe` takes a catalogue ID; no
  record under the old operation slugs exists on master.
- **Process:** `/observe`, its hook and tests; the ground register; the axes'
  ID form. RFC-0024 carries an "Amended by RFC-0027"
  line and RFC-0026's Open Question 1 a "Closed by RFC-0027" line.
- **Testing:** `tests/scripts/test_observe_ground.py` pins the entry argument,
  the input file's admission to its own entry only, and one input file per
  catalogue entry.

## Open Questions

None.

## References

- [RFC-0024](rfc-0024-spec-first-reset.md), [RFC-0026](rfc-0026-operation-catalogue.md),
  [`research-spec-first-reset.md`](../research/research-spec-first-reset.md)
  §§ 3 and 4.
- [`sdd/observe/catalogue.md`](../observe/catalogue.md),
  [`sdd/observe/shared.md`](../observe/shared.md).
