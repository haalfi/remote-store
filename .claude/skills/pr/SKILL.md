---
name: pr
description: Create a pull request for the current branch
argument-hint: "[base branch]"
---

Create a PR from the current branch. Base: `$ARGUMENTS` (default: `master`).
Repo: `haalfi/remote-store`.

Throughout this skill, **`<BASE>`** is `$ARGUMENTS` if provided, else `master`.
Substitute it in every command and reference below.

For all GitHub API calls in this skill, use the configured GitHub MCP server.
Fall back to `gh` CLI for GraphQL-only flows like review-thread resolution.

## Steps

1. **Pre-check:** Verify not on master, working tree clean, branch pushed to
   remote. Push with `-u` if needed. Then run the [branch freshness
   check](../../../sdd/CLAUDE-REFERENCE.md#branch-freshness) with `<BASE>`.

2. **Validation gates:** Run the shared [PR validation
   gates](../../../sdd/CLAUDE-REFERENCE.md#pr-validation-gates) — `hatch run all`,
   local-machine reference, qualitative TESTING/CONTENT review. Resolve any stop
   condition before drafting the PR.

3. **Trace gate:** Extract backlog IDs from `git log origin/<BASE>..HEAD --format=%s`
   using the pattern `^([A-Z]+-\d+[a-z]?)[:\s]` against each subject — the ID
   is the leading `PREFIX-NNN` token, optionally followed by a single
   lowercase letter for split items (e.g. `BK-167a`, allowed by
   `sdd/traces/_schema.yml`), then `:` or whitespace (per [CLAUDE.md § Backlog](../../../CLAUDE.md#backlog),
   commit subjects start with the item ID). For each unique ID, look up a
   matching trace **case-insensitively** — `find sdd/traces -iname '<id>-*.yml'` —
   because existing trace filenames mix lowercase and uppercase prefixes.
   If any ID has no match, stop and ask the user — [CLAUDE.md § Trace
   authoring (mandatory)](../../../CLAUDE.md#trace-authoring) requires the trace to ship in the same PR as the
   work. Schema: `sdd/traces/_schema.yml`. No ID-prefixed commits? Skip the gate.

4. **Gather context:** `git log origin/<BASE>..HEAD --oneline` and `git diff origin/<BASE>...HEAD`
   to understand all changes (not just the latest commit). Use `origin/<BASE>`,
   not local `<BASE>`, so context does not depend on a stale local ref.

5. **Draft PR:** Title (<70 chars) + body. Read `.github/PULL_REQUEST_TEMPLATE.md`
   and fill each section from gathered context: summary bullets from commits,
   check the appropriate Type of change box, link any related issues, fill the
   Checklist. The template is the authoritative body shape.

6. **Create PR** using `create_pull_request`:
   - `owner: "haalfi"`, `repo: "remote-store"`
   - `head:` current branch, `base:` `<BASE>`
   - `title:` and `body:` from step 5

7. **Report** the PR URL.

## Rules

- This skill only creates the PR. Do not merge or approve it.
- Do not push to master.
