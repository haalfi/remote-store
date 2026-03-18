# Preview — Build artifacts for consumer expectation testing

Build a wheel and docs site, then copy both to the `remote-store-expectations`
repo's `.preview/` directory for Mode B (pre-release consumer) validation.

## What this does

1. Verify `../remote-store-expectations/` exists (abort if missing)
2. Build the wheel: `hatch build -t wheel`
3. Build the docs: `hatch run docs-build`
4. Copy both to `../remote-store-expectations/.preview/`
5. Print instructions for the expectations repo

## Steps

### 1. Verify expectations repo exists (MANDATORY — do this first)

```bash
test -d ../remote-store-expectations
```

If this fails, **STOP immediately**. Do NOT proceed with any further steps.
Do NOT clone or checkout the repo — that creates an undesired dependency.
Tell the user: `"../remote-store-expectations/ not found. The expectations repo must already be cloned as a sibling directory before running /preview."`

### 2. Build wheel

```bash
hatch build -t wheel
```

The wheel lands in `dist/`.

### 3. Build docs

```bash
hatch run docs-build
```

The docs site lands in `site/`.

### 4a. Clean previous preview

```bash
rm -rf ../remote-store-expectations/.preview
```

### 4b. Create directory structure

```bash
mkdir -p ../remote-store-expectations/.preview/dist
```

```bash
mkdir -p ../remote-store-expectations/.preview/docs
```

### 4c. Copy wheel

```bash
cp dist/remote_store-*.whl ../remote-store-expectations/.preview/dist/
```

### 4d. Copy docs

```bash
cp -r site/* ../remote-store-expectations/.preview/docs/
```

### 5. Report

Print the following to the user:

```
Preview artifacts copied to ../remote-store-expectations/.preview/

To use in the expectations repo:
  cd ../remote-store-expectations
  pip install .preview/dist/remote_store-*.whl
  python -m http.server -d .preview/docs 8080
  # Then run scenarios against http://localhost:8080/
```

## Notes

- The `.preview/` directory is gitignored in the expectations repo
- This skill does NOT modify any files in remote-store
- This skill does NOT commit, push, or create PRs
- If `../remote-store-expectations/` does not exist, STOP — do not clone it
