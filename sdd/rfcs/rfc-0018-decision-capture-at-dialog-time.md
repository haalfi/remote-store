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
verbatim: two hooks append each asked and answered event to a per-session JSONL
file under `sdd/decisions/<ID>/`, committed with the work. Three readers keep it
from being write-only: the trace links it, `check_traces.py` validates it, and
`/pr` renders it as the PR body's Decisions section.

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
same section describes. The research appendix's third
gap places this in the repository: every intent-layer control binds a decision
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

### D1. Capture: two hooks, no model involvement

A single script, `.claude/hooks/record-decision.py`, runs on three events with
matcher `AskUserQuestion`:

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

### D2. Storage: one append-only file per item and session

`sdd/decisions/<ID>/<session_id>.jsonl`, one JSON object per line, appended and
never rewritten. Committed with the work, so git supplies a timestamped history
and the PR diff shows the log beside the change it explains.

- **`<ID>`** comes from the branch name using the existing convention
  (`bk-396-…` → `BK-396`; prefixes per `sdd/BACKLOG.md` § ID prefixes). A
  branch with no ID, or a detached HEAD, writes to `sdd/decisions/_unfiled/`.
  Moving an unfiled log under its item is a `git mv`, not an edit.
- **Per session, not per item.** Two sessions on one item would otherwise
  append to one file and conflict at its end on every merge. Separate files
  cannot conflict.
- **Committed verbatim, decided by the maintainer** (§ Decided while drafting).
  The repository is public, so free-text answers become public with the PR.

### D3. Outcomes are derived by readers, never stored

A reader pairs events by `tool_use_id` and classifies each question:

| Outcome | Condition |
|---|---|
| `followed` | the answer equals the option label marked `(Recommended)` |
| `alternative` | the answer equals another option's label |
| `other` | the answer matches no label (the "Other" free-text path) |
| `unanswered` | `asked` with no `answered` or `failed` event |
| `failed` | a `failed` event |
| `prefilled` | the `asked` event's `tool_input` already carries answers |

`prefilled` exists because the tool's input schema accepts an `answers` field.
Whether anything other than the user's dialog ever fills it is undocumented
(§ Open Questions 2), and the BK-396 incident is the reason to look rather than
assume.

### D4. Readers

1. **Trace link.** `sdd/traces/_schema.yml` gains an optional `decisions:` key,
   a list of log paths. A trace for work that ran dialogs lists its logs.
2. **`check_traces.py`.** For each listed path: the file exists, every line
   parses, every event has a known kind, and no `tool_use_id` has two `answered`
   events. `unanswered` is reported, not failed. Declining a dialog is a
   legitimate act, and the report is how it stays visible.
3. **`/pr`.** The skill renders a "Decisions" section from the branch's logs,
   one line per question: header → answer → outcome, with `unanswered`,
   `failed` and `prefilled` flagged, and a link to each log. Reviewers see the
   why without anyone writing it.

### D5. Build order

0. **Observe the payload.** Register a probe that dumps raw payloads for the
   three events, then run one dialog that is answered, one answered with
   "Other", and one denied. This settles § Open Questions 1 and 2, and the
   outcome rules in D3 are adjusted to what is observed before any reader is
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
  `.claude/skills/pr/SKILL.md`; `sdd/CLAUDE-REFERENCE.md` § Interview mode,
  whose wiring table gains a Record layer and whose tolerated-divergence note
  extends to the new matcher values; `sdd/AUTHORING.md` directory defaults, for
  `sdd/decisions/`; `GATE-INVENTORY.md`, regenerated.
- **Cost per dialog:** two short Python invocations and two appended lines.

**Acceptance.** Step 0 observed and its payload shapes recorded in this RFC's
dossier. Then, after the next three merged deliveries that ran dialogs: each
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

**Decided by the maintainer while drafting**, in this RFC's own dialogs and
recorded as answered (hand-copied, because the recorder does not exist yet):

- Scope of "decision log": both rejected alternatives and the information
  snapshot. Answer: "Both (Recommended)".
- Visibility: "Commit verbatim (Recommended)".
- v1 readers: "Trace link + check, /pr Decisions section, Research doc update".
  The outcome report script was offered and not chosen.
- Framing: "RFC first", against the recommended "BK item + ADR".
- Research doc: "Amend Tao doc as correction", against the recommended "New
  research doc".
- Two dialogs did not settle what they asked. One received free-text answers
  ("Wait and let's further discuss", "Not yet"), `other` under D3; one was
  denied, `unanswered`. Both shaped the work, which is why D4 reports them
  rather than failing on them.

## References

- Host item: BK-397 (`sdd/BACKLOG.md` § 6).
- [`research-code-abundance-goals-and-values.md`](../research/research-code-abundance-goals-and-values.md)
  § 2.3 (correction of 2026-10-03), § 6 proposal 8, appendix § The gaps.
- [`CLAUDE.md` § Interview mode](../../CLAUDE.md#interview-mode);
  [`CLAUDE-REFERENCE.md` § Interview mode](../CLAUDE-REFERENCE.md#interview-mode-wiring).
- Claude Code hooks reference, `PreToolUse`, `PostToolUse` and
  `PostToolUseFailure` common input fields (code.claude.com/docs/en/hooks).
