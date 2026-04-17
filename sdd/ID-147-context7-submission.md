# ID-147: Context7 Indexing Submission Guide

This document tracks the steps for submitting remote-store to Context7's curated library index.

## What is Context7?

Context7 is Upstash's curated library index for LLMs and AI code editors. It automatically extracts up-to-date code documentation, examples, and API surfaces from indexed repositories, making them discoverable to LLM-backed assistants.

## Current Status

- ✅ `context7.json` configuration file created at repository root
- ⏳ Awaiting submission to Context7 (out-of-band, requires manual action)

## Submission Steps

### Option 1: Web Form (Fastest)

1. Visit https://context7.com/add-library
2. Paste the repository URL: `https://github.com/haalfi/remote-store`
3. Submit

Processing typically takes 1–10 minutes depending on repository size.

### Option 2: GitHub PR (Fine-grained control)

1. Fork https://github.com/upstash/context7
2. Create a new branch: `git checkout -b add-remote-store`
3. Add remote-store to their library registry (format varies; check their `CONTRIBUTING.md`)
4. Include:
   - Repository: `https://github.com/haalfi/remote-store`
   - Documentation: `https://docs.remotestore.dev`
   - Configuration: reference `context7.json` in repo root
5. Open a PR against `upstash/context7`
6. Wait for maintainer approval and merge

## What Gets Indexed

Once approved, Context7 will surface:

- **docs-src/** — Full API reference and guides (RTD site)
- **examples/** — Runnable code snippets with module docstrings
- **remote_store/** — Library source code (method signatures, docstrings)
- **FEATURES.md** — Backend/capability matrix
- **README.md** — Project overview

## Configuration Details

The `context7.json` file controls indexing behavior:

```json
{
  "includes": ["docs-src/", "examples/", "remote_store/", "FEATURES.md", "README.md"],
  "exclude": {
    "folders": ["benchmarks/", "tests/", "sdd/", ".github/", ...],
    "files": ["pyproject.toml", "poetry.lock", ...]
  },
  "rules": [
    "Use Store.write() for uploads...",
    "All backends support the Store interface...",
    ...
  ]
}
```

The `rules` field provides LLMs with best-practices guidance when they query Context7.

## Timeline

- **Before next release:** Manual submission via web form or PR is required.
- **After indexing:** Update README.md to mention Context7 as a discovery option for LLM-backed assistants.
- **Ongoing:** Monitor Context7 for indexing updates as the library evolves.

## Related

- See `BACKLOG.md` (ID-147) for the original backlog item.
- See `FEATURES.md` for the backend/capability matrix.
- See docs.remotestore.dev for the full API reference.
