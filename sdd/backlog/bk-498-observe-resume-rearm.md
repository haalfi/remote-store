# BK-498 — After `/clear`, a worker restart can resume the armed `/observe` session instead of the new one
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence (2026-10-28, OP-01)

From the session that hit it, as the maintainer relayed it, and from its
transcript events: remote session `session_01QqsRzJAiM44XJo3cR8oUEJ`, read with
`list_events` on 2026-10-28. The remote session is one throughout; the Claude
session ids inside it change.

1. **The restart resumed the pre-clear session, armed.** `/observe OP-01`
   ran as session `bcb85b21` (prompt at 07:19:00Z). At 09:40:23Z `/clear`
   started session `c1c866a2` (`SessionStart:clear`), which ran Bash and
   committed `23ae05a`; the ground hook never refused it. At 09:51:28Z a
   worker restart resumed `bcb85b21`, not `c1c866a2` (`SessionStart:resume`
   with session_id `bcb85b21`, the scratchpad path back to that id), while
   `c1c866a2`'s dialog was still open (point 2). Every later restart resumed
   `bcb85b21` too. From then on the ground hook refused Bash, Reads of
   `sdd/BACKLOG.md` and `sdd/traces/`, and the hook script itself.
2. **The open dialog was split across two logs.** The "OP-01 PR" dialog was
   asked before the restart and answered after it. Its `AskUserQuestion`
   call (event `d2678aa3-aa4c-485d-94b2-c364cc7fe0a7`, 09:44:49Z) carries
   session_id `c1c866a2-414d-4eae-9d81-31103cbe4b4f`, and its result (event
   `d305e347-5674-4ec9-81aa-fb43b95e61b2`, 09:51:31Z) carries `bcb85b21`.
   The recorder names the log by session_id, so the `asked` line went to
   `c1c866a2-….jsonl` and the `answered` line to `bcb85b21-….jsonl`, which
   matches the session-start banner showing the first file new and the
   second modified. No diff could confirm the files' contents: the armed
   session cannot run Bash, and the checkout this item was filed from never
   held them (there, `bcb85b21`'s log matches `23ae05a`).
3. **The session cannot get out by itself.** An armed session cannot commit,
   read its own hook or file this item. Only a new session can. Nor can
   another session help it: a message sent to it arrives as a notification,
   and `check` refuses `ReadNotifications`, which is not among its neutral
   tools (seen 2026-10-28 in the transcript).
4. **Its decision logs are lost.** Every log line the session writes after
   the re-arm stays in the armed session's container, because it cannot
   commit, and goes when that container is archived. Here that is both halves
   of the "OP-01 PR" dialog: `c1c866a2-….jsonl` with its `asked` line, and
   the `answered` line in that container's copy of `bcb85b21-….jsonl`. The
   decision survives only in the transcript events of point 2 and in the
   note above `decisions:` in `sdd/traces/bk-485-observe-op-01.yml`.

## What the code shows

- Both hooks key on the payload's `session_id`. The ground hook's marker is
  `tmp/observe/<session_id>.json` (`observe_ground.py` `_marker`), and the
  decision log is `sdd/decisions/<session_id>.jsonl` (`record_decision.py`
  `record`). So any event carrying `bcb85b21` lands in that session's marker
  and log. That explains point 2.
- The resumed session is the design session itself, and the hook arms it as
  designed. `rearm` (SessionStart, matcher `""`, so every source) re-arms "a
  resumed or compacted session that `arm` armed" from `transcript_path`:
  `_armed_args` takes the last `/observe` prompt before the transcript's first
  tool use, and `bcb85b21`'s opens with `/observe OP-01`. `disarm` removes the
  marker only on `reason: clear`. Either path arms the resumed session:
  `rearm` writes the marker, and a marker `disarm` never removed is still
  there. Which happened is not known: the transcript holds no SessionEnd hook
  event, so nothing shows `disarm` running at the `/clear`. That explains
  point 1.
- `check` passes the neutral tools, the `observe` Skill, WebSearch and
  WebFetch unless they name remote-store, Write and Edit of the record, and
  Read or Grep of the allowlist; it refuses Bash and every other tool. An
  armed session's refusals read "is outside the ground" or "not available in
  an /observe session (S2)", and neither names a way out (the `/clear` hint is
  only in a locked marker's message). That explains point 3. It also explains
  point 4: `record` writes the log into the project directory of whichever
  container runs the session, and only a commit from that session moves it
  into the repository.
- **Not shown by the code:** why the restart resumed `bcb85b21` rather than
  `c1c866a2`. That is the harness's doing, outside this repository, so no
  root cause is named here.

## Probed (2026-10-28)

- **The incident's events show no SessionEnd hook.** All of
  `session_01QqsRzJAiM44XJo3cR8oUEJ`'s events were read, 1,421 across 15 pages: none
  is a SessionEnd hook event. The clear is a `conversation_reset` event
  (`10ba6e13-ef44-47b6-9bc5-13ff1349260c`, trigger `clear`, still under
  `bcb85b21`) followed by the only `SessionStart:clear` burst, under `c1c866a2`.
- **`disarm` runs on `/clear` in a cloud session anyway.** A throwaway session
  (`session_01QqsRzNLhUdtNmR6K7yRRd6`) wrote its own marker; the maintainer typed
  `/clear` there (result event `2688f07c-297e-4670-97d4-ef55e72db4e6`,
  `local_command: clear`), and the new session's `ls -la tmp/observe` found the
  directory empty (result event `f991e3b1-77f4-408b-b23d-46ffdf766afc`). So the
  event stream does not show SessionEnd hooks, and in the incident `disarm` most
  likely removed the marker and the resume's `rearm` re-armed from the transcript.
  A user-level hook to capture the payloads was refused by auto mode as
  self-modification, so no payload was recorded.

## Resolution (2026-10-28)

The maintainer chose, in the dialog logged in
`sdd/decisions/f13251b9-0e40-5453-864a-3e334c0cc137.jsonl`: a release marker
that `disarm` writes on `/clear` and `rearm` honours; `/observe release` typed
by the maintainer as the way out, the record staying closed to a released
session; and logs committed by the released session itself, `record_decision.py`
unchanged. What the hook cannot reach is in `scripts/observe_ground.py`'s
docstring.

## Prescription (advisory)

The open decision is what a hook could tell such a resume by. The SessionStart
`source` cannot: it is `resume` for a wrongful resume and a rightful one alike.
Candidates, none verified: a tombstone `disarm` writes at `/clear` that
`rearm` honours, which needs SessionEnd to fire in a cloud session (the
transcript shows none); or the transcript naming a `/clear` after the
`/observe` prompt, if the CLI records it there. Whichever is chosen, a session
that is armed wrongly needs a way out that does not depend on the next
restart going right, and a way for its decision logs to reach the repository.
