<!-- doc: repo-only -->
# Agent Use-Case Traces

Ordered reading paths through the repo's specs and rulings for common
agent tasks. Each trace lists the exact file and section to read, in
the order they are needed, with a one-line note on what you are
extracting at that step.

These are not tutorials — they are navigation aids. Read the referenced
section, apply what it says, move on.

---

## Use-case index

| # | Use case |
|---|----------|
| 1 | [Design a new extension](#1-design-a-new-extension) |

---

## 1. Design a new extension

**Trigger:** you need to add a new composable layer in `remote_store.ext.*`
(or `remote_store.aio.ext.*`).

**Definition of done:** spec written, tests passing, code merged, all
ripple-check items updated, CHANGELOG stub added.

---

### Phase 1 — Orient

| File | Section | Extract |
|------|---------|---------|
| `CLAUDE.md` | § Principles | The 7 project-wide working rules; apply throughout every phase |
| `FEATURES.md` | § Extensions | Inventory of existing extensions: module names, key exports, optional extras, problem each solves — understand the pattern before adding to it |
| `sdd/CLAUDE-REFERENCE.md` | § "Where do I…?" table | Quick cross-reference for where decisions, specs, ADRs, and backlog items live |
| `sdd/CLAUDE-REFERENCE.md` | Ripple-check table → **"An extension"** row | Preview the 9 artifacts you must update before the PR can merge; read this now so nothing is forgotten at the end |

---

### Phase 2 — Spec

| File | Section | Extract |
|------|---------|---------|
| `sdd/000-process.md` | § Rules | Rule 1 (no code without a spec), Rule 6 (Features pipeline: SPEC → TEST → IMPLEMENT → VALIDATE → DOCS) |
| `sdd/000-process.md` | § Document types | Decision rule: if proposing a significant new capability → write an RFC in `sdd/rfcs/` first; if the design is settled → write the spec directly in `sdd/specs/` |
| `sdd/000-process.md` | § Spec format | Required spec skeleton: `PREFIX-NNN` section IDs, Invariant, Preconditions, Postconditions, Raises, Example |
| `sdd/specs/` — pick one analog extension spec | Full file | Structural reference; good analogs: `016-ext-batch.md` (stateless helpers), `019-ext-observe.md` (Store-wrapping proxy), `023-ext-cache.md` (stateful wrapper) |
| `sdd/specs/001-store-api.md` | Full file | Store contracts your extension depends on; identify which `Store` methods you call and which capabilities you require |
| `sdd/specs/003-backend-adapter-contract.md` | Full file | Backend ABC; read if your extension touches backends directly or declares capability requirements |

**Output of this phase:** `sdd/specs/NNN-ext-<name>.md` committed to the branch.

---

### Phase 3 — Tests (write before implementing)

| File | Section | Extract |
|------|---------|---------|
| `sdd/TESTING.md` | § Test Subpackage Placement | Determines the file path for your tests; extension unit tests go in `tests/` root, not a subdirectory |
| `sdd/TESTING.md` | § Rules | 12 quality rules; the critical ones for extensions: Rule 4 (`spec=` on every MagicMock), Rule 5 (mock at the Backend ABC boundary, not third-party internals), Rule 6 (prefer `MemoryBackend` over mocks) |
| `sdd/000-process.md` | § Test traceability | Add `@pytest.mark.spec("EXT-NNN")` to every test; `pytest -m spec` must exercise all spec IDs |
| `sdd/DESIGN.md` | § 11 (Test style) | Class docstring references spec IDs; each method carries `@pytest.mark.spec` |

**Output of this phase:** `tests/test_ext_<name>.py` committed; `hatch run test` shows the new tests failing.

---

### Phase 4 — Implement

| File | Section | Extract |
|------|---------|---------|
| `sdd/DESIGN.md` | § 12 (Extension API contract) | Extensions MUST import via the public path (`from remote_store import X`); never from `remote_store._*` unless no public equivalent exists (add a comment if unavoidable). `test_no_private_module_imports` enforces this |
| `sdd/DESIGN.md` | § 1 (Formatting & Linting) | ruff + mypy strict; `from __future__ import annotations` in every module |
| `sdd/DESIGN.md` | § 2 (Module description) | First line of every module is a 1–2 sentence docstring explaining *why it exists* |
| `sdd/DESIGN.md` | § 3 (Type annotations) | PEP 604 unions; required args positional, behavior flags keyword-only |
| `sdd/DESIGN.md` | § 4 (Docstrings) | Google style; `Args:`, `Returns:`, `Raises:`; no RST roles |
| `sdd/DESIGN.md` | § 6 (Method ordering) | Class variables → `__init__` → properties → public methods → dunder → private helpers |
| `sdd/DESIGN.md` | § 9 (`__all__`) | Declared in the package `__init__.py` only; read ADR-0013 before deciding whether to re-export: pure-Python extensions ARE re-exported; optional-dep extensions are NOT |
| `sdd/DESIGN.md` | § 10 (Error messages) | f-string with context; structured attributes for programmatic access |

**Output of this phase:** `src/remote_store/ext/<name>.py` (or `aio/ext/<name>.py`) committed; `hatch run all` passes.

---

### Phase 5 — Docs

| File | Section | Extract |
|------|---------|---------|
| `sdd/AUTHORING.md` | § "Where does my new file go?" | Guide → `docs-src/guides/` (docs-only, no marker needed); API reference page → `docs-src/reference/api/extensions/<name>.md` (docs-only); spec is dual by directory default |
| `sdd/AUTHORING.md` | § Classification markers | Only applies if you create a file outside the directory-default table; most extension docs do not need an explicit marker |
| `sdd/DOCUMENTATION.md` | § 1 (Diataxis placement) | Guide answers "how do I use this?"; reference answers "what does it do?"; keep them separate |
| `sdd/DOCUMENTATION.md` | § 2 (Content homes) | `docs-src/guides/` for usage guide; `docs-src/reference/api/extensions/` for the API reference page |
| `sdd/DOCUMENTATION.md` | § 3 (Docstring completeness) | Public methods need `Args`, `Returns`, `Raises`, and an `Example:`; class needs `Args` and `Example:` |
| `sdd/DOCUMENTATION.md` | § API page building blocks | Required blocks for the reference page: Class header, Method sections, See also. Use the admonition vocabulary (`!!! note "Requires Capability.X"`) for capability gates |
| `sdd/DOCUMENTATION.md` | § 4 (Cross-linking requirements) | Guide must link to the API reference page; API page must link back to the guide (in docstring `See the [X Guide](...)`); both must link to a matching example |
| `sdd/CONTENT-RULES.md` | § Rules 1–6 | Longevity rules: 6-month test (R1), principles over enumerations (R2), one copy per fact (R4), source code examples from `examples/snippets/` via `--8<--` (R6) |

**Output of this phase:** guide, API reference page, and docstrings all in place; `hatch run all` still passes.

---

### Phase 6 — Ripple check (before merge)

Read the **"An extension"** row in `sdd/CLAUDE-REFERENCE.md` § Ripple-check table and verify each item:

| Artifact | Rule |
|----------|------|
| `src/remote_store/__init__.py` exports | Add to `__all__` if pure-Python; omit if optional-dep (ADR-0013) |
| `pyproject.toml` `[project.optional-dependencies]` | Add a new extra if the extension requires an optional dep |
| `README.md` extensions table | Add one row: extension name, problem it solves, module path |
| `FEATURES.md` § Extensions | Add one row to the "Always available" or "Optional" table |
| `docs-src/reference/api/extensions/<name>.md` | New API reference page (Phase 5) |
| `docs-src/reference/api/extensions/index.md` | Add an entry |
| `docs-src/reference/api/extensions/_nav.yml` | Add nav entry |
| `docs-src/guides/` | New guide (Phase 5) |
| `docs-src/_nav.yml` | Wire the new guide into Guides section |
| `examples/` | Add a runnable example script |
| `CHANGELOG.md` § [Unreleased] | One-line stub: `- BK-NNN: Add ext.<name> extension` |
| `sdd/BACKLOG.md` | Move the item to `sdd/BACKLOG-DONE.md` in the same commit |

Then run: `hatch run lint` (catches ripple-check drift on FEATURES.md and BACKLOG IDs) followed by `hatch run all`.
