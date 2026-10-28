---
name: observe-review
description: Check a finished /observe record before its spec is written. Pairs each decision with its dialog, has an unprimed reader re-check the whole record, then reviews it against backends, SDKs and the runtime, adding what holds to the record's Open items. Use only when the maintainer types /observe-review after an /observe session was cleared. Not for deciding: a reopen session decides.
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

1. **Pairs.** List the logs the session's dialogs went to: each
   uncommitted `sdd/decisions/` log in `git status` whose questions are
   `<entry>`'s, both halves of a split session included; a log missed shows
   as a FAIL. Run
   `hatch run observe-dialogs <record> <log> ...` and save its report as
   `tmp/observe-review/<entry>-pairs.md`. Each FAIL is a finding.
2. **Unprimed reader.** Spawn one fresh `general-purpose` agent with the
   brief below, its placeholders filled, and nothing else from this
   session: no finding, no suspicion, no audit.
3. **Primed review**, yourself, while the reader runs: per decision, does a
   backend (Memory, Local, S3, SFTP, Azure), its SDK or the Python runtime on
   a supported platform make it false, two-valued, or costly to keep? Read
   dependency source in the hatch env, Python and platform docs, vendor docs,
   and `src/remote_store/backends/` as evidence of what an SDK or the OS
   does, never as the expected answer (RFC-0024 § R1).
4. **Verify, write, commit.** Re-read every candidate, the reader's and
   yours, against what it cites, and drop what does not hold. Write the rest
   as open items, opened by one line naming this review and its date. Commit
   the record and the logs, then tell the maintainer which items need a
   reopen session.

## Reader brief

> Read `<record>` whole, then `<pairs>` (each decision beside the text of the
> option it adopts and the dialog that answered it), then `sdd/observe/axes.md` and any file the record's Session
> section lists as ground read. Read nothing else. Report, quoting the words:
>
> 1. Two decisions that cannot both hold, counting the wording of an option a
>    Decision adopts, not only the Decision's own text.
> 2. A list, table or "only", "every", "none" claim that reads as complete,
>    checked against every decision that adds a member, later ones included.
> 3. A decision's reason that another decision's outcome makes false.
> 4. Text in a Decision that its dialog's question and answer do not cover:
>    a list, a table, a row, a case, a sentence about another step.
>
> For each: the decisions, the quoted words, why they conflict. Propose no
> fix. Then list the candidates you checked and dropped, and why.
