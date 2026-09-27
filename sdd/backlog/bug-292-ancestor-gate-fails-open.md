# BUG-292 — The file-ancestor gate fails open on every `SQLAlchemyError`, so it degrades to a no-op without a signal
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`_head_one` in `_SQLAlchemyBaseBackend._maybe_check_no_file_ancestor`
(`src/remote_store/backends/_sqlalchemy.py`) wraps its probe in
`except (sa.exc.SQLAlchemyError, OSError): return False`. `False` means "no
ancestor here", so **any** database error the probe meets is read as permission
to proceed. The gate does not weaken, it disappears, and nothing says so — no
log line, no counter, no exception.
The fail-open is deliberate and documented: a transient probe error should not
roll back the caller's `move`/`copy` nor turn a best-effort gate into a hard
failure (`_flat_ns.py` § "Fail-open `head_one`"). What is undefended is the
distance between *transient* and *any*.
**Measured, not hypothesised.** BUG-281's second review round produced a live
instance: under a `mode=memory&cache=shared` URL on a pooled engine, the nested
`connect()` the walk opens inside `move`'s open write transaction read a table
the outer transaction held a write lock on and raised
`sqlite3.OperationalError: database table is locked: remote_store_objects`.
`_head_one` swallowed it and `move("a.txt", "folder/b.txt", overwrite=True)`
**succeeded** where it must raise `InvalidPath`, with `folder` a regular file.
That specific cause is closed — the pool no longer moves — but the cause was
incidental. A schema change, a pool exhaustion, a dropped connection or a
permission error would each produce the same silence, on any backend sharing
this walk.
**A second cause reaches the same silence and no error-handling change fixes
it.** BUG-281's third review round measured `move("a.txt", "folder/b.txt",
overwrite=True)` returning instead of raising `InvalidPath` on
`sqlite:///file::memory:?uri=true` — an anonymous in-memory database on
`QueuePool`, where the walk's nested checkout is a distinct connection onto a
distinct, *empty* database (SQL-BLOB-072). Nothing raises there: `_head_one`
answers `False` correctly, about the wrong database. The walk is the one path
that holds two checkouts at once, which is why it is where that row bites
first. Untouched by BUG-281 and out of its scope, but it bounds this item's
fix shapes: all three above narrow or report *errors*, and none of them would
make this instance raise.
Fix shape is open and is a contract decision rather than a patch, which is why
this is filed rather than fixed in BUG-281's PR. At least three are available
and they differ in what they promise: narrow the caught set so a lock error
propagates while a transient drop still fails open; keep the fail-open and emit
a `logging.warning` so the degradation is observable; or give the gate a strict
mode where a probe error raises. The second is the smallest and the first is
the one that matches what a reader takes "reject writes under a file ancestor"
to mean. Whichever lands, BE-008's promise needs a sentence on what the gate
does when it cannot see.
**Scope is the walk, not the SQL backend: five `_head_one` closures share the
shape**, one per flat-namespace implementation, each catching its own driver's
family plus `OSError` (`rg -n 'def _head_one' -A 22 src/remote_store`):
`_s3_base.py:161` and `_s3_boto3.py:1235` catch
`(ClientError, BotoCoreError, OSError)`, `_azure.py:324` and
`aio/_azure.py:185` catch `(AzureError, OSError)`, and `_sqlalchemy.py:421`
catches `(SQLAlchemyError, OSError)`. `_flat_ns.py` § "Fail-open `head_one`"
is the cross-backend contract all five cite, so it is the artifact the
decision lands in; a fix scoped to one closure leaves four saying otherwise.
The two Azure sites are the least exposed and show the available shape: they
take `ResourceNotFoundError` in its own arm before the broad one, so a genuine
404 is distinguishable from a failure. The S3 pair do not — a 403 arrives as a
`ClientError` like a 404 and is read as "no ancestor".
