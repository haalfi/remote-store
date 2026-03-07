# Review PR — Inline Code Review

Post inline review comments on a GitHub PR. Find real issues only — no fluff.

## MANDATORY: Bash command rules (read first)

These rules prevent built-in security prompts that CANNOT be bypassed via
settings. Violating them causes the user to approve every single command.

1. **NO `cd` prefix** — NEVER write `cd /path && ...`. The working directory
   is already correct. Just run the command directly.
2. **NO `git -C`** — NEVER write `git -C /path ...`. Not in allow list.
3. **NO piped git commands** — NEVER write `git show ... | grep` or
   `git diff ... | wc`. Use `Read`/`Grep`/`Glob` tools instead.
4. **NO `git show master:file`** — `gh pr diff` already provides the base
   comparison. Use `Read` tool for current file contents. Do NOT compare
   against master via git commands.
5. **NO heredoc** — NEVER use `<<EOF` or `<<'EOF'` in Bash commands.
   Write JSON/text to a temp file with the `Write` tool, then reference it.
6. **Use dedicated tools** — `Read` (not `cat`/`git show`), `Grep` (not `grep`),
   `Glob` (not `find`).

## Arguments

PR number: `$ARGUMENTS` (ask if missing).

## Step 1: Gather context

```bash
gh pr view $PR_NUMBER --json title,body,baseRefName,headRefName,files
gh pr diff $PR_NUMBER
```

Read every changed file **in full** using the `Read` tool (not just diff hunks) —
you need surrounding context to spot contract changes, missing imports, and
pattern breaks.

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

Write the review JSON to a temp file, then submit via `gh api --input`:

```python
# 1. Use the Write tool to create the review payload in the WORKING DIRECTORY
#    (NOT /tmp/ — the Write tool's /tmp/ is virtual and invisible to shell tools):
#    Path: pr-review-$PR_NUMBER.json  (working directory)
#    Content: the JSON object below
```

```json
{
  "event": "COMMENT",
  "body": "Summary",
  "comments": [
    {"path": "src/remote_store/_store.py", "line": 42, "body": "Bug: ..."}
  ]
}
```

```bash
# 2. Post the review (single, non-compound command):
gh api repos/{owner}/{repo}/pulls/$PR_NUMBER/reviews --input pr-review-$PR_NUMBER.json
# 3. Clean up:
rm pr-review-$PR_NUMBER.json
```

**Critical rules:**
- **`"event": "COMMENT"`** always — never APPROVE/REQUEST_CHANGES (owner token)
- **`"line"` not `"position"`** — must be a line visible in the diff; if the
  finding is outside diff hunks, attach to nearest changed line and reference
  the actual location in the body
- **Deleted lines** need `"side": "LEFT"` with the base-branch line number
- **Tag each comment:** `Bug:` / `Spec:` / `Test:` / `Consistency:` / `Ripple:` / `Security:`
- Be terse — state problem and fix, no preamble
- **NEVER use heredoc (`<<EOF`)** with `gh api` — it triggers security prompts.
  Always write JSON to a file first with the `Write` tool.

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
