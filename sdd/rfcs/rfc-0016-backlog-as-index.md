# RFC-0016: `BACKLOG.md` as an index, item detail in dossiers

## Status

Draft. Tracked as **BK-365**, whose exit criterion this answers for
`sdd/BACKLOG.md`; `BACKLOG-DONE.md` is out of scope (§ Open Questions 2). If
accepted it graduates to a new ADR carrying the structure's rationale (D4), and
to rewrites of `sdd/BACKLOG.md` § How this file works, `000-process.md`
§ Backlog, `AUTHORING.md` § Directory defaults and `CLAUDE.md` § Backlog.

**Date:** 2026-09-24. Every figure below is pinned to `e5fb4a8` and comes from
`python sdd/rfcs/rfc-0016-measure.py --at e5fb4a8`, committed beside this file.
The file changes on every merge: re-run rather than quote.

## Summary

`sdd/BACKLOG.md` is read by every session that picks, files or closes work, and
at `e5fb4a8` it is ~51k tokens and 3,013 lines — longer than one default `Read`,
so no session sees all of it. 82% of it is item bodies written as evidence
dossiers. This RFC makes the file an **index**: rules of about forty lines, one
Promise per section, and per item a header, an attribute line and a diagnosis of
at most five lines. Everything else an item carries moves **verbatim** into a
per-item dossier under `sdd/backlog/`, read only by the session working on it.
The structure's rationale moves to an ADR, `Closes when` is removed, and a gate
holds the shape.

## Motivation

**Where the length is.** Character split by region, from the script:

| Region | Characters | Share |
|---|---|---|
| § How this file works (rules) | 11,215 | 5% |
| Section preambles (Promise + Closes when + notes) | 24,627 | 12% |
| Item bodies, 67 items | 168,558 | 82% |
| **Total** | 204,413 (~51k tokens at 4 chars/token) | |

Separator lines (blank, `---`, section anchors) are charged to the section they
open, not to the item above them; the script's docstring states the regions.
Per section, median/max item content lines: § 1 34/121, § 2 22/36, § 3 20/53,
§ 4 25/69, § 5 26/63, § 6 39/130. **66 of 67 items exceed eight content lines.**
BK-365 measured the trend: median words per item doubled, 145 → 290, in seven
weeks.

**Three kinds of content share one file, and only one is read by everyone.**

1. *Rules and their reasons.* § How this file works interleaves the operational
   rules (status, admission, completing work) with why each exists: the Icebox's
   abolition, the count of IDs one restructure retired, disclaimers about which
   `DRIFT-RULES.md` obligations do not apply. A decision with its reasons is an
   ADR ([principle 8](../../CLAUDE.md#principles)); the reader filing an item
   needs the rule.
2. *Closure history in section preambles.* § 1's preamble is 1,640 words, most
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

**Why it grew.** The file's placement rules (admission test, granularity,
splitting) are review-enforced, as § How this file works states; the gated
rules cover ID integrity only (`gen_backlogid.py --check` and
`check_backlog_ids_vs_base.py`, per `GATE-INVENTORY.md`). So each placement rule
ships with its full argument attached, and nothing stops an item body growing
after it is filed.

## Proposal

### D1. `BACKLOG.md` is an index

Each item is at most **eight content lines**: header (1), attribute line (1), a
diagnosis of at most five lines stating the observed problem and the open
decision (5), and an optional `Detail:` link (1). The blank line between items
and a section's trailing `---` and anchor are not content lines; the script
counts exactly this, and R2 uses the same delimitation.

**Authority across index and dossier** (`DRIFT-RULES.md` Rule 4, declared
before R4 exists; its home after acceptance is the rewritten § Item authority,
the document that owns the pair). § Item authority's three kinds of content
split across the two files, and each is corrected where it lives:

| Kind | Lives in | Status | Corrected when re-derivation disagrees |
|---|---|---|---|
| Diagnosis claim: the observed problem | index | authoritative, current | in the index, same commit |
| Evidence: what was measured, how | dossier | durable record, dated by its commit | a dated correction is added in the dossier; the original is not rewritten |
| Prescription: fix shape, disposition, line reference, scope claim, reproduction recipe | dossier | advisory, presumed stale | in the dossier, same commit |

Where dossier prose restates the diagnosis claim and disagrees, the index wins
and the dossier is corrected in the same commit. R4 checks only link and ID, so
agreement within this pair is review-enforced, and that bound is stated with the
rule.

Worked example — BUG-276, 81 content lines at `e5fb4a8`:

```markdown
- [ ] **BUG-276 — A mapped error still reaches the caller with an empty message through five base-class arms**
  spec: ERR-009, AZ-025 · effort: M · audience: user.api
  Five fall-through arms in four files build `RemoteStoreError(str(exc))` from
  exceptions that stringify to `""`, breaking ERR-009; `_errors.py`'s arm is
  shared by all three S3 backends. Open decision: synthesise a fallback message
  or classify the fall-through. The fix deliberately falsifies AZ-025's
  blank-message clause and its pinning test.
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
- **Migration moves, never cuts.** Current bodies move verbatim into the
  dossier; the index gains a new diagnosis of at most five lines. Nothing is
  removed from an item in D1's migration, so no cut needs research § 9.2's
  licence.

### D3. Sections keep a Promise; `Closes when` is removed

A section is a heading and a Promise of at most three sentences. The cap is this
RFC's own rule (D5 R3), not a reading of
[`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz), which governs only
how a section opens.
A section **closes when it has no items**; it is then removed, or its Promise is
re-argued with a new item. **Release Blockers is the one standing section**: it
is never removed, and empty is its normal state, written as its Promise with no
placeholder line. Its admission rule is unchanged: a `BL-` item is filed there
by prefix, not by outcome. Cross-section dependencies are stated by ID inside
the dependent item only — today's first half of the rule; its second half
(repeat it in `Closes when`) goes with the field.

