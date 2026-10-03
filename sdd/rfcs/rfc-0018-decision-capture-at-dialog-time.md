# RFC-0018: Capture interview decisions where they are made

## Status

Draft, 2026-10-03. Tracked as **BK-397**. Nothing below is built. § Build order
step 0 ran on 2026-10-03 (§ Step 0 observations); D1, D3 and D4.0 are amended
to what it observed.

## Summary

Decisions in this repository are mostly taken mid-work in `AskUserQuestion`
dialogs ([`CLAUDE.md` § Interview mode](../../CLAUDE.md#interview-mode)). A
dialog already holds what a decision record needs: the question with its
context, the options with their consequences, the agent's recommendation and the
answer. It persists only in the session transcript, outside the repository, so
the next session re-argues the why from the code. This RFC keeps the dialog
verbatim: one hook, registered on three hook events, appends each asked,
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

### D1. Capture: one hook, three event registrations, no model involvement

A thin hook, `.claude/hooks/record-decision.sh`, is registered on three events
with matcher `AskUserQuestion` and runs the recorder,
`scripts/record_decision.py`:

| Event | Appends | Payload kept |
|---|---|---|
| `PreToolUse` | `asked` | `tool_input` verbatim (questions, headers, options with descriptions, `multiSelect`) |
| `PostToolUse` | `answered` | `tool_input` and `tool_response` verbatim |
| `PostToolUseFailure` | `failed` | the error payload verbatim |

Every event also carries `tool_use_id` (the pairing key, documented as common to
all three events), `session_id`, a UTC timestamp, `HEAD`'s SHA and the branch
name, plus the hook process's `CLAUDE_CODE_REMOTE_SESSION_ID` when set, which is
the identifier D4.0's trailer fallback matches (step 0 found the payload's
`session_id` does not). The `PreToolUse` registration sits beside the existing
notification hook under the same matcher.

**Fail-open, including when the recorder cannot start.** The hook never blocks
a dialog. A recorder that can stop the decision it records inverts its purpose.
Errors inside the recorder are caught and noted on stderr, but that alone is not
enough: a missing or renamed `.py` makes CPython exit 2 before any line runs,
and exit 2 from a `PreToolUse` hook blocks the tool. So the `.sh` wrapper runs
the recorder and then exits 0 unconditionally. The split also places the Python
under `scripts/`, inside `lint` and `format`, and puts a `.sh` path in
`settings.json`, which the existing existence check in
`tests/scripts/test_claude_hooks.py` matches (its regex accepts `.sh` only).

**Verbatim, not parsed.** The recorder stores payloads as received and does not
interpret them. Interpretation lives in the readers (D3), so a payload-shape
change in Claude Code breaks a reader's parse, which a test sees, rather than
silently losing data at capture time.

### D2. Storage: one append-only file per session, bound to work when read

`sdd/decisions/<session_id>.jsonl`, one JSON object per line, appended and never
rewritten. Committed with the work, so git supplies a timestamped history and
the PR diff shows the log beside the change it explains.

- **Who commits it.** `gate-commit.sh`, which already runs before every
  `git commit` the agent issues, stages `sdd/decisions/` into that commit, so
  the log travels with the work it explains. Dialogs after the branch's last
  commit (`/ship`'s close, `/pr`'s own questions) leave a tail: `/pr` Step 1
  commits it as a separate `decision log` commit before its clean-tree check.
  Bound: a commit the maintainer makes by hand outside the agent bypasses the
  hook, and its dialogs reach the next agent commit instead.

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

A reader pairs events by `tool_use_id` and gives each question exactly one
outcome: the first row, top to bottom, whose condition holds. Its **recommended
set** is the labels marked `(Recommended)`, usually one and possibly several on a
`multiSelect` question. Its **answer set** is the one label chosen, or for
`multiSelect` every label chosen:

| Outcome | Condition (first match wins) |
|---|---|
| `failed` | a `failed` event exists |
| `prefilled` | the `asked` event's `tool_input` carries an answer for the question and the `answered` event's answer equals it |
| `unanswered` | no `answered` event |
| `other` | some answer matches no label (the "Other" free-text path) |
| `followed` | the answer set equals the recommended set |
| `alternative` | otherwise: every answer is a label and the set differs from the recommended set, or nothing was recommended |

The order ranks what a reviewer must see first: a failure or an answer nobody
gave outranks what the answer was.

**Parsing rules, fixed by step 0.** The answer is read from the `answered`
event's `tool_response.answers`, a map from question text to one string (its
`tool_input.answers` carried the same map in every observation). Never read
answers from the `answered` event's `tool_input` to detect prefill: the harness
writes the user's answers into it, so every answered dialog would look
prefilled. Free text carries no marker: an "Other" answer is just a string that
matches no label, and free text identical to a label is indistinguishable from
choosing it. A multi-select answer is the chosen labels and any free text joined
by `", "` into one string. A reader matches labels against it as whole
`", "`-delimited segments, longest label first, so a label that itself contains
`", "` still parses; any residue is free text and makes the question `other`.
Answers are keyed by question text, so two questions with identical text in one
call cannot be told apart.

