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
```

- **JSON on stdin from a quoted heredoc, never `-f`/`-F` fields**: the quotes stop backticks and `$` in a body from running, `-F` rewrites `@file` and `{owner}`/`{repo}`/`{branch}`, and a `-f` `line` is a string (HTTP 422). Escape `"`, `\` and newlines (`\n`); no payload line may be the bare delimiter.
- **`commit_id` is the full SHA, and `comments[]` takes no `subject_type`** (both HTTP 422). A FILE finding goes to `pulls/<N>/comments` as `{"commit_id", "path", "subject_type": "file", "body"}`.
- **Recount before retrying a failed call.** A rejected call posts nothing (an HTTP 422 left no review), but one that timed out may have landed. If the count rose by the call's comments, it did: do not retry. Otherwise retry it once. Never re-run a call that succeeded; it would post its comments twice.
- **A worktree-isolated session refused this heredoc**, and a call whose body named git commands. A refusal is not retried: return the findings unposted.

The HTTP 422s and refusals were measured for BK-481 on PRs #1173 and #1174;
`sdd/traces/bk-481-rvw-pr-gh-post.yml` records each probe.

**A short count, or a FILE call that failed twice, is not retried.** Step 5's
header is `## PR #N Review — X of Y comments posted (partial: <what failed>)`.
Return the findings a failed call carried. If every call reported success, the
count cannot say which comments are missing, so return every finding marked
`compare with the PR before posting`.
