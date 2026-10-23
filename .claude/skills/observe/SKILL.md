---
name: observe
description: Unprimed design session for one Store operation, deciding its observable semantics axis by axis with the maintainer into its research doc. Use only when the maintainer types /observe in a fresh session. Not for the spec or the 0.33 comparison, later steps of the flow.
argument-hint: "<operation> [path ...]"
disable-model-invocation: true
---

Decide what a caller can observe of one operation, `$ARGUMENTS`'s first word,
with the implementation a black box, by RFC-0024 D4 and D11 and research § 4's
S1 to S5. This session decides and records; spec and comparison come later.

## Ground

**You read only the ground** (`active` rows of `sdd/ground-register.md`),
the method files, the paths named after the operation, and
`sdd/research/research-observe-<op>.md`, the one file you write. A hook refuses
every other read, and Bash, Glob and Agent outright. Never
use what you may know of this library's code, tests, docs or specs 001 to 050
(S1), and discard any web result about it.

## Steps

1. **Canary**, now and again before every axis, a resumed session included.
   Read `tmp/observe/canary-not-ground`. The hook must refuse it with "outside
   the ground". Any other answer, "file does not exist" included, means the
   session is not armed: stop and tell the maintainer to start a fresh session
   with `/observe`.
2. **Load.** Read the register, the axes and each named path. If the research
   doc exists, this session continues it: read it and resume at its first
   axis that is neither decided, open nor not applicable. Otherwise create it
   from `sdd/templates/research-template.md`'s header (`**Date:**`,
   `**Backlog items:**` the item the maintainer names, `**Status:** In
   progress`) with five sections: Session (date, operation, the ground read,
   the named paths), Environment, Decisions, Axis status (one row per axis),
   Open items. Environment is the operation's one list of actions O2, O3 and
   the world may take, faults included, each `<op>/E<n>`; axes cite its rows,
   and a new action is added only through a decision.
3. **Loop (S5).** Walk the axes in order. For each question an axis forces:
   - a concrete **scenario**: calls, observers and environment actions;
   - **options**, each with what callers and backends would see;
   - your **recommendation** and its reason;
   - ask through `AskUserQuestion`, related questions of one axis batched,
     recommendation first and marked `(Recommended)`;
   - write the entry to Decisions at once, in the axes file's per-question
     shape, with the next ID `<op>/D<n>`, and its **consistency check**
     against earlier decisions and the ground, naming any conflict.
   An answer may be an F3 term; "not decided yet" goes to Open items with what
   blocks it. Keep each axis's row current (decided, open, or not applicable
   with a reason).
4. **Ground conflict.** If a decision would contradict a ground artifact,
   stop on that point. Record a reopen decision as an open item: the artifact,
   the clause, the conflict, the dependent decisions. Never edit ground, the
   register or any file but the research doc; the reopen runs its own flow.
5. **End (S4)** when every axis row is decided, open or not applicable. Set
   `**Status:**` to `Research complete — ready for design decisions`, and tell
   the maintainer the doc is uncommitted: `/clear`, then commit.

## Rules

- One operation, one fresh session (S2). "Undefined" is never an answer (F3).
- A question no axis raises is asked under the nearest one and named in its
  consistency check, so the axes can be revised with F2 after `read()`.
