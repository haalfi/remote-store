<!-- doc: repo-only -->
# Drift-guard known findings

Findings the weekly run will keep reporting that somebody already owns, so the
run can tell them from new ones. Without this file every known-bad floor and
every known-failing smoke is reported afresh every week, the rolling issue
carries the same rows indefinitely, and the maintainer stops reading it — which
is the failure [`sdd/DRIFT-RULES.md` Rule 6](../../sdd/DRIFT-RULES.md#tolerated)
requires a register to prevent, on pain of the check being switched off instead.

`scripts/drift_report.py` reads the table below, keyed on **extra and lane**. A
row renders its finding as _known_ and stops it holding the rolling issue open;
a finding with no row renders as new and does hold it open. Removing a row is
therefore how a fix starts counting again — delete it in the same change that
lands the fix.

A row is not permission to leave a finding unfixed. It records who owns the fix
and when the decision is re-read.

**A week whose only findings are registered closes the issue**, so those rows
render nowhere that week — this file is where they live, and `Review by` is what
stops a row outliving its reason. That is the intended trade: an issue that is
open every Monday for the same five rows is one nobody opens.

**Scope: what the run reports, not what CI does.** A `newest`-lane smoke failure
still fails its job, registered or not — that is the posture that lane has
always had, and the `/drift` skill reads it. A floor leg never fails its job.
What a row changes is only whether the finding is presented as news.

## File format

One table, one row per extra and lane. `Lane` is `newest` or `floor`. `Owner` is
the backlog item tracking the fix. `Review by` is when the row itself expires:
past that date, re-read the rationale rather than the row.

| Extra | Lane | Owner | Rationale | Review by |
|---|---|---|---|---|
| `[arrow]` | floor | BUG-287 | `pyarrow>=12.0.0` installs on the oldest supported interpreter and then fails to import against a current `numpy` — `numpy.core.multiarray failed to import`. numpy stays newest under `lowest-direct`, so the floor broke without anyone editing it. Raising it is a floor bump with its own migration obligations. | 2026-12-31 |
| `[sql-query]` | floor | BUG-287 | Same `pyarrow>=12.0.0` declaration as `[arrow]`; `sqlalchemy>=2.0.31` resolves and imports cleanly. | 2026-12-31 |
| `[s3-pyarrow]` | floor | BUG-287 | Same cause one minor up: `pyarrow>=14.0.0` against a current `numpy`. `s3fs>=2024.2.0` resolves and imports cleanly. | 2026-12-31 |
| `[azure]` | floor | BUG-288 | `aiohttp>=3.0` names a release that installs and cannot be imported on any interpreter this package supports (`cannot import name 'Mapping' from 'collections'`). The bound was taken from `azure-core`'s own metadata and never exercised. | 2026-12-31 |
| `[sftp]` | floor | BUG-289 | `paramiko==3.1.0` reaches `algorithms.TripleDES`, which current `cryptography` answers with a deprecation warning; the suite rejects warnings, so collection fails. A user at that floor sees a warning, not a failure — the floor is a candidate for raising rather than broken today. | 2026-12-31 |
| `[s3]` | floor | BUG-289 | `s3fs==2024.2.0` leaves unraisable exceptions in teardown against a current `aiobotocore`; pytest's unraisable plugin turns them into 16 errors. Same class as `[sftp]` above: warnings, not breakage. | 2026-12-31 |
| `[sql]` | newest | BUG-281 | `_SQLAlchemyBaseBackend` lets SQLAlchemy pick the pool class from a `mode=memory` URL, which 2.1.0rc1 deprecates; the suite turns warnings into errors, so one `tests/backends/sqlblob/` case fails against the drifted resolution. Pre-existing and not a regression from any bump. | 2026-12-31 |
