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

Not ground, by RFC-0024 § R1: PR #1173's key model until the key spec is
accepted, and spec 054 of PR #1171. Nor is `research-store-model-axioms.md`,
spec 051's rationale: the hook admits whole files, and its § 10 records 0.33
and kernel design (error names, flat-store encodings) that reached the first
`/observe` session's decisions.

## Pointer edits

A cross-spec pointer in a ground spec's non-normative paragraph (its Layering
or Tested against) changes without a reopen, since it changes no ground
([RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md) D3). Each such edit:

| Artifact | Paragraph | Edit | By |
|---|---|---|---|
| `sdd/specs/051-store-tree.md` | Layering | Dropped the sentence naming spec 053's BE-032 as the tree's encoding, which left master | RFC-0025 PR 2 |

## Retired IDs

When D7 deletes a spec 001 to 050 file with no live section left, its IDs map
here to their successors (RFC-0024 § R4). A spec file
[RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md) freezes leaves master too,
and its IDs retire here with no successor. No ID changes meaning.

| Old ID | Successor |
|---|---|
| BE-030 | — (frozen on frozen/kernel-driver, RFC-0025) |
| BE-031 | — (frozen on frozen/kernel-driver, RFC-0025) |
| BE-032 | — (frozen on frozen/kernel-driver, RFC-0025) |
| BE-033 | — (frozen on frozen/kernel-driver, RFC-0025) |
