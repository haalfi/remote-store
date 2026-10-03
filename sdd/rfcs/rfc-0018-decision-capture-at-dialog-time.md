# RFC-0018: Capture interview decisions where they are made

## Status

Draft, 2026-10-03. Tracked as **BK-397**. Nothing below is built; § Build order
step 0 is a live observation this RFC cannot make on its own (§ Open Questions 1).

## Summary

Decisions in this repository are mostly taken mid-work in `AskUserQuestion`
dialogs ([`CLAUDE.md` § Interview mode](../../CLAUDE.md#interview-mode)). A
dialog already holds what a decision record needs: the question with its
context, the options with their consequences, the agent's recommendation and the
answer. It persists only in the session transcript, outside the repository, so
the next session re-argues the why from the code. This RFC keeps the dialog
verbatim: one script, registered on three hook events, appends each asked,
answered and failed event to a per-session JSONL file,
`sdd/decisions/<session_id>.jsonl`, committed with the work. Logs are bound to a
branch when read, not when written. Three readers keep them from being
write-only: the trace links them, `check_traces.py` validates them, and `/pr`
renders them as the PR body's Decisions section.

## Motivation

**The rationale is lost at a known point, and reconstruction is the failure
mode, not the fix.**
[Research § 2.3](../research/research-code-abundance-goals-and-values.md), as
corrected on 2026-10-03, finds most of intent debt forward-only. The code
records the behaviour that was implemented, not whether it was decided: a
deliberate choice and an accident look identical in it. That it was chosen, the
rejected alternatives and what was known at the time are all outside the
artifact. An agent asked later for the why writes the most plausible one, for an
accident as readily as for a decision, which is the fabrication mechanism the
same section describes.
[`research-decision-capture-at-dialog-time.md`](../research/research-decision-capture-at-dialog-time.md)
places this in the repository: every intent-layer control binds a decision
taken before implementation, and none binds one taken during it.

**The record already exists, at zero authoring cost.** The `AskUserQuestion`
call that put this RFC's framing to the maintainer carried four questions, each
with two to four options, a consequence per option and a marked recommendation.
That is every field an after-the-fact ADR would try to rebuild, written before
the answer was given. What is missing is persistence and a reader, not content.

**Three properties of a dialog log that a written summary lacks.**

1. **Rejected options survive.** They are in the `asked` event whether or not
   anyone thinks to mention them later.
2. **The outcome is observable, including "no decision".** A dialog that was
   denied or closed has an `asked` event and no `answered` event. A parallel
   session on BK-396 showed the failure this guards: its dialog "recorded Q1"
   before the maintainer had answered, the choice was pushed, and the session
   noticed only afterwards and re-asked. A summary would have recorded Q1 as the
   maintainer's decision.
3. **Divergence from the recommendation is countable.** A choice is half a
   decision; the other half is the framing, and the agent wrote it: which
   options exist, what each costs, which is recommended. That is why D1 keeps
   the `asked` event and not only the answer. Whether the maintainer took the
   recommendation, another listed option, or free text is visible per question.
   This is an audit signal for research § 6 proposal 8, not a target.

## Proposal

### D1. Capture: one script, three event registrations, no model involvement

A single script, `.claude/hooks/record-decision.py`, is registered on three
events with matcher `AskUserQuestion`:

| Event | Appends | Payload kept |
|---|---|---|
| `PreToolUse` | `asked` | `tool_input` verbatim (questions, headers, options with descriptions, `multiSelect`) |
| `PostToolUse` | `answered` | `tool_input` and `tool_response` verbatim |
| `PostToolUseFailure` | `failed` | the error payload verbatim |

Every event also carries `tool_use_id` (the pairing key, documented as common to
all three events), `session_id`, a UTC timestamp, `HEAD`'s SHA and the branch
name. The `PreToolUse` registration sits beside the existing notification hook
under the same matcher.

**Fail-open.** The script never blocks a dialog: any error exits 0 with a
one-line stderr note. A recorder that can stop the decision it records inverts
its purpose.

**Verbatim, not parsed.** The script stores payloads as received and does not
interpret them. Interpretation lives in the readers (D3), so a payload-shape
change in Claude Code breaks a reader's parse, which a test sees, rather than
silently losing data at capture time.

### D2. Storage: one append-only file per session, bound to work when read

`sdd/decisions/<session_id>.jsonl`, one JSON object per line, appended and never
rewritten. Committed with the work, so git supplies a timestamped history and
the PR diff shows the log beside the change it explains.

- **No item ID in the path.** The ID is not knowable at capture time: branch
  names need not carry one (`CLAUDE.md` § Branching lists `fix-streaming-io`),
  and dialogs are asked *before* the work, often while HEAD is still the base
  branch or detached (`/ship` Step 2 asks in plan mode, before Step 3 builds).
  This RFC's own branch, `rfc-decision-capture`, has no ID. Each event records
  branch and HEAD instead, and D4 binds logs to work when they are read.
- **Per session.** Two sessions never append to one file, so logs cannot
  conflict on merge.
- **Exempt from the tree-unchanged checks.** The recorder writes while a review
  round may be running. `/ship`'s main-tree `git status --porcelain` capture and
  `/orchestrate`'s porcelain and `git diff HEAD` captures exclude
  `sdd/decisions/` by pathspec (`-- . ':(exclude)sdd/decisions/'`), so a dialog
  during a round does not read as a contaminated pass. The exemption is safe
  because the recorder only appends to files no reviewer writes.
- **Committed verbatim, decided by the maintainer** (§ Decided while drafting).
  The repository is public, so free-text answers become public with the PR.

### D3. Outcomes are derived by readers, never stored

A reader pairs events by `tool_use_id` and classifies each question. Its
**recommended set** is the labels marked `(Recommended)`, usually one and
possibly several on a `multiSelect` question. Its **answer set** is the one
label chosen, or for `multiSelect` every label chosen:

| Outcome | Condition |
|---|---|
| `followed` | the answer set equals the recommended set |
| `alternative` | every answer is an option label, and the set differs from the recommended set (or no option was recommended) |
| `other` | some answer matches no label (the "Other" free-text path) |
| `unanswered` | `asked` with no `answered` or `failed` event |
| `failed` | a `failed` event |
| `prefilled` | the `asked` event's `tool_input` already carries answers |

How a multi-select answer is encoded is as undocumented as a single one, so the
set is parsed by rules step 0 fixes, not assumed. A free-text entry inside a
multi-select answer makes the question `other`.

`prefilled` exists because the tool's input schema accepts an `answers` field.
Whether anything other than the user's dialog ever fills it is undocumented
(§ Open Questions 2), and the BK-396 incident is the reason to look rather than
assume.

### D4. Readers

0. **Binding rule, shared by every reader.** An event belongs to a branch when
   its recorded branch is that branch, or when it ran on the base branch, a
   detached HEAD or another branch with no item ID, and the next named-branch
   event in the same session is on that branch. That captures dialogs asked
   before the branch existed without a manual move. A session whose events never
   name the branch is still bound when its `session_id` appears in a
   `Claude-Session` trailer on `origin/<base>..HEAD`, if step 0 shows the two
   identifiers correspond (§ Open Questions 4).
1. **Trace link.** `sdd/traces/_schema.yml` gains an optional `decisions:` key,
   a list of log paths. A trace for work that ran dialogs lists its logs.
2. **`check_traces.py`.** For each listed path: the file exists, every line
   parses, every event has a known kind, and no `tool_use_id` has two `answered`
   events. `unanswered` is reported, not failed. Declining a dialog is a
   legitimate act, and the report is how it stays visible.
3. **`/pr`.** The skill renders a "Decisions" section from the events the
   binding rule assigns to the branch, one line per question: header → answer → outcome, with `unanswered`,
   `failed` and `prefilled` flagged, and a link to each log. Reviewers see the
   why without anyone writing it.

### D5. Build order

0. **Observe the payload.** Register a probe that dumps raw payloads for the
   three events, then run one dialog that is answered, one answered with
   "Other", one multi-select, and one denied, and record each payload's shape
   in § Step 0 observations below. This settles § Open Questions 1, 2 and 4,
   and D3's rules are adjusted to what is observed before any reader is
   written.
1. Recorder and `settings.json` registration, with tests in
   `tests/scripts/test_claude_hooks.py` that feed recorded payloads to the
   script and assert the appended lines.
2. Schema key and `check_traces.py` rule, each with a failing fixture seen red
   first, per `sdd/TESTING.md`.
3. The `/pr` rendering.

## Alternatives Considered

- **Harvest the session transcript at `/pr` time.** Rejected: the transcript
  is outside the repo, decisions span sessions, and a harvest at the end is the
  late reconstruction this RFC exists to avoid.
- **The agent writes decisions into the trace by hand.** Rejected: it depends on
  compliance at exactly the moment attention is elsewhere, and it is a summary,
  not the record.
- **Write the log into the trace YAML from the hook.** Rejected: a hook
  rewriting structured YAML mid-session races the agent's own edits to the same
  file, and a trace may not exist yet when the first dialog runs.
- **An ADR per decision.** Rejected: most dialog decisions are too small for an
  ADR. The log is the raw record an ADR may later cite.
- **`git notes`.** Rejected: not pushed by default, absent from the PR diff, and
  read by no existing tool.

## Impact

- **Public API:** none. **Backwards compatibility:** internal process only.
- **Ripples:** `.claude/settings.json`; `.claude/hooks/record-decision.py`;
  `tests/scripts/test_claude_hooks.py` and CI's `HOOKS_PAT`, per the
  ripple-check row for a test whose subject is outside `src/`;
  `sdd/traces/_schema.yml`; `scripts/check_traces.py` and its tests;
  `.claude/skills/pr/SKILL.md`; `.claude/skills/ship/SKILL.md` and
  `.claude/skills/orchestrate/SKILL.md`, whose tree-unchanged captures take
  D2's exclusion; `sdd/CLAUDE-REFERENCE.md` § Interview mode,
  whose wiring table gains a Record layer and whose tolerated-divergence note
  extends to the new matcher values; `sdd/AUTHORING.md` directory defaults, for
  `sdd/decisions/`; `GATE-INVENTORY.md`, regenerated.
- **Cost per dialog:** two short Python invocations and two appended lines (the
  `PreToolUse` one, then whichever of the two Post events fires).

**Acceptance.** Step 0 observed and its payload shapes recorded in § Step 0
observations. Then, after the next three merged deliveries that ran dialogs: each
lists its logs in its trace, each PR body carries a Decisions section rendered
from them, and `check_traces.py` passes on all three. The ADR is written once
those three are read.

## Open Questions

1. **Do answers reach the hook?** The hooks reference documents that
   `PostToolUse` fires and carries `tool_input` and `tool_use_id`. It does not
   document whether the user's answers appear in `tool_input`, in
   `tool_response`, or neither. The tool's result text in a session reads
   `"<question>"="<answer>"`, so a parser over `tool_response` is the fallback
   if `tool_input` carries none. Step 0 decides. The agent cannot run step 0
   alone: registering the probe edits harness configuration, which this
   session's permission mode refused, so the maintainer authorizes or registers
   it.
2. **What does a denied or closed dialog send?** Whether `PostToolUseFailure`
   fires for a denial, a dismissal or a timeout is undocumented. If none fires,
   `unanswered` is still derived from a lone `asked` event, which is why D3 does
   not depend on it.
3. **Secrets in free text.** Verbatim capture commits whatever the maintainer
   types. Whether `gate-commit.sh` should scan `sdd/decisions/` for credential
   shapes is open.
4. **Does the hook's `session_id` match the `Claude-Session` trailer?** The
   trailer carries a claude.ai session URL; the hook payload carries a
   `session_id` of undocumented form. If they do not correspond, D4's trailer
   fallback is dropped and binding rests on recorded branch names alone.

**Decided by the maintainer while drafting**, in this RFC's own dialogs and
recorded as answered (hand-copied, because the recorder does not exist yet):

- Scope of "decision log": both rejected alternatives and the information
  snapshot. Answer: "Both (Recommended)".
- Visibility: "Commit verbatim (Recommended)".
- v1 readers: "Trace link + check, /pr Decisions section, Research doc update".
  The outcome report script was offered and not chosen.
- Framing: "RFC first", against the recommended "BK item + ADR".
- Research doc: "Amend Tao doc as correction", against the recommended "New
  research doc". Revised after review: "Split: correction + new doc", because
  the added material went beyond a correction.
- Log binding, after review: "Session file, bind at read (Recommended)".
- Review-round interference, after review: "Exempt sdd/decisions/
  (Recommended)", against gitignored staging, whose logs a reclaimed container
  would lose.
- Two dialogs did not settle what they asked. One received free-text answers
  ("Wait and let's further discuss", "Not yet"), `other` under D3; one was
  denied, `unanswered`. Both shaped the work, which is why D4 reports them
  rather than failing on them.

## Step 0 observations

Empty until step 0 runs. Per dialog kind (answered, "Other", multi-select,
denied): which events fired, and where the answer sits in each payload.

## References

- Host item: BK-397 (`sdd/BACKLOG.md` § 6).
- [`research-code-abundance-goals-and-values.md`](../research/research-code-abundance-goals-and-values.md)
  § 2.3 (correction of 2026-10-03), § 6 proposal 8.
- [`research-decision-capture-at-dialog-time.md`](../research/research-decision-capture-at-dialog-time.md).
- [`CLAUDE.md` § Interview mode](../../CLAUDE.md#interview-mode);
  [`CLAUDE-REFERENCE.md` § Interview mode](../CLAUDE-REFERENCE.md#interview-mode-wiring).
- Claude Code hooks reference, `PreToolUse`, `PostToolUse` and
  `PostToolUseFailure` common input fields (code.claude.com/docs/en/hooks).
