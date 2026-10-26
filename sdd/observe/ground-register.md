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
| `sdd/specs/052-store-key.md` | key | active |
| `sdd/specs/profiles/052-store-key.md` | key | active |
| `sdd/formal/lean/KeyModel.lean` | key | active |
| `sdd/specs/053-store-operations.md` | catalogue | active |
| `sdd/observe/catalogue.md` | catalogue | active |

Not ground: `research-store-model-axioms.md`, spec 051's rationale, and
`research-key-model.md`, spec 052's. The hook admits whole files, and both
record 0.33 and kernel design: the first in its § 10 (error names, flat-store
encodings), which reached the first `/observe` session's decisions; the second
in § 3.7's error table and § 9's comparison with specs 004, 005, 015 and 053.
Nor is BK-493's dossier, which maps each catalogue entry to 0.33's surface, or
the catalogue's deep-research doc, whose per-entry notes would prime every
other entry's session ([RFC-0026](../rfcs/rfc-0026-operation-catalogue.md) C4).

## Pointer edits

A cross-spec pointer in a ground spec's non-normative paragraph (its Layering
or Tested against) changes without a reopen, since it changes no ground
([RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md) D3). Each such edit:

| Artifact | Paragraph | Edit | By |
|---|---|---|---|
| `sdd/specs/051-store-tree.md` | Layering | Dropped the sentence naming spec 053's BE-032 as the tree's encoding, which left master | RFC-0025 PR 2 |
| `sdd/specs/051-store-tree.md` | Layering | Input strings point at spec 052, the store key, instead of spec 004, whose PATH-002 to PATH-008 it supersedes | RFC-0025 PR 3 |

## Spec numbering

Spec 052 is the store key from PR #1171's merge onward. A record committed
before that merge which cites "spec 052" or "spec 053" means the spec frozen on
`frozen/kernel-driver` (backend lifetime, contract kernel), and one that cites
"spec 054" means the store key; such records are not edited
([RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md) D6).

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
