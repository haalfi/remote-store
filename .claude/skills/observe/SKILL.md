---
name: observe
description: Unprimed design session for one entry of the operation catalogue, deciding its observable semantics axis by axis with the maintainer into its record, or, on a Complete record, the open items its review left. Use only when the maintainer types /observe in a fresh session, or /observe release to end one. Not for the spec or the 0.33 comparison, later steps of the flow.
argument-hint: "<entry> [path ...] | release"
disable-model-invocation: true
---

Decide what a caller can observe of one catalogue entry, `$ARGUMENTS`'s first
word (`OP-01`), with the implementation a black box, by RFC-0024's method as
this file and the axes state it. This session decides and records; spec and
comparison follow.

## Ground

In an armed session (every step but 0), **you read only**
`sdd/observe/ground-register.md` and its `active` rows (`shared.md` among
them), `sdd/observe/axes.md`, this skill, `sdd/observe/inputs/<entry>.md`, the
paths typed after the entry, and `sdd/observe/records/<entry>.md`, the record,
the one file you write. A hook refuses anything else, and Bash, Glob and Agent
outright. Never use what you
may know of this library's code, tests, docs or specs 001 to 050 (S1); discard
any web result about it.

## Steps

0. **`release`** as `$ARGUMENTS`: the hook released this session. Ground no
   longer binds it, but no record is written or staged here. Commit every
   uncommitted `sdd/decisions/` log in this tree, a dialog split across two
   session ids included, then stop: skip steps 1 to 5. A finished record is
   committed after `/clear`, by a session with no marker.
1. **Canary**, now and before every axis (in a reopen, every item), also
   one closed without a question or in a resumed session: read `tmp/observe/canary-not-ground`. Unless the
   hook refuses it with "outside the ground", the session is not armed: stop
   and tell the maintainer to start a fresh one with `/observe`.
2. **Load.** Read the session's scope in the catalogue: the entry's row,
   whose operations, forms and signatures you design (RFC-0026 C2), and each
   Not in v1 row it leaves to this entry, such as a *Form of* it, decided like
   a question no axis raises (Rules). Then the register, the axes, every
   active row but the formal models, the input file and each named path; a
   formal model row only when a decision cites a clause it checks. A record
   In progress continues at its first open axis, `In progress (reopen)` at its
   first undecided item; a Complete one is set to the latter, and Session
   gains a line for the reopen: date, ground read, named paths (step 3).
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
     shape, with the next ID `<entry>/D<n>`, an **Asked** line per dialog
     that answered it in the axes file's exact form, and its **consistency check** against earlier
     decisions and the ground, naming any conflict. A claim in the Decision
     that no dialog answered, such as a list, a table or a case, is asked
     first.
   An answer may be an F3 term; "not decided yet" goes to Open items with what
   blocks it. Keep each axis's row current.

   **Reopen** (RFC-0028 P3): walk the Open items, not the axes, but none
   tagged `shared:` or for another entry's session; ask a ground conflict
   its route only, a ground reopen staying open (step 4). Ask each as above,
   sourced to the item (a ✓ on 0.33's code shows what an SDK or OS does,
   never the answer); each answer, "as is" too, is a new decision in
   axes.md's reopen form.
4. **Ground conflict.** If a decision would contradict a ground artifact,
   stop on that point. Record a reopen decision as an open item: the artifact,
   the clause, the conflict, the dependent decisions. Never edit ground, the
   register or any file but the record; the reopen runs its own flow. An
   entry that should split is a reopen of the catalogue.
5. **End (S4)** when every axis row is closed, and every item a reopen walks
   decided or open with what blocks it. First re-read the record
   whole and re-run each consistency check against every decision, later
   ones included, not only those it names: each list, table or "only" claim
   against every decision that adds to it, each reason against every
   outcome, and an option a Decision adopts by its own wording. Ask each
   conflict as in step 3; its answer is an amendment in axes.md's form. Then set `**Status:**` to `Complete`, and tell the maintainer the
   record is uncommitted: `/clear`, then `/observe-review <entry>`, which
   checks and commits it. A stop hook asking this session to
   commit cannot be obeyed here; answer it the same way. Resumed armed after
   `/clear`? The maintainer types `/observe release`.

## Rules

- One entry, one fresh session (S2). "Undefined" is never an answer (F3).
- A question no axis raises is asked under the nearest one and named in its
  consistency check, so the axes can be revised with F2 after `read()`.
- A decision binding every operation is also listed in Open items as
  `shared: <home>`: a `shared.md` section, a home its Lands elsewhere table
  names, or `unhomed`. Where it lands is decided after this session, never in
  it; this session never writes `shared.md`.
