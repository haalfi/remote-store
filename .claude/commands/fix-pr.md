# Fix PR — Address Review Comments

Read review comments from a PR, fix each issue in the local code, resolve the
threads on GitHub, then validate. Don't auto-push.

## MANDATORY: Bash command rules (read first)

These rules prevent built-in security prompts that CANNOT be bypassed via
settings. Violating them causes the user to approve every single command.

1. **NO `cd` prefix** — NEVER write `cd /path && git ...` or `cd /path && hatch ...`.
   The working directory is already correct. Just run `git status`, not
   `cd /path && git status`.
2. **NO `git -C`** — NEVER write `git -C /path ...`. Same reason: not in allow list.
3. **NO heredoc/command substitution in commits** — NEVER write
   `git commit -m "$(cat <<'EOF'...EOF)"`. Use a plain `-m` string instead.
   For multi-line messages, use multiple `-m` flags:
   `git commit -m "subject line" -m "body paragraph" -m "Co-Authored-By: ..."`
4. **NO piped git commands** — NEVER write `git show ... | grep` or
   `git diff ... | wc`. Use `Read`/`Grep`/`Glob` tools instead.
5. **Use dedicated tools** — `Read` (not `cat`/`git show`), `Grep` (not `grep`),
   `Glob` (not `find`).

## Arguments

PR number: `$ARGUMENTS` (ask if missing).

## Step 1: Fetch review comments

Ensure you are on the PR's head branch locally (check out if needed).

Fetch **both** comment types:

```bash
# Inline review threads (includes resolved status + thread IDs)
gh api graphql -f query='
  query($owner:String!, $repo:String!, $number:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$number) {
        reviewDecision
        url
        headRefName
        reviews(last: 100) { nodes { body author { login } } }
        reviewThreads(last: 100) {
          nodes {
            id
            isResolved
            isOutdated
            path
            line
            startLine
            diffSide
            comments(first: 10) {
              nodes { body author { login } originalLine line path }
            }
          }
        }
      }
    }
  }
' -f owner='{owner}' -f repo='{repo}' -F number=$PR_NUMBER
```

```bash
# General PR comments (not attached to code lines)
gh api repos/{owner}/{repo}/issues/$PR_NUMBER/comments
```

## Step 2: Triage

Build a work list from ALL unresolved comments:
- **Skip** resolved threads (`isResolved: true`)
- **Skip** outdated threads (`isOutdated: true`) — the code has already changed
- **Skip** bot comments and CI status messages
- For each actionable comment, note: file path, line, category tag
  (Bug/Spec/Test/Consistency/Ripple/Security), and what needs to change

If a comment is **unclear or debatable** (opinion-based, unclear intent, or you
disagree with the suggestion), add it to a "Skipped" list with the reason —
do not silently ignore it.

## Step 3: Fix

For each actionable comment:
1. Read the full file using the `Read` tool
2. Make the fix — match the category:
   - `Bug:` / `Spec:` — fix the code to match correct behavior / spec
   - `Test:` — add or improve test coverage
   - `Consistency:` — align with existing codebase patterns
   - `Ripple:` — update the referenced downstream files
   - `Security:` — fix the vulnerability
3. If the fix touches a spec-covered area, verify against `sdd/specs/`

## Step 4: Resolve threads

Batch-resolve all fixed threads in a single GraphQL mutation using aliases:

```bash
gh api graphql -f query='
  mutation {
    t0: resolveReviewThread(input:{threadId:"THREAD_ID_0"}) { thread { isResolved } }
    t1: resolveReviewThread(input:{threadId:"THREAD_ID_1"}) { thread { isResolved } }
  }
'
```

Only resolve threads you actually fixed. Never resolve skipped items.
If only one thread, use a single alias (`t0`).

## Step 5: Validate

```bash
hatch run lint
hatch run test
```

Fix any failures introduced by your changes. Re-run until clean.

## Step 6: Commit

Stage and commit. Use one commit per fix or one combined commit — whichever
makes the history clearer (prefer small focused commits when fixes are independent).

Follow the Bash rules from the top of this file. Examples:

```bash
git add file1.py file2.py
```

```bash
git commit -m "fix: address PR #N review -- short description" -m "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

After all commits, push once:

```bash
git push
```

Report:
- How many comments were fixed and resolved
- Any skipped comments with reasons

## Rules

- **Do not** merge, close, or approve the PR.
- **Do not** create new issues or leave reply comments.
- Fix what the reviewer asked for — don't refactor surrounding code.
- If a fix requires clarification, skip it and explain why.
