# BUG-245 — `SQLBlobBackend(create_table=False)` leaks `NoSuchTableError` from its constructor
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Reflection is unguarded: `sa.Table(name, meta, autoload_with=engine)` against an
absent table raises `sqlalchemy.exc.NoSuchTableError`, which reaches the caller
unmapped. Every other backend's constructor rejects bad configuration with
`ValueError` (`validate_azure_params`, the S3 bucket check), so a caller
wrapping construction in `except (RemoteStoreError, ValueError)` catches
every backend but this one — and the escaping type is a SQLAlchemy import the
caller may not have.
Reproduction: `SQLBlobBackend(engine=sa.create_engine("sqlite:///:memory:"),
table_name="nope", create_table=False)`.
BE-021's "backend-native exceptions never leak" is scoped to operations, so
this is a gap in the contract as much as in the code: decide whether
construction is in scope for the mapping rule, then map it. Note the behaviour
itself is right — refusing to bind to an absent table is a sound thing to do,
and is pinned by `tests/backends/sqlblob/test_absent_table.py`; only the error
type is wrong.