`prefilled` exists because the tool's input schema accepts an `answers` field,
and the BK-396 incident is the reason to look rather than assume. Step 0 found
that an agent-supplied `answers` reaches `PreToolUse` verbatim, the dialog was
still shown, and the user's choice replaced it in the `answered` event. So a
prefill only taints the outcome when the final answer equals it: the dialog may
have been skipped or the maintainer may have chosen the same, and the payload
cannot tell which. When the final answer differs, the user overrode the prefill
and the question is classified by the rows below it.

### D4. Readers

0. **Binding rule, shared by every reader.** A *work branch* is any branch
   other than the base branch; detached HEAD is none. An event recorded on a
   work branch belongs to that branch and no other. An event recorded on the
   base branch or a detached HEAD belongs to the next work branch the same
   session records an event on, if any. That captures dialogs asked before the
   branch existed without a manual move, and binds each event once. Whether a
   branch name carries an item ID plays no part. A session whose events never
   name a work branch is still bound when a `Claude-Session` trailer on
   `origin/<base>..HEAD` matches its recorded `CLAUDE_CODE_REMOTE_SESSION_ID`:
   trailer `…/session_<X>` matches `cse_<X>`. The payload's `session_id` cannot
   serve: it is a UUID with no observed relation to the trailer (§ Step 0
   observations, Open Questions 4). A session where the variable is unset has
   no trailer fallback.
1. **Trace link.** `sdd/traces/_schema.yml` gains an optional `decisions:` key,
   a list of log paths. A trace for work that ran dialogs lists its logs.
2. **`check_traces.py`.** For each listed path: the file exists, every line
   parses, every event has a known kind, and no `tool_use_id` has two `answered`
   events. `unanswered` is reported, not failed. Declining a dialog is a
   legitimate act, and the report is how it stays visible. A `tool_use_id`
   with both an `answered` and a `failed` event is also reported: D3 still
   classifies it, but it contradicts the assumption that the two Post events are
   exclusive, which step 0 could not test: no `failed` event fired in it, so
   that assumption and D3's `failed` row still need an observation.
3. **`/pr`.** The skill renders a "Decisions" section from the committed log
   only, after Step 1 has committed the tail, so the body never cites an event
   the PR does not contain. One line per question: header → answer → outcome,
   with `unanswered`, `failed` and `prefilled` flagged, and a link to each log.
   Reviewers see the why without anyone writing it.

### D5. Build order

0. **Observe the payload.** Register a probe that dumps raw payloads for the
   three events, then run one dialog that is answered, one answered with
   "Other", one multi-select, and one denied, and record each payload's shape
   in § Step 0 observations below. This settles § Open Questions 1 and 4, and 2 as far as the dialogs run reach,
   and D3's rules are adjusted to what is observed before any reader is
   written.
1. Recorder, wrapper and `settings.json` registration, with tests that feed
   recorded payloads to the recorder and assert the appended lines, and one that
   runs the wrapper with the recorder missing and asserts exit 0.
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
- **Ripples:** `.claude/settings.json`; `.claude/hooks/record-decision.sh`;
  `scripts/record_decision.py`, inside `lint` and `format` by location;
  `tests/scripts/test_claude_hooks.py` and CI's `HOOKS_PAT`, per the
  ripple-check row for a test whose subject is outside `src/`;
  `.claude/hooks/gate-commit.sh`, which stages the log;
  `sdd/traces/_schema.yml`; `scripts/check_traces.py` and its tests;
  `.claude/skills/pr/SKILL.md`, both Step 1 (commit the tail) and the
  rendering; `.github/PULL_REQUEST_TEMPLATE.md`, which `/pr` treats as the
  authoritative body shape, for the Decisions section;
  `.claude/skills/ship/SKILL.md` and
  `.claude/skills/orchestrate/SKILL.md`, whose tree-unchanged captures take
  D2's exclusion; `sdd/CLAUDE-REFERENCE.md` § Interview mode,
  whose wiring table gains a Record layer and whose tolerated-divergence note
  extends to the new matcher values; `sdd/AUTHORING.md` directory defaults, for
  `sdd/decisions/`; `GATE-INVENTORY.md`, regenerated.
