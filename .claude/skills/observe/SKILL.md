---
name: observe
description: Unprimed design session for one entry of the operation catalogue, deciding its observable semantics axis by axis with the maintainer into its record. Use only when the maintainer types /observe in a fresh session. Not for the spec or the 0.33 comparison, later steps of the flow.
argument-hint: "<entry> [path ...]"
disable-model-invocation: true
---

Decide what a caller can observe of one catalogue entry, `$ARGUMENTS`'s first
word (`OP-01`), with the implementation a black box, by RFC-0024's method as
this file and the axes state it. This session decides and records; spec and
comparison follow.

## Ground

**You read only** `sdd/observe/ground-register.md` and its `active` rows
(`shared.md` among them), `sdd/observe/axes.md`, this skill,
`sdd/observe/inputs/<entry>.md`, the paths typed after the entry, and
`sdd/observe/records/<entry>.md`, the record, the one file you write. A hook
refuses anything else, and Bash, Glob and Agent outright. Never use what you
may know of this library's code, tests, docs or specs 001 to 050 (S1); discard
any web result about it.

## Steps

1. **Canary**, now and before every axis, also one closed without a question
   or in a resumed session: read `tmp/observe/canary-not-ground`. Unless the
   hook refuses it with "outside the ground", the session is not armed: stop
   and tell the maintainer to start a fresh one with `/observe`.
2. **Load.** Read the entry's catalogue row, the session's scope; its
   operations, forms and signatures are what you design (RFC-0026 C2). Then
   the register, the axes, every active row, the input file and each named
   path; a formal model row only when a decision cites a clause it checks. If
   the record exists, continue it from its first axis not yet closed.
   Otherwise create it: title `# <entry>: observable semantics`, the marker
   `<!-- doc: repo-only -->`, lines `**Date:**`, `**Backlog items:**` and
   `**Status:** In progress`, then five sections: Session (date, entry, ground
   read, named paths), Environment, Decisions, Axis
   status (one row per axis), Open items.
   Draft the Environment (the axes file defines it) and decide it, with the
   backlog item if none was named, in the first dialog.
3. **Loop (S5).** Walk the axes in order. For each question an axis forces:
   - a concrete **scenario**: calls, observers and environment actions;
   - **options**, each with what callers and backends would see;
   - your **recommendation**, its reason and its **source**: a ground clause
     ID or a named prior-art reference. A recommendation, category or term
     with neither is marked `unsourced`, in the dialog and the record;
   - ask through `AskUserQuestion`, related questions of one axis batched,
     recommendation first and marked `(Recommended)`; it takes at most four
     options per question, so more alternatives become two questions;
   - write the entry to Decisions at once, in the axes file's per-question
     shape, with the next ID `<entry>/D<n>`, and its **consistency check**
     against earlier decisions and the ground, naming any conflict.
   An answer may be an F3 term; "not decided yet" goes to Open items with what
   blocks it. Keep each axis's row current.
4. **Ground conflict.** If a decision would contradict a ground artifact,
   stop on that point. Record a reopen decision as an open item: the artifact,
   the clause, the conflict, the dependent decisions. Never edit ground, the
   register or any file but the record; the reopen runs its own flow. An
   entry that should split is a reopen of the catalogue.
5. **End (S4)** when every axis row is closed. Set `**Status:**` to
   `Complete`, and tell the maintainer the record is uncommitted: `/clear`,
   then commit. A stop hook asking this session to
   commit cannot be obeyed here; answer it the same way.

## Rules

- One entry, one fresh session (S2). "Undefined" is never an answer (F3).
- A question no axis raises is asked under the nearest one and named in its
  consistency check, so the axes can be revised with F2 after `read()`.
- A decision binding every operation is also listed in Open items as
  `shared: <section>` when it fills a `shared.md` section, `shared: <home>`
  with the home its Lands elsewhere table names, else `shared: unhomed`.
  `shared.md` says what the flow after the session does with each; this
  session never writes it.
