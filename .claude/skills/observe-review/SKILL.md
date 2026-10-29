---
name: observe-review
description: Check a finished /observe record before its spec is written. Pairs each decision with its dialog, has two unprimed readers re-check the whole record, then reviews it against backends, SDKs and the runtime, adding what holds to the record's Open items. Use only when the maintainer types /observe-review after an /observe session was cleared. Not for deciding: a reopen session decides.
argument-hint: "<entry>"
disable-model-invocation: true
---

Check `sdd/observe/records/<entry>.md`, which `/observe` left Complete,
before its spec is written (RFC-0028). `$ARGUMENTS`'s first word is the entry.

## Rules

- **Never decide, never edit a decision.** Decisions, Environment rows and
  axis decisions stay as written. What holds goes to Open items as the next
  `<entry>/O<n>`, in `/observe` steps 3 and 4's shapes: a reopen of a
  decision (the conflict, the dependent decisions, what to decide with the
  maintainer, what it blocks), a ground conflict, a gap, or a note. Status
  stays Complete; each axis row lists the items that reopen, gap or depend
  on its decisions.
- **Quote what you re-read.** Each finding cites the record's words, read
  again before quoting. A claim about a backend, SDK or runtime is marked ✓
  when confirmed by reading its source or running it in this session, else
  `not run`. Searches run uncapped.

## Steps

1. **Pairs.** List the logs the record's sessions' dialogs went to, both
   halves of a split session included: the `decisions:` of the traces of the
   `/observe` sessions that wrote it (not an audit's or review's that also
   names it), plus each `sdd/decisions/` log in `git status` or `git diff
   --name-only origin/master...HEAD` whose questions are `<entry>`'s, which
   no trace lists yet (a reopen's, which step 4 adds). Run
   `hatch run observe-dialogs <record> <log> ...` and save its report as
   `tmp/observe-review/<entry>-pairs.md`. Each FAIL is a finding, but on a
   decision written before RFC-0028, which has no Asked line (OP-01's D1 to
   D44), "no Asked line" is not: the readers pair those decisions with the report's
   unpaired dialogs, listed with their answers (the brief's item 4).
2. **Unprimed readers.** Spawn two fresh `general-purpose` agents at once,
   each with the brief below, its placeholders filled, and nothing else from
   this session: no finding, no suspicion, no audit. Take the union: one run
   misses what another finds (RFC-0028, Evidence).
3. **Primed review**, yourself, while the readers run: per decision, does a
   backend (Memory, Local, S3, SFTP, Azure), its SDK or the Python runtime on
   a supported platform make it false, two-valued, or costly to keep? Read
   dependency source in the hatch env, Python and platform docs, vendor docs,
   and `src/remote_store/backends/` as evidence of what an SDK or the OS
   does, never as the expected answer (RFC-0024 § R1).
4. **Verify, write, commit.** Re-read every candidate, the readers' and
   yours, against what it cites, and drop what does not hold, or what an
   open item or an amending decision already covers (name which in the
   trace). Write the rest as open items, opened by one line naming this
   review and its date. Commit the record and the logs, a reopen's added to
   the `decisions:` of the `/observe` trace that wrote the record, then tell
   the maintainer which items need a reopen session.

## Reader brief

> Read `<record>` whole, then `<pairs>` (each decision beside the text of the
> option it adopts and the dialog that answered it; dialogs no decision
> pairs with, with their answers, at its end), then `sdd/observe/axes.md`
> and any file the record's Session section lists as ground read. Read
> nothing else. A decision with an **Amended by** line holds only as the
> decisions it names leave it. Report, quoting the words:
>
> 1. Two decisions that cannot both hold, counting the wording of an option a
>    Decision adopts, not only the Decision's own text.
> 2. A list, table or "only", "every", "none" claim that reads as complete,
>    checked against every decision that adds a member, later ones included.
> 3. A decision's reason that another decision's outcome makes false.
> 4. Text in a Decision that its dialog's question and answer do not cover:
>    a list, a table, a row, a case, a sentence about another step. A
>    decision the report shows with no dialog: first find its dialog among
>    the unpaired ones at the end, by question and answer; none found is
>    itself a finding.
>
> For each: the decisions, the quoted words, why they conflict. Propose no
> fix. Then list the candidates you checked and dropped, and why.
