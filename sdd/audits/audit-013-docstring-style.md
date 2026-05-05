# Audit 013 — Docstring Style Compliance

**Date:** 2026-05-05
**Scope:** All Python docstrings in `src/`, `tests/`, and `scripts/` at
`master` `f5c8c37`.
**Method:** Agent-assisted full read of every `.py` file; each docstring
cross-checked against the three rules extracted below.

---

## Checked rules

**DESIGN.md § 2** — Every module starts with a 1-2 sentence docstring explaining *why it exists*.

**DESIGN.md § 4** — Google style (`Args:`, `Returns:`, `Raises:`). Short and purpose-focused.
RST cross-reference roles (`:class:`, `:mod:`, `:meth:`, `:func:`, `:data:`, `:exc:`, `~`-prefix)
are not defined in Google style. They render as literal punctuation-laden text in every renderer
that does not process RST (plain GitHub, mkdocstrings in Google mode, IDEs).

**DOCUMENTATION.md § 3** — Completeness by symbol type:

| Symbol | `Args` | `Returns` | `Raises` | Example |
|---|---|---|---|---|
| Public method | Yes | Yes | Yes | Yes (short) |
| Property | — | Yes (in summary) | If applicable | Optional |
| Class | Yes (`__init__` params) | — | — | Yes |
| Function | Yes | Yes | Yes | Yes |
| Enum | — | — | — | — |
| Error class | — | — | — | — |

**DOCUMENTATION.md — Docstring style notes** — Supplementary context goes in a `Notes:` block.
Use `Example:` (not `Usage:`). For module-level docstrings use `!!! example` admonition syntax.

---

## Summary

| Severity | Count | Description |
|---|---|---|
| High | 8 | RST roles in `src/` — render as literal text on the published docs site |
| Medium | 5 | RST roles in `tests/`/`scripts/` — style violation, not published |
| Low | 1 | Module docstring far exceeds the 1-2 sentence guideline |

---

## Findings

### `src/remote_store/_async_to_sync_adapter.py` — 4 High

| ID | Line(s) | Symbol | Violation |
|---|---|---|---|
| 1 | 3, 6 | module | `:class:` × 2 (`Backend`, `AsyncBackend`) |
| 2 | 209, 215, 228 | `unwrap` | `:class:` × 2, `:meth:` (with `~`) |
| 3 | 289 | `check_health` | `:class:` with `~` |
| 4 | 329 | `read` | `:class:` (`io.RawIOBase`) |

### `src/remote_store/_config.py` — 1 High

| ID | Line(s) | Symbol | Violation |
|---|---|---|---|
| 5 | 405 | `resolve_env` | `:data:` (`os.environ`) |

### `src/remote_store/_info.py` — 1 High

| ID | Line(s) | Symbol | Violation |
|---|---|---|---|
| 6 | 35 | `InfoResult` | `:func:` (`info`) |

### `src/remote_store/aio/_async_store.py` — 1 High

| ID | Line(s) | Symbol | Violation |
|---|---|---|---|
| 7 | 81 | `_read_chunks` | `:meth:` (`read`) |

### `src/remote_store/aio/_sync_adapter.py` — 1 High

| ID | Line(s) | Symbol | Violation |
|---|---|---|---|
| 8 | 47, 50 | `SyncBackendAdapter` | `:class:` × 2, `:func:` (`asyncio.to_thread`) |

### `tests/backends/test_azure_live_hns.py` — 3 Medium, 1 Low

File added in BUG-191/BUG-182; RST introduced despite doc-system rules being in scope.

| ID | Line(s) | Symbol | Violation | Sev |
|---|---|---|---|---|
| 9 | 6, 7, 11, 13, 17, 39 | module | `:mod:` × 2, `:class:` × 4 (incl. `~`) | Medium |
| 10 | 147 | `live_hns_backend` fixture | `:meth:` with `~` | Medium |
| 11 | 247 | `TestAzureLiveHnsMetadataSurvivesRename` | `:mod:` | Medium |
| 12 | 1–54 | module | 54-line docstring vs 1-2 sentence rule; rationale belongs in section comments | Low |

### `scripts/gen_pages.py` — 1 Medium

| ID | Line(s) | Symbol | Violation |
|---|---|---|---|
| 13 | 8, 15 | module | `:func:` with `~`, `:mod:` |

### `scripts/mkdocs_hooks.py` — 1 Medium

| ID | Line(s) | Symbol | Violation |
|---|---|---|---|
| 14 | 1 | module | `:class:` (`LinkResolver`) |

---

## Out of scope

- **Double-backtick `` ``foo`` ``** — valid Google-style inline code, not an RST role. Not flagged.
- **Em dashes in summary lines** — within CLAUDE.md convention (`—`, sparingly). Not flagged.
- **Test methods without docstrings** — DESIGN.md § 11 does not require prose on every test method. Not flagged.
