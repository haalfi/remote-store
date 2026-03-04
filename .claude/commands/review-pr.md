# Review PR — Inline Code Review

Post inline review comments on a GitHub PR. Find real issues only — no fluff.

## Arguments

PR number: `$ARGUMENTS` (ask if missing).

## Step 1: Gather context

```bash
gh pr view $PR_NUMBER --json title,body,baseRefName,headRefName,files
gh pr diff $PR_NUMBER
```

Read every changed file **in full** (not just diff hunks) — you need surrounding
context to spot contract changes, missing imports, and pattern breaks.

## Step 2: Analyze

Check the diff against these concerns (priority order):

1. **Correctness** — bugs, logic errors, wrong exceptions, missing boundary checks
2. **Spec compliance** — code vs `sdd/specs/`, missing `@pytest.mark.spec("ID")`
3. **Test coverage** — untested behavior, missing edge cases, untested branches
4. **Consistency** — breaks established codebase patterns
5. **Ripple gaps** — cross-refs not updated (see `sdd/CLAUDE-REFERENCE.md` table)
6. **Security** — injection, traversal, credential exposure

**Skip:** style (ruff handles it), docstrings on unchanged code, "consider X"
without reason, praise, logging suggestions.

## Step 3: Post review

Submit one review with all inline comments via `gh api --input -`:

```bash
gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/reviews --input - <<'EOF'
{
  "event": "COMMENT",
  "body": "Summary",
  "comments": [
    {"path": "src/remote_store/_store.py", "line": 42, "body": "Bug: ..."}
  ]
}
EOF
```

**Critical rules:**
- **`"event": "COMMENT"`** always — never APPROVE/REQUEST_CHANGES (owner token)
- **`"line"` not `"position"`** — must be a line visible in the diff; if the
  finding is outside diff hunks, attach to nearest changed line and reference
  the actual location in the body
- **Deleted lines** need `"side": "LEFT"` with the base-branch line number
- **Tag each comment:** `Bug:` / `Spec:` / `Test:` / `Consistency:` / `Ripple:` / `Security:`
- Be terse — state problem and fix, no preamble

## Step 4: Report

```
## PR #N Review — X comments posted
Bug: N | Spec: N | Test: N | Consistency: N | Ripple: N | Security: N
```

If no issues: `## PR #N Review — No issues found`

## Rules

- **Do not** approve, merge, close, or modify the PR.
- **Do not** create issues or leave comments outside the review.
- Large diffs: prioritize `src/` → tests → docs. State what you skipped.
- Only post what a senior engineer would flag. When uncertain, use `Possible:` prefix.
