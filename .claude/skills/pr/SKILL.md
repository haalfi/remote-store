---
name: pr
description: Create a pull request for the current branch
disable-model-invocation: true
argument-hint: "[base branch]"
---

Create a PR from the current branch. Base: `$ARGUMENTS` (default: `master`).
Repo: `haalfi/remote-store`.

For all GitHub API calls in this skill: use `github-pat` first (read+write), fall back to `MCP_DOCKER` for reads only.
When both servers expose the same tool name, always prefer `github-pat`.
See CLAUDE.md § GitHub operations for the full priority chain.

## Steps

1. **Pre-check:** Verify not on master, working tree clean, branch pushed to remote.
   Push with `-u` if needed.

   **Freshness check:** Run `git fetch origin master`, then
   `git rev-list --count origin/master ^HEAD`. If the count is non-zero, the
   branch is behind `origin/master`. Stop and ask the user whether to rebase
   (`git rebase origin/master` + force-push) before continuing. Do not rebase
   silently — a pushed branch requires `--force-with-lease`, which is
   destructive to anyone tracking the branch.

2a. **Testing gate:** Do the changed tests follow the rules in `sdd/TESTING.md`?
    Report violations before drafting the PR.

2b. **Docs gate:** Does changed documentation follow the rules in `sdd/CONTENT-RULES.md`?
    Report violations before drafting the PR.

2c. **Coverage gate:** Check `git diff origin/master...HEAD --name-only` for files under `src/`, `tests/`, or `examples/`.
    - If any match: run `hatch run test-cov` (requires 95%). If it fails, stop and report which files are below threshold. Do **not** create the PR until coverage passes.
    - If none match (docs/config-only): skip coverage.

3. **Gather context:** `git log origin/master..HEAD --oneline` and `git diff origin/master...HEAD`
   to understand all changes (not just the latest commit). Use `origin/master`,
   not local `master`, so context does not depend on a stale local ref.

4. **Draft PR:** Title (<70 chars) + body. Read `.github/PULL_REQUEST_TEMPLATE.md`
   and fill each section from gathered context: summary bullets from commits,
   check the appropriate Type of change box, link any related issues, fill the
   Checklist. The template is the authoritative body shape.

5. **Create PR** using `create_pull_request`:
   - `owner: "haalfi"`, `repo: "remote-store"`
   - `head:` current branch, `base:` master (or `$ARGUMENTS`)
   - `title:` and `body:` from step 4

6. **Report** the PR URL.

## Rules

- This skill only creates the PR. Do not merge or approve it.
- Do not push to master.
