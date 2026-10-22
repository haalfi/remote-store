# `/rvw-pr` Step 4: posting with `gh`

Read only when no MCP posting tool loads (`SKILL.md` Step 4). It replaces
[`posting.md`](posting.md)'s three MCP calls; that file's verification still
applies.

**Post one review call, then one call per file-level finding:**

```bash
gh api --method POST repos/haalfi/remote-store/pulls/<N>/reviews --input - --jq '.id' <<'RVW_PR_JSON'
{"commit_id": "<Step 0's full 40-character head SHA>", "event": "COMMENT", "body": "<summary>",
 "comments": [{"path": "<path>", "line": <line>, "side": "RIGHT", "body": "<Category: body>"}]}
RVW_PR_JSON
gh api --method POST repos/haalfi/remote-store/pulls/<N>/comments --input - --jq '.id' <<'RVW_PR_JSON'
{"commit_id": "<same SHA>", "path": "<path>", "subject_type": "file", "body": "<Category: body>"}
RVW_PR_JSON
```

Each is its own Bash call. With no line findings, `comments` is `[]`.

- **JSON on stdin from a quoted heredoc, never `-f`/`-F` fields**: the quotes stop backticks and `$` in a body from running, `-F` rewrites `@file` and `{owner}`/`{repo}`/`{branch}`, and a `-f` `line` is a string (HTTP 422). Escape `"`, `\` and newlines (`\n`); no payload line may be the bare delimiter.
- **REST spells the MCP fields in snake case**: a range adds `start_line` and `start_side`, a deleted line takes `"side": "LEFT"` with the base line number.
- **`commit_id` is the full SHA, and `comments[]` takes no `subject_type`** (both HTTP 422), which is why a FILE finding takes the second call.
- **Retry each call at most once.** A refused call never ran: resend it with the refused words reworded (hooks refused git commands and, in a cloud session, `head`). A failed call may have landed after a timeout: retry only if its count did not rise, `gh api repos/haalfi/remote-store/pulls/<N>/reviews --jq length` for the review call, the comment count for a FILE call.
- **A worktree-isolated session refused the heredoc itself.**

`sdd/traces/bk-481-rvw-pr-gh-post.yml` records each HTTP 422 and refusal.

**A review call still failing after its retry posted nothing; make no FILE
call**: `SKILL.md` Step 4's not-posted header, every finding returned. **A FILE
call still failing, or a short count, is a partial post**: `## PR #N Review — X
of Y comments posted (partial: <what failed>)`, returning the failed calls'
findings. If every call reported
success, the count cannot say which are missing: return every finding marked
`compare with the PR before posting`.
