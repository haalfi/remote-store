# Review PR — Automated Code Review with Inline Comments

You are reviewing a pull request and leaving review comments directly on GitHub.
Your job is to find real issues — bugs, missed edge cases, spec violations,
inconsistencies — and post them as inline comments. No fluff, no praise, no
"looks good" filler.

## Arguments

The user provides a PR number: `$ARGUMENTS`

If no PR number is provided, ask the user for one.

## Instructions

### Step 1: Gather PR context

Run these commands to understand the PR:

```bash
gh pr view $PR_NUMBER --json title,body,baseRefName,headRefName,files
gh pr diff $PR_NUMBER
```

Note the base branch, changed files, and PR description.

### Step 2: Read changed files in full

For each file in the diff, read the **full file** (not just the diff hunks).
You need surrounding context to spot issues like:
- Functions that callers depend on but whose contract changed
- Missing imports or exports
- Inconsistency with patterns elsewhere in the same file

### Step 3: Analyze against project standards

Check the diff against these project-specific concerns (in priority order):

1. **Correctness** — bugs, logic errors, off-by-one, wrong exception types,
   missing error handling at system boundaries
2. **Spec compliance** — does the code match its spec in `sdd/specs/`? Are
   `@pytest.mark.spec("ID")` markers present for new spec sections?
3. **Test coverage** — is new/changed behavior tested? Are edge cases covered?
   Are there untested branches?
4. **Consistency** — does the change follow patterns established elsewhere in
   the codebase? (naming, error handling, backend contract, path model)
5. **Cross-reference gaps** — use the ripple-check table from
   `sdd/CLAUDE-REFERENCE.md`. Did the PR update all downstream references?
   (README, CHANGELOG, BACKLOG, guides, examples, exports)
6. **Security** — command injection, path traversal, credential exposure

Skip these (they are noise, not value):
- Style preferences already enforced by ruff
- Missing docstrings or type annotations on unchanged code
- Suggestions to add logging or comments
- "Consider using X instead of Y" without a concrete reason
- Praise or positive remarks

### Step 4: Post review

Collect all findings and submit as a single review with inline comments.

**Use `gh api` with `--input -` and a JSON heredoc** (the `-f`/`-F` flag
approach breaks on `comments[]` array fields):

```bash
gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/reviews --input - <<'EOF'
{
  "event": "COMMENT",
  "body": "Review summary (if needed)",
  "comments": [
    {
      "path": "src/remote_store/_store.py",
      "line": 42,
      "body": "Bug: this raises `NotFound` but the spec (STORE-015) requires `PermissionError` when..."
    }
  ]
}
EOF
```

Rules for posting:
- **Event must be `COMMENT`** — never `APPROVE` or `REQUEST_CHANGES` (the
  token belongs to the repo owner; `APPROVE` fails with "Can not approve your
  own pull request").
- **Use `line` (not `position`)** — `line` is the line number in the file as
  shown in the diff's `+` side. `position` is deprecated/confusing.
- **Each comment must reference a specific line** — no general "file-level"
  comments unless absolutely necessary.
- **Comment body format**: Start with a category tag, then the issue.
  - `Bug:` — correctness issue
  - `Spec:` — deviation from specification
  - `Test:` — missing or inadequate test coverage
  - `Consistency:` — breaks established patterns
  - `Ripple:` — cross-reference not updated
  - `Security:` — security concern
- **Be terse.** State the problem and (if not obvious) the fix. No preamble.

### Step 5: Report

After posting, output a summary:

```
## PR #N Review Posted

| Category     | Count |
|--------------|-------|
| Bug          | N     |
| Spec         | N     |
| Test         | N     |
| Consistency  | N     |
| Ripple       | N     |
| Security     | N     |
| **Total**    | **N** |

Comments posted to: <PR URL>
```

If no issues were found, post nothing and report:

```
## PR #N Review — No Issues Found

No actionable findings. The diff looks correct.
```

## Important

- **Do not approve, merge, close, or modify the PR** — review only.
- **Do not create issues or leave comments outside the review.**
- If the diff is too large to analyze thoroughly, focus on `src/` changes first,
  then tests, then docs/config. State what you skipped.
- Comments must add value. If you would not flag it in a real code review
  between senior engineers, do not post it.
- When in doubt about whether something is a real issue, err on the side of
  posting it with a "Possible:" prefix rather than staying silent.
