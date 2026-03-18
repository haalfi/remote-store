# Preview — Build artifacts for consumer expectation testing

Build a wheel and docs site, then copy both to the `remote-store-expectations`
repo's `.preview/` directory for Mode B (pre-release consumer) validation.

## What this does

1. Build the wheel: `hatch build -t wheel`
2. Build the docs: `hatch run docs-build`
3. Copy both to `../remote-store-expectations/.preview/`
4. Print instructions for the expectations repo

## Steps

### 1. Build wheel

```bash
hatch build -t wheel
```

The wheel lands in `dist/`.

### 2. Build docs

```bash
hatch run docs-build
```

The docs site lands in `site/`.

### 3a. Clean previous preview

```bash
rm -rf ../remote-store-expectations/.preview
```

### 3b. Create directory structure

```bash
mkdir -p ../remote-store-expectations/.preview/dist
```

```bash
mkdir -p ../remote-store-expectations/.preview/docs
```

### 3c. Copy wheel

```bash
cp dist/remote_store-*.whl ../remote-store-expectations/.preview/dist/
```

### 3d. Copy docs

```bash
cp -r site/* ../remote-store-expectations/.preview/docs/
```

### 4. Report

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
- If `../remote-store-expectations/` does not exist, abort with a message
