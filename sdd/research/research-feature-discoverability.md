# Research: Feature Discoverability for Agents and Humans

**Item ID:** (none — exploratory research)
**Date:** 2026-03-30
**Context:** Claude Code operating in this repo consistently fails to ground its
plans in the actual feature surface of the installed version. The research
question: what proven patterns exist for exposing a Python package's features
to both AI coding agents and human developers, and what should remote-store
adopt?

---

## 1. Problem Statement

The symptom: an agent says _"Let me check remote-store v0.20.0's available
features to make sure my plan is grounded"_ — and then gets it wrong because
the answer is spread across four files (`README.md`, `docs-src/capabilities-matrix.md`,
`guides/extensions.md`, `guides/choosing-a-backend.md`) none of which is
authoritative in isolation.

Remote-store's feature/capability model is actually mature:

- `Capability` enum (10 values) gates every Store method.
- `CapabilitySet` is declared by every backend as an abstract property.
- `_BACKEND_FACTORIES` holds registered backends; lazy imports handle missing
  optional dependencies gracefully.
- 14 extras in `pyproject.toml` map to 8 backends and 6 extensions.
- `Store.supports(Capability)` and `Store.resolve()` provide runtime introspection.

What's missing is a **single, always-findable entry point** that answers
"what does this package offer at this version?" without requiring a reader to
synthesise multiple files.

---

## 2. Industry Survey

### 2.1 fsspec — `available_implementations()`

`fsspec` maintains a global registry (`known_implementations: dict[str, ...]`)
and exposes `fsspec.available_implementations()` for runtime queries. Each
filesystem class declares its own info via class attributes. The pattern maps
cleanly to remote-store's existing `_BACKEND_FACTORIES` + `CapabilitySet`.

**Verdict:** Closest match. Remote-store already has the registry; what's
missing is a public API surface over it.

### 2.2 Entry points + `importlib.metadata`

The PyPA-recommended pattern for plugin discovery. Plugins declare themselves
in `pyproject.toml` under `[project.entry-points]`; consumers discover them
via `importlib.metadata.entry_points(group=...)`. Used by pytest, Sphinx,
Flask extensions.

Pros: standard, cross-package, no import required.
Cons: describes *installation-time registration*, not runtime availability
(a backend could register but fail to import if a dependency is absent).

**Verdict:** Better suited to a third-party plugin ecosystem than to
first-party backends. Not the right fit here.

### 2.3 `importlib.metadata` extras / `Provides-Extra`

`importlib.metadata.metadata("remote-store").get_all("Provides-Extra")` lists
declared extras. Agents can query this without importing the package.

Pros: zero code, always accurate for declared extras.
Cons: tells you what *can* be installed, not what *is* installed or what
capabilities each extra unlocks.

**Verdict:** Useful as a secondary signal; insufficient alone.

### 2.4 Machine-readable manifest (JSON/TOML in package data)

A `features.json` or `features.toml` bundled via `package-data`, readable via
`importlib.resources`. Not an established standard — every package that does
this invents its own schema.

Pros: queryable without executing package code; version-stable.
Cons: non-standard; duplicate-information risk; no automatic validation.

**Verdict:** Viable, but requires a convention most readers won't know to look for.

### 2.5 Static `FEATURES.md` at repo root

A versioned prose+table snapshot committed alongside each release. Markdown
is readable by agents (file read), humans (GitHub/browser), and CI (lint).

Pros: always findable at a well-known path; no code required; can be
referenced from `CLAUDE.md`; survives import failures; accurate per version.
Cons: requires discipline to keep in sync; one more file to update at release.

**Verdict:** Highest discoverability for agents operating on a cold-start
basis. Complements, not replaces, the runtime API.

### 2.6 Runtime `info()` / `__features__` dict

A callable that interrogates the live registry and optional-dependency probes,
returning structured data. `__features__` as a module-level constant predates
runtime queries and goes stale.

