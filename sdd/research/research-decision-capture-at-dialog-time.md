# Research: Decision Capture at Dialog Time

**Date:** 2026-10-03
**Backlog items:** BK-397
**Status:** Research complete. Point-in-time snapshot per [`sdd/000-process.md` § Document types](../000-process.md#document-types). It extends the corrected § 2.3 of [`research-code-abundance-goals-and-values.md`](research-code-abundance-goals-and-values.md) to this repository's workflow; [RFC-0018](../rfcs/rfc-0018-decision-capture-at-dialog-time.md) proposes the mechanism.

## TL;DR

Most of intent debt can only be paid when the decision is made, and in this
repository decisions are mostly made in `AskUserQuestion` dialogs whose full
record is discarded. Keeping the dialog verbatim is the preventive control; the
rest of this record argues why it has to be kept rather than summarised, and
where the repository's existing controls stop short.

## 1. What the code cannot tell a later reader

**The code records behaviour, not decisions.** The corrected § 2.3 of the
code-abundance record states the argument: that a behaviour was chosen, which
alternatives were rejected, and what was known at the time are never in the
code, and a later reconstruction is a guess that fails both ways. This record
does not restate it; it takes it as the premise.

## 2. With agents, rationale written afterwards is wrong, not just incomplete

**The PR body or ADR an agent writes at the end of a session comes from a model
that no longer has the decision in its context**, after a context compaction or
in a new session. It states the most plausible why, which is the fabrication
mechanism the code-abundance record's § 2.3 describes for unstated constraints.
So that record's paydown remedy for intent debt, "write the ADR afterwards", is
how wrong rationale enters the record for the forward-only part of the debt. The
control is to store the decision when it is made.

## 3. Where the repository's controls stop

**Every intent-layer control in the code-abundance record's appendix binds a
decision taken before implementation; none binds one taken during it.** "No
implementation without a spec section" and "decision records immutable once
accepted" both act before or after the work. By the maintainer's account,
decisions here are mostly taken mid-work in the structured dialogs
[`CLAUDE.md` § Interview mode](../../CLAUDE.md#interview-mode) requires. So the
appendix's claim that the repository "orders the work so that neither is taken
on" holds for intent debt only up to the first mid-work decision.

## 4. The record already exists

**A dialog holds every field an after-the-fact ADR would try to rebuild**: the
question with its context, the options with their consequences, the agent's
recommendation, and the answer. It is written before the answer is given, at no
authoring cost. It persists only in the session transcript, outside the
repository, and no later session reads it. What is missing is persistence and a
reader, not content.

This adds one control to the code-abundance record's preventive table for
intent debt: **a decision taken mid-work is captured verbatim where it is made,
rejected alternatives included.**

## 5. Evidence and limits

**This record is argued, not measured.** Two observations support it, and
neither is a count:

- The maintainer's account that mid-work dialogs are where most decisions here
  are taken. No log exists to check it against, which is the gap itself.
- A parallel session on BK-396 reported a dialog that "recorded Q1" before the
  maintainer had answered; the choice was pushed and the session re-asked
  afterwards. A summary written later would have recorded Q1 as the
  maintainer's decision. A raw log with the dialog's outcome would show it as
  unanswered.

What would test it: once RFC-0018's recorder runs, the share of a delivery's
PR-level rationale that its dialog log already contains, and whether later
sessions cite the log.
