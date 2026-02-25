# Claude Code Instructions

## Project

Python library providing a unified file storage abstraction across backends
(Local, S3, SFTP, Azure). Follows Spec-Driven Development (SDD).

---

## Principles

These apply to every change — code, docs, CI, config. No exceptions.

### 1. Ship complete, not "almost done"

A change is finished when **everything it touches** is consistent: code, tests,
docs, examples, CHANGELOG, BACKLOG, navigation. If a PR adds a backend but
skips the docs nav, the example, or the README table — it's not done. Ship it
all in the same PR, or explicitly track what remains as `[~]` in the backlog.

### 2. Verify beyond the diff

After making a change, **search for what references the thing you changed.**
The blast radius is always wider than the files you edited.

Use the ripple-check table below — it encodes the sync failures that have
actually happened in this repo:

| If you changed…            | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **A backend**              | README backends table, `pyproject.toml` extras,           |
|                            | `guides/backends/`, docs nav, `examples/`,                |
|                            | `sdd/specs/`, `CONTRIBUTING.md` repo structure,           |
|                            | `src/remote_store/_registry.py` auto-registration         |
| **An error type**          | `sdd/specs/005-error-model.md`, all backends' error       |
|                            | mapping, tests for every backend                          |
| **A capability**           | `sdd/specs/003-backend-adapter-contract.md`,              |
|                            | every backend's `capabilities()`, Store surface API       |
| **Version number**         | `pyproject.toml`, `src/remote_store/__init__.py`,         |
|                            | `CITATION.cff` (version + date-released),                 |
|                            | `CHANGELOG.md` (new heading + `[Unreleased]` section)     |
| **A spec section**         | Tests with `@pytest.mark.spec("ID")`, BACKLOG if related  |
| **A dependency**           | `pyproject.toml` extras + minimum pins, README install    |
|                            | instructions, docs prerequisites                          |
| **Store or Backend ABC**   | All backend implementations, conformance tests            |

### 3. The repo describes reality — at every commit

The backlog, CHANGELOG, docs, and README describe what **is**, not what was or
what will be. If reality changed, these change in the same commit. "I'll update
that later" means "it won't get updated." If you can't update it now, mark it
`[~]` with a note of what remains.

### 4. Specs are the source of truth

If code and spec disagree, the code is wrong. If the backlog and git history
disagree, the backlog is wrong. When you find an inconsistency, fix the less
authoritative side — don't leave it for someone else.

### 5. Run it, don't just type-check it

Verify **behavior**, not just signatures. This repo learned the hard way: every
backend declared `read() -> BinaryIO`, mypy was happy, specs said "streaming" —
but all four backends loaded entire files into memory. Tests checked types; none
checked actual streaming. Before documenting that something works, **run it**.
Before claiming a fix, **reproduce the bug and confirm it's gone**.

---

## Quick reference — "Where do I…?"

| I need to…                               | Go here                                              |
|------------------------------------------|------------------------------------------------------|
| Find out what work is pending            | `sdd/BACKLOG.md`                                     |
| Understand how a feature should behave   | `sdd/specs/` (NNN-topic.md files; section IDs inside use STORE-, S3-, ERR- etc.)|
| Learn why a design decision was made     | `sdd/adrs/`                                          |
| Propose a significant new feature        | Write an RFC in `sdd/rfcs/` (see `rfc-template.md`)  |
| Record a new design decision             | Add an ADR in `sdd/adrs/`                            |
| Log a bug or improvement idea            | Append to `sdd/BACKLOG.md` (Ideas section)           |
| Document a user-facing change            | `CHANGELOG.md` — under `[Unreleased]` or version     |
| Share a process insight or lesson learned | `DEVELOPMENT_STORY.md`                               |
| Check or update project conventions      | `sdd/DESIGN.md`                                      |
| Understand the full SDD workflow         | `sdd/000-process.md`                                 |
| Add or update a backend guide            | `guides/backends/` + docs nav                        |
| Run a quick smoke test                   | `examples/` — pick one and run it                    |
| Verify everything passes                 | `hatch run all` (lint + format-check + typecheck + test-cov + examples) |

---

## Backlog — MANDATORY

The backlog (`sdd/BACKLOG.md`) is the single source of truth for all work.
**Every session that changes code or docs must leave the backlog consistent.**

### Before starting work

1. Read `sdd/BACKLOG.md` to understand current state.
2. If the task maps to an existing item (AF-NNN, BK-NNN, BL-NNN, ID-NNN),
   note the ID — you will reference it in commits and update it when done.

### After completing work

3. **Mark the item `[x]` done** in `sdd/BACKLOG.md` and add a one-line
   "Done:" note describing what was shipped and in which version.
4. If the work only partially addresses an item, mark it `[~]` (in progress)
   and note what remains.
5. Include the backlog update in the **same commit or PR** as the code change.
   Do not leave it for a follow-up.

### Commit messages

When a commit closes or advances a backlog item, **start the message with the
item ID**:

```
AF-008: Add credential masking to backend __repr__
BK-002: Implement glob strategy with client-side fallback
```

### Status markers

```
[ ]  pending
[~]  in progress
[x]  done
```

## Development commands

```bash
hatch run test              # run tests (pytest, 95% coverage required)
hatch run lint              # ruff check + format
hatch run typecheck         # mypy strict on src/
hatch run all               # lint + format-check + typecheck + test-cov + examples
```

## Code conventions

- **Test traceability** — spec-derived tests use `@pytest.mark.spec("ID")`.
- **Immutable config** — dataclasses use `frozen=True`.
- **Error mapping** — backends must map native exceptions to `RemoteStoreError`
  subtypes. Never let raw `OSError`/`botocore`/`paramiko` exceptions leak.
- **No code without a spec** — new features need a spec section in `sdd/specs/`.
  Operational changes (CI, docs, deps) skip the spec step.
- **Formatting** — run `hatch run lint` before committing. Pre-commit hooks
  enforce ruff and mypy, but only on staged files.

## Repository layout

```
src/remote_store/           # library source
tests/                      # pytest suite
sdd/
  BACKLOG.md                # work tracker (blockers → backlog → ideas → done)
  000-process.md            # SDD process rules
  DESIGN.md                 # design conventions
  specs/                    # specifications (NNN-topic.md)
  adrs/                     # architecture decision records
  rfcs/                     # proposals
guides/backends/            # user-facing backend docs
examples/                   # runnable examples
```
