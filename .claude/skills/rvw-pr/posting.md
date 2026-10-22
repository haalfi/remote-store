# `/rvw-pr` Step 4: posting the review

Two readers: a [`/rvw-pr`](SKILL.md) pass that posts, and `/ship`'s
orchestrator posting a panel round. An analyze-only member does not read this
file; the Comment rules stay in `SKILL.md` Step 4.

**With the MCP posting tools, use a pending review: three calls, in order.** The MCP server silently drops inline comments passed as `comments:` on a single `create`/`submit` call.

1. `pull_request_review_write`, `method: "create"`, **no `event`**: any `event` value submits at once.
2. `add_comment_to_pending_review` once per finding: `path`, `body`, and `subjectType: "LINE"` (with `line`, `side`, and `startLine`, `startSide` for a range) or `"FILE"`.
3. `pull_request_review_write`, `method: "submit_pending"`, `event: "COMMENT"`, the summary as body.

**Without them, post with `gh`: one review call, then one call per file-level finding.** `SKILL.md` Step 4 says when this applies:

```bash
gh api --method POST repos/haalfi/remote-store/pulls/<N>/reviews --input - --jq '.id' <<'RVW_PR_JSON'
{"commit_id": "<Step 0's full 40-character head SHA>", "event": "COMMENT", "body": "<summary>",
 "comments": [{"path": "<path>", "line": <line>, "side": "RIGHT", "body": "<Category: body>"}]}
RVW_PR_JSON
```

- **JSON on stdin from a quoted heredoc, never `-f`/`-F` fields**: the quotes stop backticks and `$` in a body from running, `-F` rewrites `@file` and `{owner}`/`{repo}`/`{branch}`, and a `-f` `line` is a string (HTTP 422). Escape `"`, `\` and newlines (`\n`); no payload line may be the bare delimiter.
- **`commit_id` is the full SHA, and `comments[]` takes no `subject_type`** (both HTTP 422). A FILE finding goes to `pulls/<N>/comments` as `{"commit_id", "path", "subject_type": "file", "body"}`.
- **A failed call posts nothing: retry it once.** Never re-run a call that succeeded; it would post its comments twice.
- **A worktree-isolated session refused this heredoc**, and a call whose body named git commands. A refusal is not retried: return the findings unposted.

The HTTP 422s and refusals were measured for BK-481 on PRs #1173 and #1174;
`sdd/traces/bk-481-rvw-pr-gh-post.yml` records each probe.

**Verify (only when you posted comments): the count must rise by the number posted.** Count before the first post call and after the last; an absolute count proves nothing on a PR carrying earlier rounds.

- **MCP short:** the submit dropped comments. Retry once from step 1, since a submitted review takes no more; if it is short again, report it in Step 5.
- **`gh` short, or a FILE call failed twice:** not retried. Step 5's header is `## PR #N Review — X of Y comments posted (partial: <what failed>)`. Return the findings a failed call carried. If every call reported success, the count cannot say which comments are missing, so return every finding marked `compare with the PR before posting`.

**Take the count from exactly one instrument, walking its pages:**

```bash
gh api "repos/haalfi/remote-store/pulls/<N>/comments?per_page=100&page=1" --jq 'length'
# page=2, 3, ... while the last page returned exactly 100; sum them
```

It runs in a cloud session too (measured on PR #1162). Without `gh`, skip
verification and say so in Step 5; no MCP read substitutes:

| Forbidden | Why |
|---|---|
| `gh api ".../comments" --jq 'length'` | No `per_page`: caps at the default page size, so a long PR reads as a failed post |
| `pull_request_read` → `get_review_comments` → `totalCount` | Counts threads, not comments |

Prefer the explicit walk to `--paginate`: behind an agent proxy that refuses its
page-follow URLs (measured here) it prints a partial count and exits non-zero.
If you use it, check the exit status.

**Why the instrument is pinned:** a verification that fails silently is trusted.
A miscount once read as a failed post, and the review was re-posted twice:
fifteen comments where five were intended.
