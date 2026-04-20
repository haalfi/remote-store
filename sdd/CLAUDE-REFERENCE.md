# Claude Code Reference

Lookup tables and detailed procedures for Claude Code sessions.
Scope: cross-file dependency checks, repo navigation, and layout.

---

## Ripple-check table

Before committing, check whether your change has cross-file dependencies:

| If you changed…            | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **A backend**              | README backends table, `pyproject.toml` extras,           |
|                            | `guides/backends/`, docs nav, `examples/`,                |
|                            | `sdd/specs/`, `CONTRIBUTING.md` repo structure,           |
|                            | `src/remote_store/_registry.py` auto-registration         |
| **An error type**          | `sdd/specs/005-error-model.md`, all backends' error       |
|                            | mapping, tests for every backend,                         |
|                            | error docstring "raised by" list, troubleshooting guide   |
| **A capability**           | `sdd/specs/003-backend-adapter-contract.md`,              |
|                            | every backend's `capabilities()`, Store surface API,      |
|                            | capabilities matrix page                                  |
| **Version number**         | `pyproject.toml`, `src/remote_store/__init__.py`,         |
|                            | `CITATION.cff` (version + date-released),                 |
|                            | `CHANGELOG.md` (new heading + `[Unreleased]` section),    |
|                            | `packaging/conda-forge/recipe.yaml` (version + sha256)    |
| **A spec section**         | Tests with `@pytest.mark.spec("ID")`, BACKLOG if related  |
| **A dependency**           | `pyproject.toml` extras + minimum pins, README install    |
|                            | instructions, docs prerequisites                          |
| **Store or Backend ABC**   | All backend implementations, conformance tests            |
| **A public method signature** | Docstring (Args, Returns, Raises), examples that       |
|                            | call it, guides that reference it                         |
| **A Store method**         | README Store API table + comparison method count,         |
|                            | `__init__.py` `__all__`, README examples table (if new    |
|                            | example added), `examples/`, spec in `sdd/specs/`,        |
|                            | guides, CHANGELOG                                         |
| **Public API** (`__all__`) | README Store API table, `docs-src/api/*.md` directive     |
|                            | (every `__all__` symbol needs a `:::` entry),             |
|                            | `docs-src/api/index.md` summary table (every public       |
|                            | class/function needs a row), `docs-src/api/_nav.yml`,     |
|                            | `examples/`, user guides.                                 |
|                            | **Check**: `backends/__init__.py` `__all__` too —         |
|                            | secondary public API (e.g. `SFTPUtils`) needs its own     |
|                            | `api/*.md` page and index entry                           |
| **An extension**           | `__init__.py` exports (pure-Python only; optional-dep     |
|                            | extensions are NOT re-exported — ADR-0013),               |
|                            | `pyproject.toml` extras (if optional dep),                |
|                            | README extensions table, `docs-src/api/extensions/*.md` +  |
|                            | `api/extensions/index.md` + `api/extensions/_nav.yml`,    |
|                            | `guides/`,               |
|                            | `docs-src/` + `_nav.yml`, `examples/`,                    |
|                            | CHANGELOG, BACKLOG                                        |
| **An example script**      | README examples table, `docs-src/examples/*.md` wrapper,  |
|                            | `tests/test_examples.py` import                           |
| **Docs navigation**        | Per-section `_nav.yml` files in `docs-src/`,              |
|                            | `guides/backends/index.md`,                               |
|                            | `sdd/DOCUMENTATION.md` § Content homes                    |
| **An API reference page**  | `sdd/DOCUMENTATION.md` § 8 — page-type templates          |
| (new or restructured)      | and building blocks for required sections                 |
| **A bug fix**              | `sdd/BACKLOG.md` (item), `CHANGELOG.md` (stub line under  |
|                            | `[Unreleased]`), failing test **before** the fix, spec if |
|                            | the bug contradicts a spec invariant                      |
| **Source/test/spec counts**| README badge + CI coverage report (no manual table)       |
| **A new test file**        | Ask: does it exercise OS-specific code (path separators,  |
|                            | `os.replace`, `tempfile`, local filesystem, atomic writes)?|
|                            | If yes → add `pytestmark = pytest.mark.os_sensitive` at   |
|                            | module level (or mark fixture params for parameterized     |
|                            | suites). Periodically re-audit existing files for          |
|                            | correctness — see `@pytest.mark.os_sensitive` in          |
|                            | `pyproject.toml` for rationale.                           |
| **CHANGELOG entry**        | During development: one stub line per item —              |
|                            | `- <ID> <Title> [<type>]` under the correct section.      |
|                            | No details. One heading per section — no duplicates.      |
|                            | Section order: Added > Fixed > Known Issues > Changed >   |
|                            | Deprecated > Removed > Documentation > Internal.          |

---

## Quick reference — "Where do I…?"

| I need to…                               | Go here                                              |
|------------------------------------------|------------------------------------------------------|
| Find out what work is pending            | `sdd/BACKLOG.md` (active), `sdd/BACKLOG-DONE.md` (archive) |
| Understand how a feature should behave   | `sdd/specs/` (NNN-topic.md; IDs use STORE-, S3-, ERR- etc.) |
| Learn why a design decision was made     | `sdd/adrs/`                                          |
| Propose a significant change             | Write an RFC in `sdd/rfcs/` (see `rfc-template.md`)  |
| Explore feasibility of an idea           | Write a research doc in `sdd/research/`              |
| Record a new design decision             | Add an ADR in `sdd/adrs/`                            |
| Log a bug or improvement idea            | Append to `sdd/BACKLOG.md` (Ideas section)           |
| Document a user-facing change            | `CHANGELOG.md` — under `[Unreleased]` or version     |
| Share a process insight or lesson learned | `DEVELOPMENT_STORY.md`                               |
| Check or update code style conventions   | `sdd/DESIGN.md`                                      |
| Check or update testing quality rules    | `sdd/TESTING.md`                                     |
| Check or update doc content quality rules | `sdd/CONTENT-RULES.md`                              |
| Understand the full SDD workflow         | `sdd/000-process.md`                                 |
| Add or update a backend guide            | `guides/backends/` + docs nav                        |
| Run a quick smoke test                   | `examples/` — pick one and run it                    |
| Verify everything passes                 | `hatch run all` (lint + format-check + typecheck + test-cov + examples) |

---

## Local toolchain

`session-init.sh` auto-installs on Linux+root (claude.ai/code). On-prem: warn only.

| Tool  | Auto-install trigger       | Version | Manual fallback                  |
|-------|----------------------------|---------|----------------------------------|
| hatch | always (if missing)        | latest  | `uv tool install hatch`          |
| dafny | `sdd/formal/*.dfy` present | 4.11.0  | see `session-init.sh` for steps  |

---

## Repository layout

```
src/remote_store/          # Library source (backends, Store, errors, registry)
tests/                     # pytest suite — spec-traced via @pytest.mark.spec("ID")
examples/                  # Core runnable examples (run locally, no credentials)
examples/backends/         # Cloud backend examples (need services + credentials)
sdd/                       # Specs, ADRs, RFCs, research, audits, backlog, design docs
guides/backends/           # User-facing backend configuration guides
docs-src/                  # MkDocs Material documentation source
```

For backlog process, SDD workflow, and `sdd/` subtree details see `sdd/000-process.md`.
