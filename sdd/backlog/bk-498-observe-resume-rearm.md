# BK-498 — A session resumed under an `/observe` session's id is re-armed and logs into that session's decisions
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence (2026-10-28, OP-01)

From the session that hit it, as the maintainer relayed it, with what the code
and this checkout show beside each point.

1. **The hook re-arms.** `/observe OP-01` ran as session `bcb85b21`. After
   `/clear`, a session (`c1c866a2`) ran Bash and committed `23ae05a`. A worker
   restart then resumed it under `bcb85b21` (its scratchpad path changed to
   that id). From then on the ground hook refused Bash, Reads of
   `sdd/BACKLOG.md` and `sdd/traces/`, and the hook script itself.
2. **The log went to the wrong file. Confirmed** by `git diff` in the
   checkout holding the lines: every line added to
   `sdd/decisions/bcb85b21-….jsonl` since `23ae05a` is one dialog asked after
   the restart, headed "OP-01 PR" and answered "Bookkeeping, /pr, one review
   (Recommended)". That dialog is `c1c866a2`'s. It is not visible in the
   checkout this item was filed from, where `bcb85b21`'s log matches
   `23ae05a`.
3. **The session cannot get out by itself.** An armed session cannot commit,
   read its own hook or file this item. Only a new session can.
4. **Its decision logs are stranded.** Every log the session writes after the
   re-arm stays in the armed session's container, because it cannot commit
   them, and goes when that container is archived. Here those were
   `c1c866a2-….jsonl` and the "OP-01 PR" lines in that container's copy of
   `bcb85b21-….jsonl`. The decision survives only in session
   `session_01QqsRzJAiM44XJo3cR8oUEJ`'s transcript and in the note in
   `sdd/traces/bk-485-observe-op-01.yml`.

## What the code shows

- Both hooks key on the payload's `session_id`. The ground hook's marker is
  `tmp/observe/<session_id>.json` (`observe_ground.py` `_marker`), and the
  decision log is `sdd/decisions/<session_id>.jsonl` (`record_decision.py`
  `record`). So any event carrying `bcb85b21` lands in that session's marker
  and log. That explains point 2.
- `rearm` (SessionStart, matcher `""`, so every source) arms from
  `transcript_path` alone: `_armed_args` takes the last `/observe` prompt
  before the transcript's first tool use. It does not read the payload's
  `source`, so it cannot tell a resumed design session from any other session
  that arrives with that transcript. `disarm` removed the marker at `/clear`
  (`reason: clear`), and `rearm` wrote it again on the restart. That explains
  point 1, if the restart's payload pointed at `bcb85b21`'s transcript. A
  post-`/clear` session that did not open with `/observe` has no such prompt
  before its first tool use, so the code implies that it did. The payload itself was not captured.
- `check` passes only the neutral tools and Read or Grep of the allowlist, and
  denies Bash outright. Its lock message offers `/clear` as the only way out.
  That explains point 3. It also explains point 4: `record` writes the log
  into the project directory of whichever container runs the session, and
  only a commit from that session moves it into the repository.
- **Not shown by the code:** why the restart resumed the post-`/clear`
  session under the earlier id. That is the harness's doing, outside this
  repository, so no root cause is named here.

## Prescription (advisory)

The open decision is what distinguishes the two cases. Candidate signals, none
of them verified: the SessionStart `source`, a transcript that names a
`/clear` after the `/observe` prompt, or a marker recording the transcript it
was armed from. Whichever is chosen, a session that is armed wrongly needs a way
out that does not depend on the next restart going right, and a way for its
decision logs to reach the repository.
