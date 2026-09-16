<!-- doc: repo-only -->
# Floor-lane register

Floor-lane findings that are **known and tracked**, so the weekly run can tell
them from new ones. Without this file every known-bad floor is red every week,
the rolling issue carries the same rows indefinitely, and the maintainer stops
reading it — which is the failure
[`sdd/DRIFT-RULES.md` Rule 6](../../sdd/DRIFT-RULES.md#tolerated) requires a
register to prevent, on pain of the check being switched off instead.

`scripts/drift_report.py` reads the table below. An extra listed here renders
under "Known floor findings" and does not on its own hold the rolling issue
open; an extra **not** listed renders as a new finding and does. Removing a row
is therefore how a fixed floor starts counting again — delete the row in the
same change that raises the floor.

A row is not permission to leave a floor wrong. It records who owns the fix and
when the decision is re-read.

## File format

One table, one row per extra. `Owner` is the backlog item tracking the fix.
`Review by` is when the row itself expires: past that date, re-read the
rationale rather than the row.

| Extra | Owner | Rationale | Review by |
|---|---|---|---|
| `[arrow]` | BUG-287 | `pyarrow>=12.0.0` installs on the oldest supported interpreter and then fails to import against a current `numpy` — `numpy.core.multiarray failed to import`. numpy stays newest under `lowest-direct`, so the floor broke without anyone editing it. Raising it is a floor bump with its own migration obligations. | 2026-12-31 |
| `[sql-query]` | BUG-287 | Same `pyarrow>=12.0.0` declaration as `[arrow]`; `sqlalchemy>=2.0.31` resolves and imports cleanly. | 2026-12-31 |
| `[s3-pyarrow]` | BUG-287 | Same cause one minor up: `pyarrow>=14.0.0` against a current `numpy`. `s3fs>=2024.2.0` resolves and imports cleanly. | 2026-12-31 |
| `[azure]` | BUG-288 | `aiohttp>=3.0` names a release that installs and cannot be imported on any interpreter this package supports (`cannot import name 'Mapping' from 'collections'`). The bound was taken from `azure-core`'s own metadata and never exercised. | 2026-12-31 |
