# Ground register

<!-- doc: repo-only -->

**Every ground artifact an `/observe` design session may read, the flow that
admitted it, and its status.** It is the one register RFC-0024 D11 names; the
design hook (`scripts/observe_ground.py`) reads its allowlist from the
`active` rows of the first table, so a row here is a file the hook lets the
session read. What may join, and when, is RFC-0024 § R1 with research § 3: only
the new layer, once its spec and formal model are accepted; 0.33's code, tests
and specs 001 to 050 never.

## Artifacts

One row per file, its path relative to the repository root. Flow is the flow
that admitted it, or `start` for the ground RFC-0024 § R1 fixes. Status is
`active`, or `reopened` while a recorded reopen decision runs its own flow; a
reopened file is not on the allowlist until its flow re-admits it.

| Artifact | Flow | Status |
|---|---|---|
| `sdd/specs/051-store-tree.md` | start | active |
| `sdd/formal/alloy/StoreAxioms.als` | start | active |
| `sdd/formal/lean/StoreAxioms.lean` | start | active |
| `sdd/formal/lean/lakefile.toml` | start | active |
| `sdd/formal/lean/lake-manifest.json` | start | active |
| `sdd/formal/lean/lean-toolchain` | start | active |
| `sdd/formal/tex/store-axioms.tex` | start | active |
| `sdd/specs/054-store-key.md` | key | active |
| `sdd/specs/profiles/054-store-key.md` | key | active |
| `sdd/formal/lean/KeyModel.lean` | key | active |

Not ground: `research-store-model-axioms.md`, spec 051's rationale, and
`research-key-model.md`, spec 054's. The hook admits whole files, and both
record 0.33 and kernel design: the first in its § 10 (error names, flat-store
encodings), which reached the first `/observe` session's decisions; the second
in § 3.7's error table and § 9's comparison with specs 004, 005, 015 and 053.

## Retired IDs

When D7 deletes a spec 001 to 050 file with no live section left, its IDs map
here to their successors (RFC-0024 § R4). No ID changes meaning.

| Old ID | Successor |
|---|---|
| — | — |
