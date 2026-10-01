# ID-247 — Record the Graph root-path cassettes
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

**30** `TestBackendRootPath` cells still skip on `graph_replay` for want of a
recording — the "pinned nowhere" column of spec 003's BE-029 table. Graph is
the only HTTP family with **no emulator tier** (`graph_live` Stage 3 and
`graph_replay` Stage 1, nothing between), so those contracts are unexercised
against `GraphBackend` at every stage below a live account; Azure's equivalent
skips are covered by `azurite` at Stage 2.
The 30 is re-derived by `pytest -k TestBackendRootPath -rs`, summing the skip
reasons naming `cassettes/graph`. Twelve of the 30 are the rosters BUG-259
added — `test_write_to_root_is_refused_and_the_store_survives` at 2 ops × 2
overwrite modes × 2 root spellings, and
`test_root_as_move_or_copy_destination_is_refused` at 2 ops × 2 spellings —
both seeding through `write` and so skipping on the same terms, leaving **18**
that predate it. The item previously said 22, which the 30 does not reproduce
(18 + 12); the 22 is superseded rather than reconciled. Section 2's "Closes
when" cites this figure and was updated with it — a superseded number is only
harmless once nothing reads it, and checking that is part of superseding it.
**The old "14 of the 22 are Graph-only" split is not re-derived here** —
the new cells skip on the Azure replay lanes too, so the split did not simply
move with the total, and separating it needs a per-node comparison of the graph
and azure lanes rather than a count of skip reasons. Left for this item's own
work rather than guessed at.
`python scripts/record_cassettes.py --backend graph` needs `RS_TEST_LIVE_GRAPH=1`
plus `GRAPH_CLIENT_ID` / `GRAPH_TENANT_ID` / `GRAPH_DRIVE_ID` (device-code, so
interactive). Prefer `--node` per cell: a full run re-records all 119 existing
graph cassettes, churning their volatile headers into an unreviewable diff
against TEST-009. Any op that raises before issuing a request records nothing
and needs nothing: since ID-241 such a cell runs on replay without a cassette.
`pytest tests/backends/conformance -k "graph_replay and TestBackendRootPath"`
passes 8 of them (the `move`/`copy` source cells and BK-388's root-destination
cell), beside the 30 skips.

## Correction, 2026-09-27

"Section 2's 'Closes when' cites this figure" was already false when this body
moved: `8e35697` (BUG-281) replaced "ID-247's 30 root-path cells" in that
field with a clause carrying no figure, and the ADR-0040 § 2 conversion then
removed the field. Nothing outside this item reads the figure. The 30 itself
re-derives: `pytest tests/backends/conformance -k TestBackendRootPath -rs`
prints 30 skip lines naming `cassettes/graph`.

## Correction, 2026-10-01

ID-251 widened the write and `move`/`copy` destination cells from two root
spellings to six, so both figures moved. `pytest tests/backends/conformance -k
"TestBackendRootPath and graph_replay" -rs` now reports 16 passed and 54
skipped, every skip naming `cassettes/graph`. The 24 new skips are the writer
cell (2 ops × 2 overwrite modes × 4 new spellings) and the seeded destination
cell (2 ops × 4); the 8 new passes are the unseeded root-destination cell
(2 ops × 4), which refuses before a request.
