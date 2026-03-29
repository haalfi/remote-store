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

2. **Coverage gate:** Check `git diff master...HEAD --name-only` for files under `src/`, `tests/`, or `examples/`.
   - If any match: run `hatch run test-cov` (requires 95%). If it fails, stop and report which files are below threshold. Do **not** create the PR until coverage passes.
   - If none match (docs/config-only): skip coverage.

3. **Gather context:** `git log master..HEAD --oneline` and `git diff master...HEAD`
   to understand all changes (not just the latest commit).

4. **Draft PR:** Title (<70 chars) + body. Body format:

   ```
   ## Summary
   <1-3 bullet points>

   ## Test plan
   - [ ] ...
   ```

5. **Create PR** using `create_pull_request`:
   - `owner: "haalfi"`, `repo: "remote-store"`
   - `head:` current branch, `base:` master (or `$ARGUMENTS`)
   - `title:` and `body:` from step 4

6. **Report** the PR URL.

## Rules

- This skill only creates the PR. Do not merge or approve it.
- Do not push to master.
