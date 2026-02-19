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
  adrs/                       # Architecture Decision Records (immutable)
  rfcs/                       # Proposals under discussion
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
5. Add user-facing docs in `docs/backends/<name>.md` and register in `mkdocs.yml` nav
6. Update `docs/backends/index.md` (Supported Backends table)
7. Update `README.md` (Supported Backends table + Installation extras)
8. Add backend config example to `examples/configuration.py`
9. If the backend needs an extra, add it to `pyproject.toml` `[project.optional-dependencies]`

## Adding an Extension

1. Write an RFC in `sdd/rfcs/`, get it accepted as a spec
2. Implement in `src/remote_store/ext/<name>.py`
3. Add tests in `tests/ext/test_<name>.py`
4. Use `unwrap()` for native backend access when needed

## Third-Party Extensions

External packages should:

- Use naming convention: `remote-store-<name>`
- Use `register_backend()` for backend registration
- Use `unwrap()` for native handle access
- Reuse the conformance test suite by importing and parameterizing it

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

### How to bump

Version is managed with [`bump-my-version`](https://github.com/callowayproject/bump-my-version). A single command bumps `pyproject.toml`, `src/remote_store/__init__.py`, and `CITATION.cff` atomically, commits, and tags:

```bash
bump-my-version bump patch   # 0.4.1 → 0.4.2
bump-my-version bump minor   # 0.4.1 → 0.5.0
bump-my-version bump major   # 0.4.1 → 1.0.0
```

After bumping, move the `[Unreleased]` section in `CHANGELOG.md` under a new `[X.Y.Z] - YYYY-MM-DD` heading and add a fresh `[Unreleased]` above it.

## Consistency Checklists

Documentation, examples, and metadata live in many places. Use these checklists to keep them in sync.

### New backend

- [ ] Spec in `sdd/specs/`
- [ ] Implementation in `src/remote_store/backends/_<name>.py`
- [ ] Conformance fixture in `tests/backends/conftest.py`
- [ ] User docs page `docs/backends/<name>.md`
- [ ] Added to `docs/backends/index.md` table
- [ ] Added to `mkdocs.yml` nav under Backends
- [ ] Added to README.md Supported Backends table
- [ ] Added to README.md Installation extras (if applicable)
- [ ] Added to `docs/getting-started.md` Installation extras (if applicable)
- [ ] Backend config example in `examples/configuration.py`
- [ ] Extra added to `pyproject.toml` `[project.optional-dependencies]` (if applicable)
- [ ] Spec index updated: `docs/design/specs/index.md` + `docs/design/index.md`
- [ ] CONTRIBUTING.md Repository Structure updated

### New Store method

- [ ] Added to `_store.py`
- [ ] Added to README.md Store API table
- [ ] Added to `docs/getting-started.md` Core Operations table
- [ ] Demonstrated in an `examples/` script (extend existing where possible)
- [ ] `docs/examples/index.md` description updated if example scope changed

### Release

- [ ] `bump-my-version bump patch|minor|major` (bumps `pyproject.toml`, `__init__.py`, `CITATION.cff`)
- [ ] CHANGELOG.md updated
- [ ] `hatch run all` passes (lint, typecheck, test-cov, examples)
- [ ] `mkdocs build --strict` passes
- [ ] Tagline consistent: `pyproject.toml` = README.md = `docs/index.md` = `mkdocs.yml` = `CITATION.cff`
- [ ] Keywords consistent: `pyproject.toml` = `CITATION.cff`
