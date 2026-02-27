# Ripple Check — Cross-Reference Validator

You are performing a ripple check on the current working changes. This skill
verifies that all files affected by a change are consistent.

The canonical ripple-check table lives in `sdd/CLAUDE-REFERENCE.md`. If the
table below drifts from the reference, update this skill.

## Instructions

1. **Detect what changed.** Run `git diff --name-only HEAD` (unstaged + staged)
   and `git diff --cached --name-only` to identify modified files. If no changes
   are detected, ask the user what they changed or plan to change.

2. **Classify the change** using the table below. A single change may match
   multiple categories — check all that apply.

3. **For each matching category**, verify every item in the "Also check" column.
   Read the referenced files and confirm they are consistent with the change.
   Report any gaps found.

4. **Output a summary** with three sections:
   - **OK** — items verified as consistent
   - **Needs update** — items that are stale or missing (with specific details)
   - **Not applicable** — items that don't apply to this change

## Ripple-Check Table

| If you changed…               | Also check / update                                          |
|-------------------------------|--------------------------------------------------------------|
| **A backend** (`src/remote_store/backends/`) | README.md backends table, `pyproject.toml` extras, `guides/backends/` guide, `guides/backends/index.md` table, `mkdocs.yml` nav, `examples/configuration.py`, `sdd/specs/`, `CONTRIBUTING.md` repo structure, `src/remote_store/_registry.py` auto-registration |
| **An error type** (`src/remote_store/_errors.py`) | `sdd/specs/005-error-model.md`, all backends' `_errors()` context managers, tests for every backend, `src/remote_store/__init__.py` exports |
| **A capability** (`src/remote_store/_capabilities.py`) | `sdd/specs/003-backend-adapter-contract.md`, every backend's `capabilities()` property, Store surface API methods, conformance tests |
| **Version number**            | `pyproject.toml` version, `src/remote_store/__init__.py` `__version__`, `CITATION.cff` version + date-released, `CHANGELOG.md` new heading + `[Unreleased]` section |
| **A spec section** (`sdd/specs/`) | Tests with `@pytest.mark.spec("ID")` for that section, `sdd/BACKLOG.md` if related item exists |
| **A dependency**              | `pyproject.toml` extras + minimum pins (`>=X.Y`), README.md install instructions, `guides/backends/` prerequisites |
| **Store or Backend ABC** (`_store.py`, `_backend.py`) | All 6 backend implementations (Local, S3, S3-PyArrow, SFTP, Azure, Memory), conformance tests in `tests/backends/test_conformance.py` |
| **Public API** (`__init__.py` `__all__`) | README.md Store API table, `examples/` scripts, user guides |
| **Docs navigation** (`mkdocs.yml`) | Per-section `_nav.yml` files in `docs-src/`, `guides/backends/index.md` |

## Verification Commands

When checking consistency, use these to find references:
- Search for spec IDs: `grep -r "SPEC-ID" tests/`
- Find backend references: `grep -r "backend_name" src/ tests/ examples/ guides/`
- Check version strings: `grep -rn "0\.\d\.\d" pyproject.toml src/remote_store/__init__.py CITATION.cff`
- Find capability references: `grep -r "Capability\." src/ tests/`

## Important

- Do NOT silently skip items. Every cell in "Also check" must be explicitly
  verified or marked "not applicable" with a reason.
- If you find a gap, propose the specific fix (file, line, change needed).
- This check exists because sync failures have actually happened in this repo.
  Take it seriously.
