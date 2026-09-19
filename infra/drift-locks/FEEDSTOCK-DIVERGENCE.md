<!-- doc: repo-only -->
# Accepted divergences in the published conda recipe

`scripts/drift_feedstock.py` compares the recipe
`conda-forge/remote-store-feedstock` publishes against the generated copy this
repo committed at the tag its `context.version` names. A difference is normally
fixed by a pull request against the feedstock, per
[`sdd/CONDA-FORGE.md`](../../sdd/CONDA-FORGE.md).

**This file is for the differences that will not be.** The recipe lives in a
repository this project does not own, which is the one artifact pair here where
a divergence can be imposed without our consent — a conda-forge migrator, or the
`@conda-forge-admin, please add user @X` flow editing `extra.recipe-maintainers`.
Reverting such an edit is not the right answer, and
[`sdd/CONDA-FORGE.md` Rule 1](../../sdd/CONDA-FORGE.md) forbids the only in-repo
one: our copy governs, so changing it to match would be inventing a difference
rather than resolving one.

Without this register those edits would hold the **shared** `[drift-guard]`
issue open forever, because a feedstock `drift` forces an update on every run —
which would retire the dependency lanes' own "drift cleared" signal.
[`sdd/DRIFT-RULES.md` Rule 6](../../sdd/DRIFT-RULES.md#tolerated) is the rule
that asks for this, and it ends "A check with no such register will be switched
off instead".

## How this file works

- **Keyed by the published body itself**, as the sha256 `drift_feedstock`
  reports in its verdict. A row therefore accepts **one published file**, not a
  field and not a standing permission. `drift_report.py` reads the table below
  and a `drift` whose fingerprint a live row names stops holding the issue open.
- **Any further change on the far side ends the row's effect.** A second edit
  produces a different body, so a different fingerprint, so no matching row, and
  the whole difference is reported as new — with the accepted part still in it.
  That is the trade this key makes: re-cutting a row is the cost of never
  silencing something nobody looked at.
- **`Review by` is read by code**, through the same predicate the other two
  registers use. Past its date a row stops silencing and the difference is
  reported as new again. Extending a date without re-reading the rationale is
  what that enforcement exists to prevent.
- **A row is a decision, not a note.** It is committed so that adding or
  removing one is a reviewable act, and a row naming no owner is a hard failure
  rather than an anonymous silencer.

<a id="why-content"></a>
## Why content and not the YAML key

An earlier revision keyed rows on the differing YAML key path
(`extra.recipe-maintainers`, `requirements.run_constraints[pyarrow]`), which
reads better and had two measured defects a content key does not have.

3 of the recipe's 62 key paths could not be written as a row at all:
`tests[python:]`, `tests.python_version[${{]` and `tests.python_version["*"]`
are outside the loader's key shape, so those divergences were unregisterable.
(`drift_feedstock._key_path` over every line of the committed copy's
`comparable` form, distinct paths, matched against the old row pattern.)

And a difference `differing_keys` could not localize was reported as `?` and
dropped before the registration check. Driven on the real recipe: a
`run_constraints` pin bump plus one hand-added column-0 comment yields
`('requirements.run_constraints[pyarrow]',)` and nothing else, so a row for that
one key read as "every difference is accepted" and closed the rolling issue. The
same pair of edits changes the fingerprint.

Content is a total key: every possible published file has exactly one, and no
difference can hide inside a fingerprint that already matched. Key paths stay in
the rendered finding, where they name what changed for a reader and where being
imperfect costs nothing.

## File format

One table, one row per accepted published body. The first cell is the
fingerprint in backticks, `sha256:` followed by 64 lowercase hex digits, exactly
as the **Published body** line of the rolling issue's `Conda feedstock` section
prints it (`drift_feedstock.fingerprint` computes it over the *comparable* body,
so a `build.number` bump does not invalidate a row). That shape is what keeps
this loader from reading the sibling registers' rows. `Owner` is the ADR or
backlog item carrying the decision and may not be blank. `Rationale` says why
the difference stands. `Review by` is when the row expires, per the section
above.

| Published body | Owner | Rationale | Review by |
|---|---|---|---|

**An empty table is a valid state, not a stub**, and is the state this file
ships in: nothing is accepted today. A row exists only to say that somebody has
decided to leave a published divergence standing, and the weekly run reports one
whether or not this file has ever held a row.