Pros: answers "what is *currently* available in *this environment*";
programmatically queryable; no schema convention required.
Cons: requires code execution; probe logic needs maintenance as new optionals
are added.

**Verdict:** Best for runtime verification; pairs well with the static manifest.

### 2.7 MCP (Model Context Protocol) tool schemas

An emerging standard for AI-native tool exposure. Packages or services expose
a `tools/list` endpoint returning JSON-RPC schemas. Already used by GitHub
Copilot. Heavyweight; requires a server/client architecture.

**Verdict:** Future-facing and purpose-built for agents, but premature for a
library that is not serving an API endpoint.

---

## 3. Scoring Summary

| Pattern | AI agent | Human | Notes |
|---|---|---|---|
| Static `FEATURES.md` at root | ★★★★☆ | ★★★★☆ | Single entry point; no execution needed |
| Runtime `info()` function | ★★★★☆ | ★★★☆☆ | Answers environment-specific questions |
| `importlib.metadata` extras | ★★★☆☆ | ★★★★☆ | Install-time; incomplete on capabilities |
| fsspec-style registry API | ★★★★☆ | ★★★☆☆ | Already half-implemented in `_registry.py` |
| Entry points | ★★★☆☆ | ★★★☆☆ | Better for third-party plugin ecosystems |
| JSON/TOML manifest in pkg data | ★★★☆☆ | ★★★☆☆ | Non-standard; duplication risk |
| MCP tool schemas | ★★★★★ | ★★☆☆☆ | Premature for a library |

---

## 4. Recommendations

### R-1 — `FEATURES.md` at repo root (high value, low cost)

Create a single versioned file at the repo root. Minimum sections:

- Package version and date
- Backends table: type-string, extras install, always-available flag,
  capability list
- Extensions table: name, always-available, extras install
- Core `Store` API methods grouped by `Capability` gate
- `Capability` enum values with plain-English descriptions

Reference it from `CLAUDE.md` and add its update to the release checklist in
`CONTRIBUTING.md`. This single change resolves the cold-start agent problem
immediately — the file is findable via `Glob("FEATURES.md")` or by reading
the `CLAUDE.md` pointer.

### R-2 — `remote_store.info()` public function (medium cost)

Expose a top-level `info() -> dict` that:

1. Triggers `_register_builtin_backends()` to populate `_BACKEND_FACTORIES`.
2. For each backend, records availability (present in registry = True) and the
   extra required to install it.
3. Probes each optional extension via `importlib.util.find_spec()` (no import
   needed).
4. Returns a structured dict with `version`, `backends`, `extensions`.

This answers what `FEATURES.md` cannot: "is `azure` actually importable in
*this* environment right now?" Approximately 60–80 lines of new code in
`_info.py`, exported from `__init__.py`.

### R-3 — Reference `FEATURES.md` in `CLAUDE.md`

One line under a "Feature reference" heading:

> See `FEATURES.md` at the repo root for the authoritative list of backends,
> extensions, capabilities, and install extras for the current version.

This costs nothing and ensures every agent session starts with awareness of
where to look.

---

## 5. Out of Scope

- MCP integration: not warranted for a pure-library package at this stage.
- Entry-point registration for built-in backends: adds complexity without
  benefit over the existing lazy-import registry.
- `__features__` constant: `info()` is strictly better (environment-aware,
  no staleness risk).

---

## 6. Related Files

| File | Role |
|---|---|
| `src/remote_store/_capabilities.py` | `Capability` enum — 10 values |
| `src/remote_store/_registry.py` | `_BACKEND_FACTORIES`, `_register_builtin_backends()` |
| `src/remote_store/__init__.py` | Public API; `__version__` |
| `pyproject.toml` §`optional-dependencies` | 14 extras → 8 backends + 6 extensions |
| `docs-src/capabilities-matrix.md` | Human-readable matrix (currently fragmented) |
| `guides/extensions.md` | Extensions overview (currently fragmented) |
