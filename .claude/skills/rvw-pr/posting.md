# `/rvw-pr` Step 4: posting the review

Two readers: a [`/rvw-pr`](SKILL.md) pass that posts, at its Step 4; and
`/ship`'s orchestrator when it posts a panel round. An analyze-only panel
member does not post and does not read this file; the Comment rules that bind
every pass stay in `SKILL.md` Step 4.

**Use the pending-review flow — three steps, in order.** The GitHub MCP server silently drops inline comments if you pass them as a `comments:` array on a single `submit`/`create` call. Always:

1. **Create a pending review.** `pull_request_review_write` with `method: "create"` and **no `event` parameter** — omitting `event` is what makes the review pending (the `event` enum is only `APPROVE` / `REQUEST_CHANGES` / `COMMENT`; passing any value here submits immediately). No review ID bookkeeping is needed — subsequent calls attach to the requester's latest pending review automatically.
2. **Attach each inline comment** with `add_comment_to_pending_review`, one call per finding. Required params: `path`, `body`, `subjectType: "LINE"` (or `"FILE"` for file-level). Optional: `line`, `side`, `startLine`, `startSide` for multi-line. Do not batch into a single review creation.
3. **Submit the review.** `pull_request_review_write` with `method: "submit_pending"`, `event: "COMMENT"`, and the summary body.

**Verify (only when you posted inline findings).** The check is a **delta**, not an absolute: capture the review-comment count **before** creating the pending review, and again after `submit_pending`. The count must rise by the number of comments you attached (at minimum, it must rise) — an absolute non-zero count proves nothing on a PR that already carries review comments from earlier rounds. If you had no inline findings to post (step 2 had nothing to attach), skip verification — an unchanged count is the correct outcome. If the count did not rise, the submit dropped your comments. Retry **once**: restart from step 1 (new `create` pending review, re-attach every comment, re-`submit_pending`) — after `submit_pending` there is no pending review to attach to, so calling `add_comment_to_pending_review` without a fresh `create` will fail. If the retry also fails the delta, stop and report the failure in the Step 5 summary (do not loop further).

**Take the count from exactly one instrument, and walk its pages explicitly:**

```bash
# Sum pages until one comes back short. per_page is the page size, not a ceiling.
gh api "repos/haalfi/remote-store/pulls/<N>/comments?per_page=100&page=1" --jq 'length'
gh api "repos/haalfi/remote-store/pulls/<N>/comments?per_page=100&page=2" --jq 'length'   # only if page 1 returned exactly 100
```

This REST read also runs in a cloud session (measured on PR #1162). Without
`gh`, skip it and say so in Step 5; no MCP read substitutes (table below).

**A page that returns exactly `per_page` means there is more, not that you are
done** — advance `page` until a short page (or `0`) comes back, and sum. That
loop is what makes this a count rather than a ceiling: `/ship` runs to eight
rounds and the closing gate is where a dropped finding costs most, so a
verification that switches itself off above 100 comments switches off exactly
when it is needed. Verified by walking one PR at `per_page=40`: `40 + 6 + 0`,
matching its true total.

This is the one count that does **not** follow Step 1's `gh`-content-first split
as a matter of convenience — the split is why a saturating spelling was
reachable at all, so the instrument is pinned here instead of chosen at the call
site.

Two spellings are **forbidden**, each for a structural reason rather than a
tuning one:

| Forbidden | Why |
|---|---|
| `gh api ".../comments" --jq 'length'` | No `per_page`, so it silently caps at the default page size and reads as "the comments did not post" |
| `pull_request_read` → `get_review_comments` → `totalCount` | Counts **threads**, not comments, so a comment delta compared against it compares two different quantities |

Both were caught by measuring one PR three ways and getting three different
answers — the capped count, the true count, and the thread count. The figures
are recorded with the item that found them; what belongs here is that neither
instrument is a comment count.

**Prefer the explicit `page=` walk above to `--paginate`**, which is why it is
written that way. Behind an agent proxy that refuses `gh`'s page-follow URLs —
measured here, and not a property of `--paginate` everywhere — it streams
partial results to stdout *and* exits non-zero, so a caller reading only stdout
gets a truncated count from a call that failed: the original failure mode at a
different threshold. Where it does work it is fine; the explicit walk is
portable across both, which is the reason to pin it. If you use `--paginate`
anyway, check its exit status before believing its output.

**The rule this encodes:** a verification step that can fail silently is worse
than no verification, because it is trusted. This one once read as a failed post
and caused a review to be re-posted twice — fifteen comments where five were
intended, plus a public claim that posting had failed when it had not.
