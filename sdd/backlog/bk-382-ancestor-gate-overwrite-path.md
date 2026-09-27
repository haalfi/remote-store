# BK-382 — The file-ancestor gate ships unexercised on the overwrite path, where the pre-check runs inside an open write transaction
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`test_destination_under_file_ancestor_raises_invalid_path` seeds a blocker and
a source and then moves onto `blocker.txt/dst.txt`, which **does not exist**.
So `dst_exists` is `False`, the `DELETE` branch never runs, and the ancestor
pre-check is never reached with an uncommitted write held open — the one state
the production path is in whenever `overwrite=True` meets an existing
destination. Every other cell that touches the gate has the same shape.
**Measured against a live regression, not reasoned about.** BUG-281's round 2
introduced a pool change that made this exact path silently stop rejecting. I
added a `sqlblob_shared_cache_strict` fixture and ran the whole conformance
suite against it with that regression reintroduced: **58 passed, 0 failed.**
The fixture alone catches nothing, because the suite never reaches the state.
Adding an overwrite-path variant does catch it, and discriminates: with the
regression in, `[move-sqlblob_shared_cache_strict]` and its `copy` twin fail
on `DID NOT RAISE InvalidPath`; with the pool correct, both pass.
**The obstacle is the seeding, and it is why this is an item.** Reaching the
state needs a destination that exists *under a file ancestor*, which means
writing the child first and the blocker second — legal only where a file and a
prefix may share a name. Run across the strict roster, that seeding raised on
five of the other fixtures: `memory`, `local`, `sftp_inproc`,
`sftp_chroot_inproc` and `dafny_oracle` all rejected the blocker write with
`InvalidPath` (hierarchical backends cannot have both), and `s3_moto_strict`
raised `AlreadyExists`. So the cell needs either a flat-NS gate the registry
does not currently express, or per-backend seeding — which is the thing
conformance tests exist to avoid, and the decision this item carries.
The `sqlblob_shared_cache_strict` fixture itself is cheap and independently
useful: 8 lines in `fixtures.toml`, a unique database name per `factory()` call
in `sqlblob.py`, and one entry in `_MODULE_FOR`. It lands in 10 existing
conformance cells with no new test code, and it is the only fixture that would
exercise a shared-cache in-memory database anywhere in the suite.
Scoped to the gate's *class*, not to SQLBlob: the same blind spot covers
`[s3]`, `[s3-boto3]`, `[s3-pyarrow]` and `[azure]`, whose strict fixtures run
the same cells. BUG-292 is the related decision one layer down — the walk fails
open on any driver error, which is *why* the regression was silent rather than
loud; if that closes first, this cell becomes a much stronger check.
