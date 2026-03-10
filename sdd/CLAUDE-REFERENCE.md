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
| **A Store method**         | README Store API table, `__init__.py` `__all__`,          |
|                            | `examples/`, spec in `sdd/specs/`, guides, CHANGELOG      |
| **Public API** (`__all__`) | README Store API table, `examples/`, user guides          |
| **An extension**           | `__init__.py` exports (if pure Python),                   |
|                            | `pyproject.toml` extras (if optional dep),                |
|                            | `guides/`, `docs-src/` + `_nav.yml`, `examples/`,         |
|                            | CHANGELOG, BACKLOG                                        |
| **Docs navigation**        | Per-section `_nav.yml` files in `docs-src/`,              |
|                            | `guides/backends/index.md`,                               |
|                            | `sdd/DOCUMENTATION.md` § Navigation & Placement           |
| **Source/test/spec counts**| `DEVELOPMENT_STORY.md` "The Numbers" table                |

---

## Quick reference — "Where do I…?"

| I need to…                               | Go here                                              |
|------------------------------------------|------------------------------------------------------|
| Find out what work is pending            | `sdd/BACKLOG.md`                                     |
| Understand how a feature should behave   | `sdd/specs/` (NNN-topic.md; IDs use STORE-, S3-, ERR- etc.) |
| Learn why a design decision was made     | `sdd/adrs/`                                          |
| Propose a significant new feature        | Write an RFC in `sdd/rfcs/` (see `rfc-template.md`)  |
| Record a new design decision             | Add an ADR in `sdd/adrs/`                            |
| Log a bug or improvement idea            | Append to `sdd/BACKLOG.md` (Ideas section)           |
| Document a user-facing change            | `CHANGELOG.md` — under `[Unreleased]` or version     |
| Share a process insight or lesson learned | `DEVELOPMENT_STORY.md`                               |
| Check or update code style conventions   | `sdd/DESIGN.md`                                      |
| Understand the full SDD workflow         | `sdd/000-process.md`                                 |
| Add or update a backend guide            | `guides/backends/` + docs nav                        |
| Run a quick smoke test                   | `examples/` — pick one and run it                    |
| Verify everything passes                 | `hatch run all` (lint + format-check + typecheck + test-cov + examples) |

---

## Repository layout

```
src/remote_store/          # Library source (backends, Store, errors, registry)
tests/                     # pytest suite — spec-traced via @pytest.mark.spec("ID")
examples/                  # Core runnable examples (run locally, no credentials)
examples/backends/         # Cloud backend examples (need services + credentials)
sdd/                       # Specs, ADRs, RFCs, backlog, design docs
guides/backends/           # User-facing backend configuration guides
docs-src/                  # MkDocs Material documentation source
```

For backlog process, SDD workflow, and `sdd/` subtree details see `sdd/000-process.md`.
