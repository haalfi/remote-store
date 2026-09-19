# Accepted divergences in the published conda recipe

<!-- doc: repo-only -->

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

- **Keyed by YAML key path**, as `drift_feedstock.differing_keys` reports it:
  `extra.recipe-maintainers`, `about.summary`,
  `requirements.run_constraints[pyarrow]`. A row silences that key and nothing
  else, so an accepted maintainer-list edit does not also silence a changed
  dependency floor.
- **A drift stops holding the issue only when *every* differing key is
  registered.** One unregistered key and the finding is reported as new, with
  the registered ones still named beside it.
- **`Review by` is read by code**, through the same predicate the other two
  registers use. Past its date a row stops silencing and the difference is
  reported as new again, with its owner still named. Extending a date without
  re-reading the rationale is what that enforcement exists to prevent.
- **A row is a decision, not a note.** It is committed so that adding or
  removing one is a reviewable act.

An empty table is the healthy state, and is the state this file ships in: no
divergence is accepted today.

## Accepted divergences

| Key path | Owner | Rationale | Review by |
|---|---|---|---|
</content>
