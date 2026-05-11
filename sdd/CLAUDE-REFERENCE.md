# Claude Code Reference
<!-- doc: repo-only -->

Lookup tables and detailed procedures for Claude Code sessions.
Scope: cross-file dependency checks, repo navigation, and layout.

---

## Ripple-check table

The ripple-check has two presentations of the same set of triggers:

- The **Pre-work index** below is a one-line-per-trigger scan you read **before starting work** that might touch backends, errors, capabilities, versions, specs, dependencies, or anything in the trigger column. It exists because 3/9 sampled PRs missed ripples by consulting the table only at verify-end (`sdd/research/research-agent-workflow-substrate.md` § 2.3).
- The **Detailed checklist** below it lists the same triggers with the full ripple set, used at verify-end after the diff is complete and by PR reviewers.

Both tables are presentations of the same set of triggers. If you add, remove, or rename a row, update both.

<!-- Two-presentations-one-source: every row in "Pre-work index" must have a
matching row in "Detailed checklist" and vice versa. Reviewer-enforced; if
drift recurs, consider promoting a check script (gen or lint) into BACKLOG. -->

### Pre-work index

Read this before starting. One line per trigger:

| Trigger                       | Ripples (at a glance)                                                              |
|-------------------------------|------------------------------------------------------------------------------------|
| A backend                     | README backends table, `pyproject` extras, guides, docs nav, examples, specs, `_registry.py` |
| An error type                 | `005-error-model.md` spec, every backend's error mapping + tests, docstring "raised by", troubleshooting guide |
| A capability                  | `003-backend-adapter-contract.md` spec, every backend's `capabilities()`, Store surface, capability matrix |
| Version number                | `bump-my-version` (drives `pyproject` file list), then `hatch run gen-graph`; full checklist in CONTRIBUTING § Phase 2 |
| A spec section                | Tests tagged `@pytest.mark.spec("ID")`, BACKLOG if related                         |
| A dependency                  | `pyproject` extras + pins, README install, docs prerequisites                      |
| Store or Backend ABC          | All backend implementations, conformance tests                                     |
| A public method signature     | Docstring (Args/Returns/Raises), examples that call it, guides referencing it      |
| A Store method                | README Store API table + comparison count, `__init__.py` `__all__`, README examples table, `examples/`, spec, guides, CHANGELOG |
| Public API (`__all__`)        | README Store API table, `reference/api/*.md` directive + index summary + `_nav.yml`, `examples/`, user guides; check `backends/__init__.py` `__all__` too |
| An extension                  | `__init__.py` exports (ADR-0013 rules), `pyproject` extras, README extensions table, `reference/api/extensions/*` + index + `_nav.yml`, guides, examples, CHANGELOG, BACKLOG |
| An example script             | README examples table, generated `tutorial/examples/<slug>.md`, `tests/test_examples.py` import |
| Docs navigation               | Per-section `_nav.yml` files, `docs-src/guides/backends/index.md`, AUTHORING Rule 1, DOCUMENTATION § Content homes |
| An API reference page         | DOCUMENTATION § API page building blocks + required sections                       |
| A bug fix                     | BACKLOG item, CHANGELOG stub under `[Unreleased]`, failing test **before** fix, spec if invariant contradicted |
| A backlog item touched        | Live trace at `sdd/traces/<id>-<slug>.yml` (CLAUDE.md § Trace authoring); schema at `sdd/traces/_schema.yml`; `audience` drives the CHANGELOG-required rule |
| Source/test/spec counts       | README badge + CI coverage report (no manual table)                                |
| A new test file               | OS-sensitive code? Add `pytestmark = pytest.mark.os_sensitive`; periodically re-audit |
| CHANGELOG entry               | One-line `- <ID>: <Title>` at top of `[Unreleased]`; release skill expands and groups |
| `CAPABILITIES` ClassVar       | `003-backend-adapter-contract.md` (BE-003), `test_capabilities.py`, `test_conformance.py`, custom-backend guide, `examples/snippets/` |
| `_GATING` dict (`_store.py`)  | `001-store-api.md` (STORE-gate entries), `test_store.py`, guides if a method's cap docs change, `store.md` admonitions (verified by `gen-api-check`, ID-170) |
| `_BACKEND_GATING` dict (`gen_graph.py`) | `003-backend-adapter-contract.md` (BE-gate entries), `backend.md` admonitions (verified by `gen-api-check`, ID-171) |
| `__mirror__` attribute        | Async spec (mirror invariant), `gen_graph.py` (mirrors-edge), `tests/` mirror test on add/remove |
| A new authoritative process doc in `sdd/` | CLAUDE.md § Documentation framework (if part of the trio), CONTRIBUTING § Authoritative Document Format Scope, sibling authority back-references, `.claude/skills/*/SKILL.md` foundation lists, `docs-src/explanation/design/_nav.yml`, and this ripple-check |

