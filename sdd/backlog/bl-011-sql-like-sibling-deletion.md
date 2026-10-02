# BL-011 — `SQLBlobBackend.delete_folder` deletes sibling keys, and listings return them, because prefix `LIKE` patterns leave `_` and `%` unescaped
<!-- doc: repo-only -->

Filed as a release blocker by maintainer decision on 2026-09-27, absorbing
BUG-241. The index entry holds the current diagnosis; this file and BUG-241's
dossier are evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

- (was BUG-241, absorbed here) Its body, the `LIKE` site list and the
  reproduction are in [BUG-241's dossier](bug-241-sql-like-metacharacters.md),
  whose path does not move. Read its `## Correction, 2026-09-27` first: the
  body predates the measurement and scopes the defect to probes.

**Why `BL-`.** [§ ID prefixes](../BACKLOG.md#how-this-file-works) admits an item
whose shipping unresolved costs users more than delaying the release.
`delete_folder(path, recursive=True)` on a key holding `_` or `%` deletes rows
under sibling prefixes, with no error and no way to recover them short of a
backup, and `_` in object keys is common. A delayed release costs time; this
costs data.

## Correction, 2026-10-02

Escaping `_` and `%` was not the whole defect. Measured on base, same SQLite
setup as BUG-241's correction (`tmp/bl011_repro.py`, `tmp/bl011_glob.py` in
the implementing session):

- **SQLite's `LIKE` folds ASCII case**, while its `=` does not.
  `delete_folder("UP", recursive=True)` with no `UP/` folder deleted `Up/u.txt`
  and `up/l.txt`; `is_folder("UP")` answered `True` while `is_file` stays exact.
- **Glob's non-SQLite branch** (`_glob_to_like`) passed no `ESCAPE`, so it
  relied on the dialect's default, and translated `**/` to `%/` and `[...]` to
  `_`. Forced on SQLite: `**/*.csv` dropped root `a.csv`, `[]k]x` dropped
  `kx`, and `a_b/*` returned nothing. The first two are under-matches on every
  dialect that branch served, PostgreSQL included.

Both were folded into BL-011 by maintainer decision. Shipped shape: one
predicate, `SQLBlobBackend._under` (escaped `LIKE`, plus `substr` equality on
SQLite), and glob narrowing by literal prefix and literal tail on every
dialect.
