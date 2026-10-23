# `/rvw-pr` Step 4: posting the review

Two readers: a [`/rvw-pr`](SKILL.md) pass that posts, and `/ship`'s
orchestrator posting a panel round. An analyze-only member does not read this
file; the Comment rules stay in `SKILL.md` Step 4.

**With the MCP posting tools, use a pending review: three calls, in order.** The MCP server silently drops inline comments passed as `comments:` on a single `create`/`submit` call.

1. `pull_request_review_write`, `method: "create"`, **no `event`**: any `event` value submits at once.
2. `add_comment_to_pending_review` once per finding: `path`, `body`, and `subjectType: "LINE"` (with `line`, `side`, and `startLine`, `startSide` for a range) or `"FILE"`.
3. `pull_request_review_write`, `method: "submit_pending"`, `event: "COMMENT"`, the summary as body.

Without them, `SKILL.md` Step 4 sends you to [`posting-gh.md`](posting-gh.md) instead of these calls.

**Verify (only when you posted comments): the count must rise by the number posted.** Count before the first post call and after the last; an absolute count proves nothing on a PR carrying earlier rounds. If it is short, the submit dropped comments: retry once from step 1, since a submitted review takes no more, and if it is short again, report it in Step 5. A short count on the `gh` route follows `posting-gh.md` instead.

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
