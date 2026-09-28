# BUG-287 — Three extras declare a `pyarrow` floor that installs and then cannot import
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`[arrow]` and `[sql-query]` declare `pyarrow>=12.0.0`, `[s3-pyarrow]`
declares `pyarrow>=14.0.0`. At those floors, against a current `numpy`,
`import pyarrow` raises
`ImportError: numpy.core.multiarray failed to import` — numpy 2 support
lands in pyarrow 16. All three install cleanly first, which is the class a
floor must exclude and the one nothing announces.
**Measured**, on the oldest supported interpreter, by resolving each extra at
`--resolution lowest-direct` and importing: three collection errors for
`[arrow]`'s smoke, and the same import failure for the other two.
**This falsifies a claim in the item that motivated the lane.** BK-369's body
said *"a floor that pip refuses (no wheel for the interpreter) is
self-announcing, and pyarrow's two floors are in that class and are fine"*.
Both floors ship a `cp310-cp310-manylinux` wheel and install without
complaint; the refusal BUG-285 measured was on the *newest* interpreter,
where no wheel exists. On the oldest — where the lane runs — they are in the
target class, not the self-announcing one.
Fix is a floor raise, priced by
[`CONTRIBUTING.md` § When to bump](../../CONTRIBUTING.md#when-to-bump): find the
oldest pyarrow that imports against a current numpy, raise all three, refresh
the recipe pins and the baselines, and delete the three rows from
`infra/drift-locks/KNOWN-FINDINGS.md`. **Check whether a `numpy` bound is the
better answer** before raising: the failure is an interaction, and
`lowest-direct` leaves numpy newest deliberately, so a floor raise fixes the
combination the lane tests while a bound fixes the one a user hits.

## Re-measured, 2026-09-28

The declarations hold (`rg -n 'pyarrow' pyproject.toml`): `sql-query` and
`arrow` at `pyarrow>=12.0.0`, `s3-pyarrow` at `pyarrow>=14.0.0`;
`rg -n numpy pyproject.toml` finds no numpy bound. `KNOWN-FINDINGS.md` carries
the three BUG-287 rows. Both conda recipes pin `pyarrow >=14.0.0`
(`rg -n pyarrow packaging/conda-forge/recipe.yaml
packaging/conda-forge/feedstock/recipe.yaml`), so a raise touches both. BK-377's
entry in `BACKLOG-DONE.md` (`:892-897`) exercised this item's raise and found
`pyarrow` 14.0.0 → 16 patch-eligible rather than breaking, which updates the
"migration obligations" framing. The import failure needs a floor install
and was not re-run. Found by the ADR-0040 § 5 conversion.
