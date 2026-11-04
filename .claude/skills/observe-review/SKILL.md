---
name: observe-review
description: Check a finished /observe record before its spec is written. Pairs each decision with its dialog, checks its tables, has two unprimed readers re-check the whole record, then reviews it against storage systems, SDKs and the runtime, adding what holds to the record's Open items; after a reopen or a close-out, says whether it can be frozen. Use only when the maintainer types /observe-review after an /observe session was cleared, or /observe-review <entry> close-out after a review. Not for deciding otherwise: a reopen session decides.
argument-hint: "<entry> [close-out]"
disable-model-invocation: true
---

Check `sdd/observe/records/<entry>.md`, which `/observe` left Complete,
before its spec is written (RFC-0028), and after its reopen, before its freeze
(RFC-0029), or closes it out (RFC-0030). `$ARGUMENTS`'s first word is the entry; a second word
`close-out` runs step 6 only.

## Rules

- **Never decide, never edit a decision**, but in a close-out (step 6).
  Decisions, Environment rows and
  axis decisions stay as written. What holds goes to Open items as the next
  `<entry>/O<n>`, in `/observe` steps 3 and 4's shapes: a reopen of a
  decision (the conflict, the dependent decisions, what to decide with the
  maintainer, what it blocks), a ground conflict, a gap, or a note. Write a
  reopen, ground conflict or gap only when it leaves what a caller observes
  false, two-valued or undecided, else a note, so the shape is the item's
  tag: the first three block a freeze, a note never does (RFC-0030 C1).
  Status stays Complete; each axis row lists the items that reopen, gap or
  depend on its decisions.
- **Quote what you re-read.** Each finding cites the record's words, read
  again before quoting. A claim about a storage system, SDK or runtime is marked ✓
  when confirmed by reading its own source or running it in this session,
  never through `src/remote_store/`, else `not run`. Searches run uncapped.

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
   unpaired dialogs, listed with their answers (the brief's item 4). It also
   lists split dialogs, dialogs with no answer in the logs given (add the
   missing log, re-run) and items asked in several dialogs (BK-510): one
   question answered two ways, with no decision naming both and which
   stands, is a finding.
   **Tables** (G3): declare each undeclared table in
   `sdd/observe/tables/<entry>.toml` (form: `scripts/observe_tables.py`), its
   domain from the enumeration the record names, a reading, never a decision;
   save `hatch run observe-tables <record> <declarations>` as
   `tmp/observe-review/<entry>-tables.md` after re-running with each
   declaration a re-read shows wrong fixed. Its findings are step 4's
   candidates; the readers never see it.
2. **Unprimed readers.** Spawn two fresh `general-purpose` agents at once,
   each with the brief below, its placeholders filled, and nothing else from
   this session: no finding, no suspicion, no audit. Take the union: one run
   misses what another finds (RFC-0028, Evidence).
3. **Primed review**, yourself, while the readers run: per decision, does a
   storage system (local filesystem, S3, SFTP, Azure Blob), its SDK or the
   Python runtime on a supported platform make it false, two-valued, or costly
   to keep? Read dependency source in the hatch env, Python and platform docs
   and vendor docs, or probe them; never 0.33's code, tests or specs
   (RFC-0024 § R1, RFC-0031 F2).
4. **Verify, write, commit.** Re-read every candidate, the readers' and
   yours, against what it cites, and drop what does not hold, or what an
   open item or an amending decision already covers (name which in this
   review's trace). Write the rest as open items, opened by one line naming this
   review and its date. Commit the record, the declarations and the logs, a
   reopen's added to the `decisions:` of the `/observe` trace that wrote the
   record, then tell the maintainer which items block a freeze, for a reopen
   session or a close-out (step 6), and which are notes.
5. **Freeze** (RFC-0029 R2), after a reopen or a close-out only: the record
   can be frozen when each open item is decided, routed with no `Flow done`
   (a note to the spec flow included, RFC-0030 C1), another entry's or
   `shared:`, each naming what it blocks; else name the items in
   the way. After the merge the maintainer tags that master commit
   `observe/<entry>/freeze-<n>` (`git tag -a`, `<n>` 1, then one past the
   last), not a release; this review never creates the tag.
6. **Close-out** (RFC-0030 C2, C3), after a review whose items the
   maintainer chose to close out: for each item that blocks a freeze, the
   answer that leaves the record's behaviour closest to the decisions it
   amends and to `io`, the SDK or the runtime as run. Ask them in one
   dialog: one question per item, the answer first and marked
   `(Recommended)`, and one routing every note (`AskUserQuestion`, four per
   call). No other question. Write each answer as a decision in
   `axes.md`'s reopen form, its Asked line quoting its own question, and one
   decision routing the notes (`Routed to <entry>'s spec flow by
   <entry>/D<m>.`); a Session line names the close-out, the review and the
   log. Then step 1 over the whole record, compared with step 1 run on the
   record as the review's commit left it (`git show <commit>:<record>`): a
   FAIL on a close-out decision, or a FAIL or table finding the earlier run
   did not report (line numbers aside), fails the check. And a re-read of each close-out
   decision against every decision it cites or amends: correct the close-out's
   own text before the commit, route a note. Commit with the log added to the
   `/observe` trace's `decisions:`, and give step 5's verdict; no full
   re-run follows a close-out.

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