### Detailed checklist

Read this at verify-end (after the diff is complete) and during PR review. Each row expands the Pre-work index above:

| If you changed…            | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **A backend**              | README backends table, `pyproject.toml` extras,           |
|                            | `docs-src/guides/backends/`, docs nav, `examples/`,       |
|                            | `sdd/specs/`, `CONTRIBUTING.md` repo structure,           |
|                            | `src/remote_store/_registry.py` auto-registration         |
| **An error type**          | `sdd/specs/005-error-model.md`, all backends' error       |
|                            | mapping, tests for every backend,                         |
|                            | error docstring "raised by" list, troubleshooting guide   |
| **A capability**           | `sdd/specs/003-backend-adapter-contract.md`,              |
|                            | every backend's `capabilities()`, Store surface API,      |
|                            | capabilities matrix page                                  |
| **Version number**         | Run `bump-my-version` (manages the files listed in        |
|                            | `[[tool.bumpversion.files]]` in `pyproject.toml`);        |
|                            | then `hatch run gen-graph` to re-stamp `graph.json`.      |
|                            | Full checklist: `CONTRIBUTING.md` § Phase 2.              |
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
| **Public API** (`__all__`) | README Store API table, `docs-src/reference/api/*.md` directive |
|                            | (every `__all__` symbol needs a `:::` entry),             |
|                            | `docs-src/reference/api/index.md` summary table (every public |
|                            | class/function needs a row), `docs-src/reference/api/_nav.yml`, |
|                            | `examples/`, user guides.                                 |
|                            | **Check**: `backends/__init__.py` `__all__` too —         |
|                            | secondary public API (e.g. `SFTPUtils`) needs its own     |
|                            | `api/*.md` page and index entry                           |
| **An extension**           | `__init__.py` exports (pure-Python only; optional-dep     |
|                            | extensions are NOT re-exported — ADR-0013),               |
|                            | `pyproject.toml` extras (if optional dep),                |
|                            | README extensions table, `docs-src/reference/api/extensions/*.md` + |
|                            | `reference/api/extensions/index.md` + `reference/api/extensions/_nav.yml`, |
|                            | `docs-src/guides/`,      |
|                            | `docs-src/` + `_nav.yml`, `examples/`,                    |
|                            | CHANGELOG, BACKLOG                                        |
| **An example script**      | README examples table, generated `tutorial/examples/<slug>.md` |
|                            | `tests/test_examples.py` import                           |
| **Docs navigation**        | Per-section `_nav.yml` files in `docs-src/`,              |
|                            | `docs-src/guides/backends/index.md`,                      |
|                            | `sdd/AUTHORING.md` Rule 1 (file classification),          |
|                            | `sdd/DOCUMENTATION.md` § Content homes                    |
| **An API reference page**  | `sdd/DOCUMENTATION.md` § API page building blocks         |
| (new or restructured)      | and building blocks for required sections                 |
| **A bug fix**              | `sdd/BACKLOG.md` (item), `CHANGELOG.md` (stub line under  |
|                            | `[Unreleased]`), failing test **before** the fix, spec if |
|                            | the bug contradicts a spec invariant                      |
| **A backlog item touched** | Live trace at `sdd/traces/<id>-<slug>.yml` per `CLAUDE.md`|
|                            | § Trace authoring (mandatory). Created/updated as work    |
|                            | proceeds (not retrospectively); ships in same PR; schema  |
|                            | at `sdd/traces/_schema.yml`. `audience` priority-sorted   |
|                            | drives the CHANGELOG-required rule.                       |
| **Source/test/spec counts**| README badge + CI coverage report (no manual table)       |
| **A new test file**        | Ask: does it exercise OS-specific code (path separators,  |
|                            | `os.replace`, `tempfile`, local filesystem, atomic writes)?|
|                            | If yes → add `pytestmark = pytest.mark.os_sensitive` at   |
|                            | module level (or mark fixture params for parameterized     |
|                            | suites). Periodically re-audit existing files for          |
|                            | correctness — see `@pytest.mark.os_sensitive` in          |
|                            | `pyproject.toml` for rationale.                           |
| **CHANGELOG entry**        | Add `- <ID>: <Title>` at the top of `[Unreleased]`.       |
|                            | One line, no details, no sections. Release skill          |
|                            | organises into sections and expands to prose.             |
| **`CAPABILITIES` ClassVar**| `sdd/specs/003-backend-adapter-contract.md` (BE-003),     |
| (added/changed on a backend| `tests/test_capabilities.py` (class-attr parametrize list),|
| or ABC)                    | `tests/backends/test_conformance.py` (subset invariant),  |
|                            | `docs-src/guides/custom-backend-guide.md`, `examples/snippets/` |
| **`_GATING` dict**         | `sdd/specs/001-store-api.md` (STORE-gate entries),        |
| (key→Capability mapping    | `tests/test_store.py` (gate-fires parametrize list),      |
| in `_store.py`)            | `docs-src/guides/` if a method's capability docs change.  |
|                            | `docs-src/reference/api/store.md` `!!! note "Requires …"` |
|                            | admonitions — verified by `hatch run gen-api-check`       |
|                            | (ID-170)                                                  |
| **`_BACKEND_GATING` dict** | `sdd/specs/003-backend-adapter-contract.md` (BE-gate      |
| (key→cap-name strings      | entries), `docs-src/reference/api/backend.md` `!!! note "Requires   |
| in `scripts/gen_graph.py`) | …"` admonitions — verified by `hatch run gen-api-check`   |
|                            | (ID-171). Lives in gen_graph.py (static-extraction only;  |
|                            | Backend has no runtime _gate() equivalent).               |
| **`__mirror__` attribute** | `sdd/specs/` async spec (async-mirror invariant),         |
| (on an async backend)      | `scripts/gen_graph.py` (mirrors-edge emission),           |
|                            | `tests/` mirror test if backend is added or removed       |
| **A new authoritative**    | `CLAUDE.md` § Documentation framework (if part of the     |
| **process doc in `sdd/`**  | trio), `CONTRIBUTING.md` Authoritative Document Format    |
|                            | § Scope, sibling authority docs (back-references in       |
|                            | their Intent & Scope), `.claude/skills/*/SKILL.md`        |
|                            | foundation lists, `docs-src/explanation/design/_nav.yml`, |
|                            | and this ripple-check                                     |

---

## Quick reference — "Where do I…?"

| I need to…                               | Go here                                              |
|------------------------------------------|------------------------------------------------------|
| Find out what work is pending            | `sdd/BACKLOG.md` (active), `sdd/BACKLOG-DONE.md` (archive) |
| Understand how a feature should behave   | `sdd/specs/` (NNN-topic.md; IDs use STORE-, S3-, ERR- etc.) |
| Learn why a design decision was made     | `sdd/adrs/`                                          |
| Propose a significant change             | Write an RFC in `sdd/rfcs/` (see [`sdd/templates/rfc-template.md`](templates/rfc-template.md)) |
| Explore feasibility of an idea           | Write a research doc in `sdd/research/`              |
| Record a new design decision             | Add an ADR in `sdd/adrs/`                            |
| Log a bug or improvement idea            | Append to `sdd/BACKLOG.md` (Ideas section)           |
| Document a user-facing change            | `CHANGELOG.md` — under `[Unreleased]` or version     |
| Share a process insight or lesson learned | `DEVELOPMENT_STORY.md`                               |
| Check or update code style conventions   | `sdd/DESIGN.md`                                      |
| Check or update testing quality rules    | `sdd/TESTING.md`                                     |
| Check or update doc content quality rules | `sdd/CONTENT-RULES.md`                              |
| Understand the full SDD workflow         | `sdd/000-process.md`                                 |
| Add or update a backend guide            | `docs-src/guides/backends/` + docs nav               |
| Run a quick smoke test                   | `examples/` — pick one and run it                    |
| Verify everything passes                 | `hatch run all` (lint + format-check + typecheck + test-cov-strict + examples) |

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
docs-src/tutorial/         # Tutorial pages (Diataxis) — getting-started + examples
docs-src/guides/           # User-facing guides (Diataxis)
docs-src/guides/backends/  # Backend configuration guides
docs-src/reference/api/    # API reference pages (mkdocstrings)
docs-src/explanation/      # Explanation pages (Diataxis)
docs-src/explanation/design/ # Design docs — sdd/ dual files rendered here
docs-src/reference/        # Reference pages, FEATURES.md, migration guide
docs-src/                  # MkDocs Material documentation source (prose + nav)
```

For backlog process, SDD workflow, and `sdd/` subtree details see `sdd/000-process.md`.