- **Cost per dialog:** two short hook invocations and two appended lines (the
  `PreToolUse` one, then whichever of the two Post events fires); one of each
  for a denied dialog, which fired no Post event in step 0.

**Acceptance.** Step 0 observed and its payload shapes recorded in § Step 0
observations. Then, after the next three merged deliveries that ran dialogs: each
lists its logs in its trace, each PR body carries a Decisions section rendered
from them, and `check_traces.py` passes on all three. The ADR is written once
those three are read.

## Open Questions

Questions 1 and 4 are answered by step 0, and question 2 only for a denial:
dismissal and timeout are still open. The answers are summarised in § Step 0
observations and the text below is kept as asked.

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
- Who commits the log, after the second review: "Auto-stage + /pr tail
  (Recommended)", against "/pr commits only" and "Tail goes to the next PR".
- Review-round interference, after review: "Exempt sdd/decisions/
  (Recommended)", against gitignored staging, whose logs a reclaimed container
  would lose.
- Two dialogs did not settle what they asked. One received free-text answers
  ("Wait and let's further discuss", "Not yet"), `other` under D3; one was
  denied, `unanswered`. Both shaped the work, which is why D4 reports them
  rather than failing on them.

## Step 0 observations

Answers reach `PostToolUse` as `tool_response.answers`, one string per question
keyed by question text, with free text unmarked and multi-select joined by
`", "`. A denied dialog fires nothing after `PreToolUse`, and no
`PostToolUseFailure` was seen. The payload's `session_id` does not match the
`Claude-Session` trailer, but the hook process's `CLAUDE_CODE_REMOTE_SESSION_ID`
does.

Run 2026-10-03 in one Claude Code on the web session (`permission_mode`
`"auto"`). A probe, `tmp/probe_hook.py`, was registered in an uncommitted
`.claude/settings.local.json` with matcher `AskUserQuestion` on `PreToolUse`,
`PostToolUse` and `PostToolUseFailure`, and wrote each hook's stdin unchanged to
one file. Seven dialogs ran: a trivial fire check, the four kinds below, one
real decision (whether to run e and an environment dump), and a prefill probe
(e) added for Open Questions 2. Enumerating the probe directory gave 13
payloads: 7 `PreToolUse`, 6 `PostToolUse`, 0 `PostToolUseFailure`. Probe and
payloads were deleted afterwards. Fragments are quoted verbatim from the dumped files; long question
texts are elided with `…`.

**Common to every payload.** Top-level keys: `session_id`, `transcript_path`,
`cwd`, `scratchpad_dir`, `prompt_id`, `permission_mode`, `effort`,
`hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`; `PostToolUse` adds
`tool_response` and `duration_ms` (0 or 1 in every Post payload, so it does not
measure the wait for the user). `PreToolUse` and `PostToolUse` of one dialog
shared `tool_use_id` in every case, e.g. `"toolu_01DszzP88WbZW186LFgwMQtK"`
for dialog a. `PostToolUseFailure` never fired.

**a. Single-select, recommended option chosen.** Events: `PreToolUse`,
`PostToolUse`. Pre's `tool_input` holds `questions` only. Post carries the
answer twice, identically, in `tool_input.answers` and `tool_response.answers`:

```json
"answers": {"Dialog a (single-select, recommended): …": "Alpha (Recommended)"}
```

The value is the label string, `(Recommended)` suffix included.
`tool_response.questions` repeats the questions. D3: `followed`.

**b. Single-select, answered via "Other".** Events: `PreToolUse`,
`PostToolUse`. Same shape; the free text is the value, with no marker field:

```json
"answers": {"Dialog b (single-select, Other): …": "Other manual echo"}
```

