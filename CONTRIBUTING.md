# Contributing to Remote Store

Thank you for your interest in contributing! This project follows a **spec-first development model**: every feature starts as a specification before any code is written.

## Spec-First Workflow

1. **Propose a spec** — Open a PR adding a markdown file to `docs/specs/` (core), `docs/specs/backends/` (backend), or `docs/specs/extensions/` (extension). No code yet.
2. **Spec review** — Maintainers review for design fit, completeness, and consistency.
3. **Spec approval** — The spec is merged and becomes the contract.
4. **Implement** — Open a follow-up PR with tests (referencing spec IDs) and implementation.

## Spec Format

Each spec file uses section IDs with a module prefix:

```markdown
# <Module> Specification

## <PREFIX>-001: <Rule Title>
**Invariant:** <what must always be true>
**Preconditions:** <what the caller must ensure>
**Postconditions:** <what the callee guarantees>
**Raises:** <error conditions>
**Example:**
    <short code example>
```

Prefixes: `ERR` (errors), `PATH` (path), `MOD` (models), `CAP` (capabilities), `BE` (backend), `STORE` (store), `CFG` (config), `REG` (registry).

## Adding a New Backend

1. Write a spec in `docs/specs/backends/<name>.md`
2. Implement `Backend` ABC in `src/remote_store/backends/_<name>.py`
3. Add a conformance fixture in `tests/backends/conftest.py`
4. The entire conformance suite (`tests/backends/test_conformance.py`) runs automatically

## Adding an Extension

1. Write a spec in `docs/specs/extensions/<name>.md`
2. Implement in `src/remote_store/ext/<name>.py`
3. Add tests in `tests/ext/test_<name>.py`
4. Use `unwrap()` for native backend access when needed

## Third-Party Extensions

External packages should:

- Use naming convention: `remote-store-<name>`
- Use `register_backend()` for backend registration
- Use `unwrap()` for native handle access
- Reuse the conformance test suite by importing and parameterizing it

## Code Style

- **Formatter/linter:** ruff (line-length 120)
- **Type checking:** mypy strict mode
- **Tests:** pytest with `@pytest.mark.spec("ID")` markers for spec traceability
- **Coverage:** Target >= 95%

## Test Requirements

- Every spec section must have at least one test with `@pytest.mark.spec("ID")`
- Run `pytest -m spec` to verify all spec-derived tests pass
- Run `pytest --cov=remote_store` for coverage reports

## Versioning

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes. The public API surface is everything in `remote_store.__init__.__all__`.
