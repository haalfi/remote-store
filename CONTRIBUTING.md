# Contributing to Remote Store

Thank you for your interest in contributing! This project follows **Spec-Driven Development (SDD)**: every feature starts as a specification before any code is written. See [`sdd/000-process.md`](sdd/000-process.md) for the full methodology.

## Spec-First Workflow

1. **Propose** — Open a PR with an RFC in `sdd/rfcs/` (see [`rfc-template.md`](sdd/rfcs/rfc-template.md)). No code yet.
2. **Review** — Maintainers and community review for design fit and completeness.
3. **Accept** — The RFC graduates to a spec in `sdd/specs/`. It now defines the contract.
4. **Implement** — Open a follow-up PR with tests (referencing spec IDs) and implementation.

## Repository Structure

```
sdd/
  000-process.md              # How specs work in this repo
  specs/                      # Accepted specifications (source of truth)
    001-store-api.md
    002-registry-config.md
    003-backend-adapter-contract.md
    004-path-model.md
    005-error-model.md
    006-streaming-io.md
    007-atomic-writes.md
    008-s3-backend.md
    009-sftp-backend.md
    010-native-path-resolution.md
    011-s3-pyarrow-backend.md
    012-azure-backend.md
    013-memory-backend.md
    014-pyarrow-filesystem-adapter.md
    015-store-child.md
    016-ext-batch.md
    017-ext-transfer.md
    018-glob.md
  adrs/                       # Architecture Decision Records (9 ADRs)
  rfcs/                       # Proposals under discussion (3 RFCs)
```

## Spec Format

Each spec uses numbered section IDs with a module prefix:

```markdown
## <PREFIX>-NNN: <Rule Title>
**Invariant:** <what must always be true>
**Preconditions:** <what the caller must ensure>
**Postconditions:** <what the callee guarantees>
**Raises:** <error conditions>
**Example:**
    <short code example>
```

Prefixes: `STORE`, `MOD` (models), `CFG` (config), `REG` (registry), `BE` (backend), `CAP` (capabilities), `PATH`, `ERR`, `SIO` (streaming I/O), `AW` (atomic writes).

## Adding a New Backend

1. Write a spec in `sdd/specs/` or as an addendum in `sdd/specs/backends/<name>.md`
2. Implement `Backend` ABC in `src/remote_store/backends/_<name>.py`
3. Add a conformance fixture in `tests/backends/conftest.py`
4. The entire conformance suite (`tests/backends/test_conformance.py`) runs automatically
5. Add user-facing guide in `guides/backends/<name>.md` and register in `mkdocs.yml` nav
6. Update `guides/backends/index.md` (Supported Backends table)
7. Update `README.md` (Supported Backends table + Installation extras)
8. Add backend config example to `examples/configuration.py`
9. If the backend needs an extra, add it to `pyproject.toml` `[project.optional-dependencies]`

## Adding an Extension

Extensions live in `src/remote_store/ext/` and follow the contract in [ADR-0008](sdd/adrs/0008-extension-architecture.md). Full checklist:

1. Write an RFC in `sdd/rfcs/`, get it accepted as a spec in `sdd/specs/`
2. Implement in `src/remote_store/ext/<name>.py` — define `__all__`
3. Use only the public `Store` / `Backend` API (never `_backend`). Use `unwrap()` for native access
4. Do not own Store lifecycle — never call `store.close()` or use `with store:`
5. Let `CapabilityNotSupported` propagate — do not catch and suppress it
6. Add tests in `tests/test_<name>.py` with `@pytest.mark.spec("ID")`
7. Write a user guide in `guides/<name>.md`
8. Add an `include-markdown` wrapper in `docs-src/<name>.md`
9. Add the page to `docs-src/_nav.yml`
10. Add a runnable example in `examples/`
11. Update `CHANGELOG.md` and `sdd/BACKLOG.md` in the same commit

### Export patterns

**Pure Python (no extra dependencies)** — export unconditionally from `remote_store.__init__`:

```python
# In remote_store/__init__.py:
from remote_store.ext.<name> import Foo, bar
```

**Optional dependency** — two guards are needed:

1. In the extension module, raise a helpful error if the dependency is missing:

```python
# In ext/<name>.py:
try:
    import some_lib
except ModuleNotFoundError as _exc:
    raise ModuleNotFoundError(
        "some_lib is required for the <name> extension. "
        "Install it with: pip install 'remote-store[<name>]'"
    ) from _exc
```

2. In `remote_store/__init__.py`, conditionally re-export with a silent guard:

