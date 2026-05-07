---
name: pr
description: Create a pull request for the current branch
disable-model-invocation: true
argument-hint: "[base branch]"
---

Create a PR from the current branch. Base: `$ARGUMENTS` (default: `master`).
Repo: `haalfi/remote-store`.

Throughout this skill, **`<BASE>`** is `$ARGUMENTS` if provided, else `master`.
Substitute it in every command and reference below.

For all GitHub API calls in this skill, use the configured GitHub MCP server.
Fall back to `gh` CLI for GraphQL-only flows like review-thread resolution.

## Steps

1. **Pre-check:** Verify not on master, working tree clean, branch pushed to remote.
   Push with `-u` if needed.

   **Freshness check:** Run `git fetch origin <BASE>`, then
   `git rev-list --count origin/<BASE> ^HEAD`. If the count is non-zero, the
   branch is behind `origin/<BASE>`. Stop and ask the user whether to rebase.
   If approved: `git rebase origin/<BASE>` then immediately
   `git push --force-with-lease origin <current-branch>`, so subsequent steps
   see the rebased commits on the remote. Do not rebase silently —
   `--force-with-lease` is destructive to anyone tracking the branch.

2a. **Testing gate:** Do the changed tests follow the rules in `sdd/TESTING.md`?
    Report violations before drafting the PR.

2b. **Docs gate:** Does changed documentation follow the rules in `sdd/CONTENT-RULES.md`?
    Report violations before drafting the PR.

2c. **Coverage gate:** Check `git diff origin/<BASE>...HEAD --name-only` for files under `src/`, `tests/`, or `examples/`.
    - If any match: run `hatch run test-cov` (requires 95%). If it fails, stop and report which files are below threshold. Do **not** create the PR until coverage passes.
    - If none match (docs/config-only): skip coverage.

3. **Gather context:** `git log origin/<BASE>..HEAD --oneline` and `git diff origin/<BASE>...HEAD`
   to understand all changes (not just the latest commit). Use `origin/<BASE>`,
   not local `<BASE>`, so context does not depend on a stale local ref.

4. **Draft PR:** Title (<70 chars) + body. Read `.github/PULL_REQUEST_TEMPLATE.md`
   and fill each section from gathered context: summary bullets from commits,
   check the appropriate Type of change box, link any related issues, fill the
   Checklist. The template is the authoritative body shape.

5. **Create PR** using `create_pull_request`:
   - `owner: "haalfi"`, `repo: "remote-store"`
   - `head:` current branch, `base:` `<BASE>`
   - `title:` and `body:` from step 4

6. **Report** the PR URL.

## Rules

- This skill only creates the PR. Do not merge or approve it.
- Do not push to master.