D3: `other`, because the value matches neither `"Delta (Recommended)"` nor
`"Echo"`.

**c. multiSelect, two recommended, a different set chosen.** Events:
`PreToolUse`, `PostToolUse`. The set is one string, labels and free text joined
by `", "`; there is no list:

```json
"answers": {"Dialog c (multiSelect): …": "Golf (Recommended), India, Some more not mentioned yet"}
```

`"Golf (Recommended)"` and `"India"` are labels; `"Some more not mentioned yet"`
is free text entered through "Other". D3: `other`.

**d. Single-select, denied.** Events: `PreToolUse` only. The agent's tool
result was `Denied by user`; neither `PostToolUse` nor `PostToolUseFailure`
fired. D3: `unanswered`, from the lone `asked` event.

**e. Prefill probe.** The agent's call passed
`answers: {"Dialog e …": "Lima (Recommended)"}`, and the user was asked to pick
`"Mike"` if the dialog appeared. Pre's `tool_input` carried it verbatim:

```json
"answers": {"Dialog e (prefill probe): …": "Lima (Recommended)"}
```

The dialog was shown, and Post's `tool_input.answers` and `tool_response.answers`
both held `"Mike"`.

**Answers to the Open Questions.**

1. **Answers reach `PostToolUse`**, in both `tool_response.answers` and
   `tool_input.answers`, keyed by question text, one string per question. The
   result-text parser is not needed. `PreToolUse` carries none unless the agent
   supplied them (e).
2. **Answered for a denial only: it sends nothing after `PreToolUse`.**
   `PostToolUseFailure` did not fire for it. A dismissal distinct from a
   denial and a timeout were not observed, so whether either fires
   `PostToolUseFailure` is still open. In the normal flow nothing filled `answers` before
   the dialog, but the agent can (e), and the user's choice then overrides it.
3. Not in step 0's scope.
4. **No: `session_id` does not match the trailer.** It was
   `"8f551ca6-684d-5d72-b7c0-d6da1ce729ee"`, a UUID (version 5, no match by
   `uuid5` over the standard namespaces and the trailer's id forms), equal to
   the session's `CLAUDE_CODE_SESSION_ID` and to the `transcript_path` stem. The
   trailer was `https://claude.ai/code/session_01FPZRdRyQ4sj5AD4DZF1zg3`. The
   hook process's environment, dumped by the probe for e, held
   `"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_01FPZRdRyQ4sj5AD4DZF1zg3"`, whose
   suffix equals the trailer's. That correspondence is observed in one session
   and is not documented.

**What changed in the RFC, and why.**

- **D3 `prefilled`** now requires the final answer to equal the prefill. As
  first written, e would read `prefilled` although the user answered `"Mike"`,
  hiding the user's real choice.
- **D3 parsing rules** replace "rules step 0 fixes": where the answer is read,
  why Post's `tool_input` must not be used for prefill detection, how free text
  and the `", "`-joined multi-select string are parsed (a, b, c).
- **D4.0 trailer fallback** matches `CLAUDE_CODE_REMOTE_SESSION_ID` instead of
  `session_id`, and **D1** records that variable, because of question 4's
  answer. Kept rather than dropped, since the observed identifier does
  correspond.
- **Not changed:** the "Post events are exclusive" assumption and D3's `failed`
  row. Neither was contradicted: no `failed` event fired at all, so both stay
  untested; D4.2 now says so. Both still need an observation, a dismissal or
  timeout probe being the remaining candidate trigger, before step 1 builds
  the `failed` path and its tests. D3's `unanswered` row is confirmed by d.

## References

- Host item: BK-397 (`sdd/BACKLOG.md` § 6).
- [`research-code-abundance-goals-and-values.md`](../research/research-code-abundance-goals-and-values.md)
  § 2.3 (correction of 2026-10-03), § 6 proposal 8.
- [`research-decision-capture-at-dialog-time.md`](../research/research-decision-capture-at-dialog-time.md).
- [`CLAUDE.md` § Interview mode](../../CLAUDE.md#interview-mode);
  [`CLAUDE-REFERENCE.md` § Interview mode](../CLAUDE-REFERENCE.md#interview-mode-wiring).
- Claude Code hooks reference, `PreToolUse`, `PostToolUse` and
  `PostToolUseFailure` common input fields (code.claude.com/docs/en/hooks).
