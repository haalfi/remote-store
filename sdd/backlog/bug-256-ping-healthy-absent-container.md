# BUG-256 — `ping()` reports a healthy store on three backends whose container is gone
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

PING-001's postconditions give `ping()` a `NotFound` for a "missing
bucket/container/path". Measured against an absent container:
| Backend | `check_health()` |
| --- | --- |
| S3, S3-Boto3, Azure (sync and async), Local | raises `NotFound` |
| S3-PyArrow, SQLBlob, **SQLQuery** | returns cleanly |
| ReadOnlyHttp | raises `BackendUnavailable` — wrong type, not a missing raise |

Both SQL backends inherit the same bare `SELECT 1` on
`_SQLAlchemyBaseBackend`: it verifies connectivity and never looks at the table
or the queried relation, so a dropped table and a discarded in-memory store both
read as healthy. `SQLQueryBackend` overrides nothing, which is why naming only
`SQLBlobBackend` understates it. The `S3PyArrowBackend` probe misses it for the
same reason one layer out. `ReadOnlyHttpBackend` is a fourth case of a different
kind and is listed so a fix does not stop at the three.
**Six documentation surfaces promise the behaviour** and are part of this item
rather than of BUG-246, which measured the divergence but did not create it:
`Backend.check_health` and `AsyncBackend.check_health` docstrings,
`Store.ping()`, `AsyncStore.ping()`, `docs-src/guides/health-check.md`, and
`docs-src/reference/migration.md` § v0.30.0 to v0.31.0, whose
absent-container section sends a caller to `ping()` as the replacement for the
`except` clause this release stops firing. The sixth was **five** until BUG-261
added that section; it is counted here rather than left to the grep because the
figure is the derivation ([principle 9](../../CLAUDE.md#principles)) and a fix
scoped to a stale enumeration reaches five of six surfaces. That section already
carries this item's bound in published prose — a table naming all three
backends measured above, `SQLBlobBackend` and `SQLQueryBackend` on the bare
`SELECT 1` and `S3PyArrowBackend` on a `get_file_info(bucket)` whose result
`check_health` discards (`_s3_pyarrow.py:188-190`), which is the same shape
stated without this file's shorthand, plus a statement that "is my store
there?" is unanswered on `S3PyArrowBackend` today —
so closing this item edits that table rather than discovering it. It stops at
the three: `ReadOnlyHttpBackend`'s wrong-type raise is not published anywhere,
because no migration section names that backend.
The caller this hurts is the one doing the obvious thing — using `ping()` at
startup to check the store is really there — and getting "yes" for a store that
is not. It is also the operation an absent-container caller is *sent* to by the
error-model docs, which is how this was found.
**Pre-existing**, and out of BE-021's reach: a health probe is off the roster
that clause governs, which is why the divergence lives under PING-001 rather
than in BE-021's list. Discovered while measuring BUG-246's migration advice,
which is why that advice sends callers to `write()` instead.
