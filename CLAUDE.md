# Claude Code Instructions

## Project

Python library providing a unified file storage abstraction across backends
(Local, S3, SFTP, Azure). Follows Spec-Driven Development (SDD).

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
hatch run all               # lint + typecheck + test
```

## Key conventions

- **Specs are authoritative** — if code and spec disagree, fix the code.
- **Test traceability** — spec-derived tests use `@pytest.mark.spec("ID")`.
- **Immutable config** — dataclasses use `frozen=True`.
- **Error mapping** — backends must map native exceptions to `RemoteStoreError`
  subtypes. Never let raw `OSError`/`botocore`/`paramiko` exceptions leak.
- **No code without a spec** — new features need a spec section in `sdd/specs/`.
  Operational changes (CI, docs, deps) skip the spec step.

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