```python
try:
    from remote_store.ext.<name> import Foo, bar
    __all__ += ["Foo", "bar"]
except ImportError:
    pass
```

Add the optional dependency as an extra in `pyproject.toml [project.optional-dependencies]`.

## Third-Party Extensions

External packages should use the naming convention `remote-store-<name>` and:

- Use only the public `Store` / `Backend` API
- Use `register_backend()` for backend registration (if applicable)
- Use `unwrap()` for native handle access
- For backend extensions: reuse the conformance test suite by importing and parameterizing it

## Development Setup

```bash
# Clone and enter the repo
git clone https://github.com/haalfi/remote-store.git
cd remote-store

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Verify everything works
hatch run all    # or run individual steps:
hatch run lint
hatch run typecheck
hatch run test-cov
hatch run examples
```

All dev scripts are defined in `pyproject.toml` under `[tool.hatch.envs.default.scripts]`. Run `hatch run` to see available commands.

## Code Style

See [`sdd/DESIGN.md` Section 11](sdd/DESIGN.md#11-code-style) for the full code style conventions.

- **Formatter/linter:** ruff (line-length 120)
- **Type checking:** mypy strict mode
- **Tests:** pytest with `@pytest.mark.spec("ID")` markers for spec traceability
- **Coverage:** Target >= 95%

## Test Requirements

- Every spec section must have at least one test with `@pytest.mark.spec("ID")`
- Run `pytest -m spec` to verify all spec-derived tests pass
- Run `pytest --cov=remote_store` for coverage reports

## Examples and Notebooks

The `examples/` directory contains runnable Python scripts that are validated in CI. Example scripts must remain self-contained and use `tempfile.TemporaryDirectory` for cleanup.

Jupyter notebooks in `examples/notebooks/` are for interactive exploration and are **not** run in CI. They require manual testing when the API changes. This is intentional: notebooks depend on visual output and interactive workflows that don't translate well to automated checks.

## Versioning

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes. The public API surface is everything in `remote_store.__init__.__all__`.

### When to bump

| Change type | Bump | Examples |
|-------------|------|----------|
| New public API, feature, or backend | **minor** (`0.X.0`) | `Store.to_key()`, new backend, new config loader |
| Bug fix, internal refactor | **patch** (`0.0.X`) | Fix round-trip bug, update retry logic |
| Breaking API change (pre-1.0) | **minor** (`0.X.0`) | Remove method, rename parameter |
| Breaking API change (post-1.0) | **major** (`X.0.0`) | — |
| CI, docs, metadata-only | **no bump** | Add classifier, update README |

### Stability tiers

| Label | Meaning |
|-------|---------|
| **Alpha** (pre-0.11) | API may change freely between releases |
| **Beta** (0.11+) | Core API (`Store`, `Registry`, `Backend`, models, errors) is stable. Breaking changes are documented in CHANGELOG and avoid gratuitous churn. Extensions (`ext.*`) may evolve more freely. |
| **Stable** (1.0+) | Full SemVer: breaking changes require a major bump |

### How to bump

Version is managed with [`bump-my-version`](https://github.com/callowayproject/bump-my-version). It modifies `pyproject.toml`, `src/remote_store/__init__.py`, and `CITATION.cff` in-place without committing or tagging (configured in `pyproject.toml`). The release checklist below handles the commit and tag lifecycle.

Quick reference for the command syntax:

```bash
bump-my-version bump patch   # 0.4.1 → 0.4.2
bump-my-version bump minor   # 0.4.1 → 0.5.0
bump-my-version bump major   # 0.4.1 → 1.0.0
```

## Consistency Checklists

Documentation, examples, and metadata live in many places. Use these checklists to keep them in sync.

### New backend

- [ ] Spec in `sdd/specs/`
- [ ] Implementation in `src/remote_store/backends/_<name>.py`
- [ ] Conformance fixture in `tests/backends/conftest.py`
- [ ] User guide in `guides/backends/<name>.md`
- [ ] Added to `guides/backends/index.md` table
- [ ] Added to `mkdocs.yml` nav under Backends
- [ ] Added to README.md Supported Backends table
- [ ] Added to README.md Installation extras (if applicable)
- [ ] Backend config example in `examples/configuration.py`
- [ ] Extra added to `pyproject.toml` `[project.optional-dependencies]` (if applicable)
- [ ] CONTRIBUTING.md Repository Structure updated

### New Store method

- [ ] Added to `_store.py`
- [ ] Added to README.md Store API table
- [ ] Demonstrated in an `examples/` script (extend existing where possible)

### Release

#### Phase 0: Pre-flight

- [ ] Master is clean: `git status` shows no uncommitted changes
- [ ] CI is green on master (lint, typecheck, test 3.10-3.14, examples, docs, package)
- [ ] No open `[~]` items shipping in this release in `sdd/BACKLOG.md` — complete (`[x]`) or defer (`[ ]`)
- [ ] `[Unreleased]` section in CHANGELOG.md is non-empty
- [ ] Decide bump level (patch / minor / major) per the table above

#### Phase 1: Content freeze

- [ ] CHANGELOG.md `[Unreleased]` is complete — every user-facing change listed with its backlog ID
- [ ] `sdd/BACKLOG.md`: all shipping items marked `[x]` with version (e.g. `(v0.8.0)`)
- [ ] README.md: backends table, installation extras, API table, badges are current
- [ ] Specs vs code: spot-check shipped features match their specs (`pytest -m spec` as proxy)
- [ ] Examples: `hatch run examples` passes; manually review notebooks if API surface changed
- [ ] Guides: new/changed backend guides are accurate
- [ ] DEVELOPMENT_STORY.md: add a section for this release (pre-1.0 only)

#### Phase 2: Version bump (on a release branch)

- [ ] Create release branch: `git checkout -b release-vX.Y.Z`
- [ ] CHANGELOG.md: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add fresh empty `[Unreleased]` above
- [ ] Update `date-released` in `CITATION.cff` to today (bump-my-version only updates `version:`, not this field)
- [ ] Tagline consistent: `pyproject.toml` = README.md = `docs-src/index.md` = `mkdocs.yml` = `CITATION.cff`
- [ ] Keywords consistent: `pyproject.toml` = `CITATION.cff`
- [ ] Conda recipe: update `context.version` in `packaging/conda-forge/recipe.yaml` to X.Y.Z
- [ ] `bump-my-version bump patch|minor|major` (modifies version in `pyproject.toml`, `__init__.py`, `CITATION.cff`)
- [ ] Review and commit: `git diff` to verify, then `git add pyproject.toml src/remote_store/__init__.py CITATION.cff CHANGELOG.md packaging/conda-forge/recipe.yaml && git commit -m "Release vX.Y.Z"`

#### Phase 3: Validate

- [ ] `hatch run all` passes (lint + format-check + typecheck + test-cov + examples)
- [ ] `mkdocs build --strict` passes
- [ ] `python -m build && twine check dist/*` — package builds cleanly
- [ ] `pip install dist/*.whl && python -c "import remote_store; print(remote_store.__version__)"` — version matches
- [ ] Conda recipe: version in `packaging/conda-forge/recipe.yaml` matches release version

#### Phase 4: Ship

- [ ] Push branch, open PR, wait for CI green
- [ ] Request PR review — wait for approval before merging
- [ ] Merge PR to master
- [ ] Wait for CI to pass on the merge commit (multi-platform source of truth)
- [ ] Verify HEAD is the merge commit: `git log --oneline -1`
- [ ] Tag the merge commit: `git tag vX.Y.Z` (or `git tag vX.Y.Z <sha>` if master advanced)
- [ ] Push the tag: `git push origin vX.Y.Z`
- [ ] Create GitHub Release from the tag — this triggers both `publish.yml` (PyPI) and versioned docs deploy
- [ ] Watch `publish.yml` — confirm it completes successfully
- [ ] Delete the release branch: `git push origin --delete release-vX.Y.Z`

#### Phase 5: Post-release verification

- [ ] PyPI: `pip install remote-store==X.Y.Z` in a fresh venv, verify version and README renders on pypi.org
- [ ] GitHub Pages: check version switcher shows new version as "latest"
- [ ] ReadTheDocs: check https://remote-store.readthedocs.io/ shows correct version (requires RTD automation rule for tag-based builds)
- [ ] Conda recipe: fetch sha256 from PyPI (`curl -s https://pypi.org/pypi/remote-store/X.Y.Z/json | python -c "import sys,json; d=json.load(sys.stdin); print([f['digests']['sha256'] for f in d['urls'] if f['filename'].endswith('.tar.gz')][0])"`) and update `source.sha256` in `packaging/conda-forge/recipe.yaml`
- [ ] Commit recipe update to master: `git add packaging/conda-forge/recipe.yaml && git commit -m "Update conda recipe for vX.Y.Z"`
- [ ] Conda-forge: if feedstock exists, verify bot opened a version-bump PR
- [ ] Announce if applicable (tracking issues, users)
