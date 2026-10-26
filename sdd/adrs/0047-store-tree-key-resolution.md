# ADR-0047: The Store Is One Tree, and Each Backend Encodes It

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Implementation frozen on `frozen/kernel-driver`
([RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md)). The decision is not
withdrawn; RFC-0024 D10 decides whether it stands.

Records the design stances of
[RFC-0021](../rfcs/rfc-0021-key-resolution-model.md) (BK-432), accepted by the
maintainer on 2026-10-13: its D1 to D4 and D8. Accepted in BK-394's PR together
with [ADR-0042](0042-contract-kernel-over-thin-drivers.md), once `MemoryBackend`
and `AsyncMemoryBackend` run on the kernel (the maintainer's decision of
2026-10-15, in PR #1127). The contract these stances produce is spec 053's
[BE-032](https://github.com/haalfi/remote-store/blob/frozen/kernel-driver/sdd/specs/053-contract-kernel.md#be-032-the-store-tree-on-the-kernel),
which this record does not restate.

It amends no record. A search of `sdd/adrs/` for `flat`, `namespace`,
`reject_write_under_file_ancestor`, `ID-211` and `RFC-0021` finds no other ADR that
decides what a key resolves to, the flat-namespace write exemption or how a
refusal is typed. BE-008's opt-in file-ancestor check, which D4 retires, was
decided in the spec under ID-211, so its retirement is spec 003's, and BE-008
already states it for the classes on the kernel.

## Context

The spec had no single statement of what a key names, and its statements
disagreed: BE-030's *What is at a key*, BE-031's probe rule for
`delete_folder`, and rows for a folder, an absent key, a key under a file and a
shadowed prefix in BE-008, BE-014, BE-017 and BE-021. The kernel mirrored the
split, with a different probe set per call family. Rounds 7 to 10 of PR #1127's
review each added a probe to one family and the next round found one nobody had
crossed, because no artifact held the question "what does a refusal of shape X
say about the key" above the families. A first draft of RFC-0021 then made
backend geometry a parameter of the model, and the model inherited every
encoding's oddities. RFC-0021 § Motivation carries the evidence.

## Decision

Section references are to RFC-0021, which carries the rationale.

- **The store is one tree** (D1), spec 051's. A Key resolves to an item, a
  folder or nothing, and every keyed operation is specified once against that.
  Rejected: keeping the per-operation rules and adding the missing driver
  obligation, which leaves two rules for one `stat` answer.
- **Each backend encodes the tree through a partial `decode`** (D2). Backends
  differ only in the properties their drivers declare, so a backend's quirk
  belongs to its encoding, and what an answer costs depends on the encoding,
  never the answer. Rejected: geometry as a parameter of the model, whose
  outcomes grew a flat `Prefix` and a `FileAndPrefix`.
- **A raw state that does not decode is not in the store** (D3). Listings omit
  it. On a flat encoding a keyed operation below an item trusts the encoding,
  a stated limit. Rejected: keeping such entries reachable by their own key,
  which puts nodes outside the tree; and checking every ancestor on every flat
  lookup, success included, for states only a foreign writer creates.
- **The library never writes a state that does not decode** (D4). A write
  below an item, or of an item over a folder, is `InvalidPath` on every
  backend; neither check stops another writer. Rejected: keeping BE-008's
  opt-in, whose default lets the library create such states. *Reverse if* the
  checks' per-write cost on flat backends outweighs a decodable store.
- **Refusals are observations of the encoding** (D8). After a refusal the
  kernel probes until the family's result is decided, and replaces the refusal
  only where the call must refuse, or with a listing's empty result. A probe
  that runs anyway fails closed; one run only because the call refused fails
  open. Drivers owe no rule on how a refusal is typed beyond two: drivers with
  links, and flat listings. Rejected: a probe set per call family, and a
  typing obligation on every driver, since a wire's ENOTDIR may arrive as any
  probed shape.

D5 to D7, D9 and D10 are contract or placement and live in BE-032.

## Consequences

- **Positive:** what a key resolves to, and what a refusal says about it, is
  answered once for every call family, so a fix reaches every family. The
  flat encoding's `decode`, its operations and the refusal rule are verified
  in `sdd/formal/StoreTree.dfy`.
- **Positive:** a driver author owes no refusal typing beyond the two rules,
  and a backend's quirks are stated in its encoding's declared properties.
- **Negative:** a flat write pays one `stat` per ancestor and one
  `list_page(limit=1)`, and a flat folder operation one `stat`; BE-032's cost
  table holds the figures.
- **Negative:** `reject_write_under_file_ancestor` loses its effect, so each
  backend retires it as it moves onto the kernel; some refusals change type,
  listed in RFC-0021 § Impact.
- **Negative:** on a flat encoding, an operation on a key below an item acts
  on whatever raw entry another tool wrote there.
- **Neutral:** flat raw keys with an empty segment (BK-438) and name equality
  other than exact (BK-436) are open; links are stated in BE-032 but not yet
  on the kernel.