Preamble material that is neither the Promise nor a rule moves by kind, and
nothing is deleted on the ground that another file could reconstruct it:

- **Rationale for the Promise** (e.g. § 1's "BK-359 is why the Promise above
  carries a third clause") moves to the D4 ADR, one subsection per section.
- **Closure narration** is removed only where the closed item's
  `BACKLOG-DONE.md` entry states the same fact (principle 4: one copy per fact).
  The migrator checks each sentence against that entry; a sentence stating
  something no entry does moves to the ADR instead.
- **Ordering notes** become the order itself; the dependency they name moves
  into the dependent item.
- **Research qualifications** (§ 6's note on research § 9) move to the dossier
  of the item they bound.

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
| R2 Inline item cap | an item over eight content lines (D1's delimitation), naming the item and its length |
| R3 Section shape | a section preamble beyond heading, anchor and one Promise paragraph of at most three sentences |
| R4 Dossier link | a `Detail:` link that does not resolve, or a dossier whose header ID differs from the item's |

**R2 and R3 are length rules, and this RFC departs from research
[§ 9.1](../research/research-appropriate-level-of-detail.md) for this one file,
by maintainer decision.** § 9.1 says to put no length rule beside Rule 7, partly
because § 1 rules out every text-level instrument; a line count and a sentence
count are text-level instruments, and this RFC does not claim otherwise. What
the departure rests on is what the research does not measure: the reader here
is a session with a bounded context that loads this file on every pick, file or
close, and at `e5fb4a8` the file does not fit one default `Read` (§ Motivation).
Two bounds on the departure. It does not extend to any other `sdd/` document.
And overflow moves to the dossier rather than being cut, so no rationale is
lost to the cap; what the cap costs is where a reader finds it. If § Acceptance's
re-measurement shows the caps pushing load-bearing diagnosis out of the index,
that is evidence against this departure, and the ADR records it as such.

## Alternatives Considered

- **Trim in place with a line cap, no dossier.** Rejected: it forces cutting
  rather than moving, and research § 9.2 found readers did not rebuild cut
  rationale that carried a fact from outside the surviving text.
- **Use the trace as the dossier.** Rejected: traces are YAML, begin at
  implementation, and a pre-work diagnosis mixed with a work log is two records
  in one.
- **One file per section.** Rejected: it reduces per-read size without reducing
  the total, and it scatters the one view (all open work) the index exists for.
- **GitHub issues.** Rejected: backlog IDs are the address `sdd/` cites.
  `scripts/check_no_tracker_refs.py` exempts `sdd/**` because "the trackers are
  how those documents are addressed" and routes coordinates into `sdd/specs/`
  or `sdd/BACKLOG-DONE.md`; moving item detail to an external tracker would put
  what those citations resolve to outside the repo.
- **Move the rationale into `000-process.md`.** Rejected: it grows another
  frequently read file; the rationale is a decision, which is an ADR's job.

## Impact

- **Public API:** none. **Backwards compatibility:** internal process only.
- **Context cost:** estimate, not a measurement — 67 items × (≤ 8 content lines
  + 1 blank separator) ≈ 600 lines, plus ~40 of rules and ~6 per section,
  ≈ 680 lines, one `Read`. The acceptance run below replaces this estimate with a figure.
- **Ripples:** `CLAUDE.md` § Backlog; `000-process.md` § Backlog and Rule 6's
  bug-fix pipeline (where the reproduction now lives);
  `AUTHORING.md` § Directory defaults (new `sdd/backlog/*.md` → repo-only row);
  `CLAUDE-REFERENCE.md` lookup row "Log a bug or improvement idea";
  `CLAUDE-REFERENCE.md` ripple-check rows **Bug fix** and **Backlog item
  touched**, in both presentations (Pre-work index and Detailed checklist, held
  in parity by `check_ripple_parity.py`): the dossier as where a bug's
  reproduction lives, the dossier read as a trace orient step, and the
  `BACKLOG-DONE.md` entry linking the dossier on close;
  `sdd/traces/_schema.yml` (dossier as an orient step, if stated there);
  `GATE-INVENTORY.md` (regenerated); `.claude/hooks/backlog-status-brake.sh`
  (unaffected; it keys on headers).
- **Testing:** R1–R4 each with a failing fixture seen red first, per
  `sdd/TESTING.md`.

**Acceptance.** After the § 1 pilot, `rfc-0016-measure.py` reports **0** § 1
items over eight content lines and § 1's preamble is heading plus Promise. After
the full migration, it reports the file under 2,000 lines, **0** items over
eight content lines and no attribute value R1 would reject, and `--check`
passes R1–R4 on the tree. Measured again after the next three merged deliveries that file an item: no
item body exceeds the cap without failing the gate.

## Open Questions

1. **The cap values.** Eight lines per item and three sentences per Promise are
   proposals. The acceptance run tests them; move them only on evidence.
2. **`BACKLOG-DONE.md`.** BK-365 names both files. `BACKLOG-DONE.md` is read by
   grep, not whole, so its length costs little context. Out of scope here;
   BK-365 keeps that half open.

**Decided by the maintainer while drafting**, recorded so review does not
re-open them without new evidence:

- **Effort is strictly `S`/`M`/`L`.** R1 rejects anything else. The script
  lists every value it would reject: at `e5fb4a8`, eleven effort values and one
  audience value. Migration maps them: `XS` → `S` (four); a slash range to its
  upper bound, `S/M` → `M` (five) and `XS/S` → `S` (one); BK-332's
  `S to define, M per run` → `M`, keeping the split in its dossier; and ID-242's
  `audience: contributor` → `infra.test`, since its title names test-coverage
  pragmas ("Four `moto doesn't raise PermissionError` pragmas are coverage
  holes"). R1 lands in the same PR as the
  mapping, so `--check` never runs against unmapped values.
- **Release Blockers gets a one-line Promise**: "Nothing ships to PyPI until this
  section is empty." It is D3's one standing section, so empty does not remove
  it, and R3 needs no exemption because its preamble is heading, anchor and
  Promise like every other section's.
- **Migration pilots § 1 first**, the worst case (1,640 preamble words, max item
  121 content lines), measures it with the script, then converts the rest.

## References

- Host item: BK-365 (`sdd/BACKLOG.md` § 6); structural lint host: ID-235.
- [`research-appropriate-level-of-detail.md`](../research/research-appropriate-level-of-detail.md)
  § 1, § 9.1, § 9.2.
- [`DRIFT-RULES.md` Rule 4](../DRIFT-RULES.md#rules) (authority per artifact
  pair, D1); `scripts/check_no_tracker_refs.py` (§ Alternatives).
- [`CONTENT-RULES.md` Rule 7](../CONTENT-RULES.md#kernsatz);
  [`CLAUDE.md` principles 3, 4, 8, 9](../../CLAUDE.md#principles).
- Measurement: `sdd/rfcs/rfc-0016-measure.py` (this directory).
