# ID-251 — BE-029's widest clause is one the conformance suite cannot fail on
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

BE-029 requires the write guard to refuse **every spelling that addresses the
root**, and says outright that a backend implementing it as `if is_root(path)`
is not conformant. The conformance cells cannot detect that: `_ROOT_WRITE_OPS`
and `_ROOT_WRITE_DST_OPS` are parametrised over `["", "."]` only, because they
also `assert is_root(exc.value.path)`. So a backend that reimplements the guard
narrowly ships green, and the only things holding the wider rule are
`tests/backends/test_flat_ns.py` (the shared helper in isolation) plus the
Local, SFTP and Graph per-backend modules — none of which a third-party backend
runs.
**Widening the parametrisation is not a one-liner**, which is why this is an
item rather than a follow-up commit. `assert exc.value.path == root` has to
replace the `is_root` assertion, and `DafnyOracleBackend` — registered with all
capabilities bar GLOB and LAZY_READ, so bound by these cells — passes `"./"`
through to the Dafny model unnormalised. Either the oracle normalises first or
the roster carries a documented carve-out for it; that choice is the work.
Found by the closing gate of BUG-259, which introduced the clause and the cells
in the same change and so had no round in which the gap was visible as a
regression.
