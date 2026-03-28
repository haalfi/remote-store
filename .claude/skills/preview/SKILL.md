---
name: preview
description: Build wheel and docs for consumer expectation testing
disable-model-invocation: true
---

Build wheel + docs, copy to `../remote-store-expectations/.preview/`.

## Steps

1. **Verify** `../remote-store-expectations/` exists. If missing, STOP — do not clone it.
2. **Build wheel:** `hatch build -t wheel` (lands in `dist/`)
3. **Build docs:** `hatch run docs-build` (lands in `site/`)
4. **Copy artifacts:**
   ```bash
   rm -rf ../remote-store-expectations/.preview
   mkdir -p ../remote-store-expectations/.preview/dist ../remote-store-expectations/.preview/docs
   cp dist/remote_store-*.whl ../remote-store-expectations/.preview/dist/
   cp -r site/* ../remote-store-expectations/.preview/docs/
   ```
5. **Report** the path and usage instructions (`pip install .preview/dist/...`, `python -m http.server -d .preview/docs 8080`)

## Rules

- Do NOT modify any files in remote-store. Do NOT commit, push, or create PRs.
