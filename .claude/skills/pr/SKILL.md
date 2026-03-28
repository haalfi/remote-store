---
name: pr
description: Create a pull request for the current branch
disable-model-invocation: true
argument-hint: "[base branch]"
---

Create a PR from the current branch. Base: `$ARGUMENTS` (default: `master`).
Repo: `haalfi/remote-store`.

For all GitHub API calls in this skill, use `github-pat` if available, otherwise fall back to `MCP_DOCKER`.
See CLAUDE.md § GitHub operations for details.

## Steps

1. **Pre-check:** Verify not on master, working tree clean, branch pushed to remote.
   Push with `-u` if needed.

2. **Gather context:** `git log master..HEAD --oneline` and `git diff master...HEAD`
   to understand all changes (not just the latest commit).

3. **Draft PR:** Title (<70 chars) + body. Body format:

   ```
   ## Summary
   <1-3 bullet points>

   ## Test plan
   - [ ] ...
   ```

4. **Create PR** using `create_pull_request`:
   - `owner: "haalfi"`, `repo: "remote-store"`
   - `head:` current branch, `base:` master (or `$ARGUMENTS`)
   - `title:` and `body:` from step 3

5. **Report** the PR URL.

## Rules

- This skill only creates the PR. Do not merge or approve it.
- Do not push to master.
