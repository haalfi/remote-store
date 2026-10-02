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

## Correction (2026-10-01), and as landed

**The oracle premise above was half-true by the time the item was worked.**
BK-388 made the Dafny refinements check `AddressesRoot` on the raw string in
`Write`, `Move` and `Copy`. Re-measured before relying on it, with a throwaway
conformance-fixture harness over the six spellings, every write op, both
overwrite modes and the `move`/`copy` destination (852 rows, 14 Stage-1 lanes,
sync and async): the oracle *did* pass `"./"` to the model unnormalised, and the
model refused it with `InvalidPath("./")`. What was missing was certification,
not the refusal: `"./"` and `"/"` sit outside every method's
`requires WellFormedPath`, so the answer was observed, not proved. Every other
measured lane named the raw spelling; both oracle lanes named `"."` for `""`.

**The prescription "`assert exc.value.path == root`" was not adopted.** It fails
both oracle lanes for `""` today. BE-029 asks for an error naming the root, so
the cells accept any root spelling.

**As landed:** `MemoryBackend.dfy` includes `RootPath.dfy`, so §5's `WriteKey`,
`MoveKey` and `CopyKey` compile into the oracle, and the adapter routes write
keys and destinations through them. Every root spelling now reaches the class
folded onto Root, and the oracle names `"."`. Widened cells, measured with
`_flat_ns._reject_root_as_write_target` narrowed to `is_root` in-session and
`pytest tests/backends/conformance/test_io.py tests/backends/conformance/test_async_extended.py
-k "test_write_to_root_is_refused or test_root_as_move_or_copy_destination or
test_root_destination_outranks"` on the Stage-1 no-Docker lanes: 62 failed /
570 passed / 256 skipped (unmutated: 648 passed / 240 skipped), none failing
with an `empty` or `dot` id. Not reached here (no Docker): the azurite,
sftp_docker and MinIO lanes, which route through that shared guard. On the
Azure replay lanes the mutation shows as skips, not failures (ID-262).
