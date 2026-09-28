# ADR-0041: A Done Entry Links Its Dossier Instead of Restating It, and the Migration Opt-Out Is Retired

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0040 |

Amends [ADR-0040](0040-backlog-as-index.md)'s *Gates hold the shape* clause,
whose R2 and R3 were **scoped to migrated sections** through an opt-out marker:
every section is now converted, so the scope and its marker are retired. It
also answers the question ADR-0040 left open for `BACKLOG-DONE.md`, which that
record's Decision does not govern. Everything else in ADR-0040 stands. Closes
BK-365; decided with the maintainer in the closing session.

## Context

ADR-0040 made `BACKLOG.md` an index with per-item dossiers and left
`BACKLOG-DONE.md` open: BK-365 asked whether that file's growth is a defect or
the price of [principle 9](../../CLAUDE.md#principles)'s derivations. Median
words per completed entry, per `## ` release section (each `- [x] **ID` header
to the next header or heading, counted with Python's `str.split()`, over the
file at `7cc9f96`, the commit before the one that adds this record and BK-365's
own entry): 9.5 at v0.3.0, 145 at v0.25.0, 235 at v0.30.0, 646 at v0.31.0,
403 at v0.32.0 (6 entries) and 599.5 under `Unreleased` (16 entries). The file then held 687 such entries and 122,869 words
of entry text, 24 of the entries under § Absorbed and § Decided against. Re-run
rather than quote: the file grows on every close.

Two facts changed the question. First, since ADR-0040 every open item's
evidence already sits in a dossier whose path never moves, and a done entry
must link it, so an entry that also restates the evidence keeps a second copy
of text the dossier holds. Second, the register is read by lookup (an ID, a
release), not front to back on every pick as `BACKLOG.md` is, which is the
reader ADR-0040's caps were argued for.

## Decision

- **A done entry for an item with a dossier is short: what shipped and where,
  then the dossier link.** Evidence, derivations and review history stay in the
  dossier and the trace. The length that measured growth is duplication, and
  moving it costs nothing because the dossier already holds it. *Reverse if* a
  closed item's dossier proves insufficient to reconstruct what shipped, which
  would show the entry carrying load the dossier does not.
- **New completed entries only.** Released entries are not condensed: a rewrite
  of about 123k words of dated record is a large, unreviewable diff for a file
  read by lookup, and the old entries are the record their releases cite. The
  retirement sweep's factual corrections still reach them, and § Absorbed and
  § Decided against entries keep their own shape.
- **No length rule.** The shape is review-enforced and has no word or line cap,
  following [research § 9.1](../research/research-appropriate-level-of-detail.md)
  (no length rule beside Rule 7). ADR-0040's departure from § 9.1 rested on a
  reader who loads the file on every pick; this file has no such reader.
  **Bound** ([`DRIFT-RULES.md` Rule 7](../DRIFT-RULES.md#miss-rate)): nothing
  mechanical catches a long entry, so the rule holds only as far as review
  reads the register diff.
- **The migration opt-out is retired.** `gen_backlogid.py`'s R2 and R3 run on
  every section, and the `<!-- backlog: unconverted -->` marker exempts nothing:
  once no section needed it, it could only serve to escape the gate, which only
  review would see. Pinned by `tests/scripts/test_gen_backlogid.py`'s two
  retired-marker tests, written failing first.

## Consequences

- **Positive:** the register stops growing by duplication, and the one place
  that holds an item's evidence stays the dossier before and after close.
- **Positive:** the shape gate has no escape hatch; a re-added marker fails R3
  as preamble text.
- **Negative:** the short-entry shape is review-enforced only. Its miss rate is
  whatever review lets through; this record states that rather than claiming a
  gate.
- **Neutral:** the register keeps its long released entries, so its total and
  its older medians do not fall. Whether new entries follow the shape shows only
  in the next release section's median, and nothing schedules that measurement.
