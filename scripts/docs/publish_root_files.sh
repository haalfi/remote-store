#!/usr/bin/env bash
# Publish root-level discovery files to the docs domain root (gh-pages root).
#
# mike (see .github/workflows/docs.yml) deploys docs-src/ content under
# versioned subdirectories only — e.g. docs.remotestore.dev/latest/context7.json —
# so files that must live at the *true* domain root are not reached by the
# normal build. Two need it:
#   - llms.txt    : the llmstxt.org standard resolves /llms.txt at a domain root.
#   - context7.json: a root copy makes the docs site discoverable to context7
#                    crawlers that hit the domain root (the versioned copy stays).
#
# Run this after `mike deploy ...` (which advances the local gh-pages ref); it
# commits the files onto gh-pages via a throwaway worktree and pushes. Idempotent:
# commits only when the content changed. ID-161.
set -euo pipefail

worktree="$(mktemp -d)/gh-pages"
git worktree add "$worktree" gh-pages
trap 'git worktree remove --force "$worktree"' EXIT

cp docs-src/llms.txt "$worktree/llms.txt"
cp docs-src/context7.json "$worktree/context7.json"

git -C "$worktree" add llms.txt context7.json
if git -C "$worktree" diff --cached --quiet; then
  echo "Root discovery files unchanged; nothing to commit."
else
  git -C "$worktree" commit -m "docs: publish root-level llms.txt and context7.json (ID-161)"
fi

git push origin gh-pages
