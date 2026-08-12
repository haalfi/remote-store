# ADR-0038: An Absent Container Reads as Absence, Except Where the Contract Is Silent

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

Two clauses of this repository's own specs gave opposite answers for the same
call, both written deliberately, neither implementation wrong under its own.

[BE-021](../specs/003-backend-adapter-contract.md#be-021-error-mapping)
§ "An absent container reads as an absent path" holds that the bucket, container
or table holding a path is part of that path's existence: a container that is not
there holds no path either. It binds every backend with no carve-out, and its
§ Reach paragraph states what each operation answers — a clean return from the
tolerant deletes, `NotFound` from the strict ones and from the reads, an empty
listing from the listings, `False` from the probes.

[GR-031](../specs/044-graph-backend.md#gr-031-404-discrimination-item-vs-drive)
held that a `404` carrying `error.code == "resourceNotFound"` — Graph's
drive-identity code, honoured regardless of the failing URL's scope because every
item-by-path URL embeds the drive — maps to `BackendUnavailable` for every
error-raising operation: a deleted or misconfigured drive is a backend identity
failure, not a per-item condition, and silently returning from a delete against a
store the caller cannot reach hides a configuration error behind a success.

`GraphBackend`'s drive is a container, so the two clauses meet.

### The collision was recorded as two operations wide and is eleven

BUG-248, BE-021's own divergence list, GR-031's conflict paragraph and the
pinning test `tests/backends/graph/aio/test_absent_drive.py` all stated that only
the two tolerant deletes disagreed. Running every operation against an absent
drive refuted that. Derivation: a respx catch-all `404` on every
`https://graph.microsoft.com/v1.0/drives/*` URL against `GraphBackend`, 17
operations × both error codes. Under `404 resourceNotFound` **every**
error-raising operation answered `BackendUnavailable`:

| Operation | BE-021 requires | Answered before this ADR |
|---|---|---|
| `delete` / `delete_folder` (`missing_ok=True`) | clean return | `BackendUnavailable` |
| `delete` / `delete_folder` (`missing_ok=False`) | `NotFound` | `BackendUnavailable` |
| `read`, `get_file_info`, `get_folder_info`, `move`/`copy` source | `NotFound` | `BackendUnavailable` |
| `list_files`, `list_folders` | empty listing | `BackendUnavailable` |
| `write` | *undecided — BE-021 § Reach declines it* | `BackendUnavailable` |
| `exists`, `is_file`, `is_folder` | `False` | `False` — complied |

Eleven of those rows are operations BE-021 names verbatim; `read_bytes` and
`iter_children` diverged too as unnamed siblings of named ones. Under
`404 itemNotFound` every row already complied, which is why the width stayed
hidden: live consumer OneDrive returns `itemNotFound` for a nonexistent drive on
both URL forms (GR-031's verification note), so the escalation has never been
observed to fire on the tier the live suite covers.

That reframes the choice. "Two clauses disagree about two calls" invites a
carve-out; a carve-out eleven operations wide would not narrow BE-021 on Graph,
it would void it there — and section 1 of the backlog promises that "an absent or
denied store answers the same way on every backend".

## Decision

**BE-021 wins on every operation it decides. GR-031 keeps the operations BE-021
is silent about.** A `404` is classified by what its URL addresses and what the
contract says about the operation, in three cases:

- **Item scope** — the backend's path-addressed data-plane operations. A `404` is
  `NotFound` whatever its `error.code`, which is what makes the tolerant deletes
  tolerate an absent drive and the strict ones report it as absence.
- **Identity scope** — `resourceNotFound` is `BackendUnavailable`, any other
  `404` is `NotFound`. Three groups of caller, and the reason differs between
  them, which is why this is stated as a rule and not as one test:
  - `write`, both the small `PUT /content` and the `createUploadSession` halves.
    It is the single path-addressed operation BE-021 § Reach explicitly declines
    to decide, so Graph decides it.
  - `check_health` (PING-011), which reports reachability rather than addressing
    a path.
  - `GraphUtils.resolve_drive_id`'s lookups (GR-057), which resolve a drive
    before any backend exists.
- **Drive scope** — the bare `/drives/{drive_id}` resource. Any `404` is
  `BackendUnavailable`. No path is being addressed, so there is no absence for
  BE-021 to describe.

**Membership in item scope is not "BE-021 names this operation".** A sibling that
delegates to a named operation belongs where that operation belongs — `read_bytes`
to `read`, `iter_children` to the listings — whether or not the clause spells it
out. Stated the other way round, the rule would send exactly the two operations
§ Context's eleven-operation measurement surfaced as unnamed into identity scope,
reintroducing the escalation on a path BE-021 governs.

The probe scope is unchanged and keeps its own value even though it now answers
exactly as item scope does: it pins BE-004 / BE-005 independently of the rest of
the table, so a future renarrowing at item scope cannot reach the probes.

**Drive scope has no call site**, and did not have one before this change either
— the fact is already registered against the change that introduced the probe
scope. Every drive-addressed lookup either resolves an id, which is identity
scope, or goes through `/drives/{id}/root`, which is path-shaped. It is retained
as the table's statement of what a bare drive `404` means, and only the table's
own tests reach it. So the escalation this ADR actually leaves GR-031 is the
three identity-scope groups; the drive row is a definition, not a live half of
the compromise.

`write` is the load-bearing half of the compromise. It is the operation a caller
runs first against a freshly configured store, so a misconfigured drive still
surfaces as a configuration error rather than as "your file isn't there" — the
failure GR-031 was written to prevent — while every operation the contract *does*
decide answers portably.

## Consequences

The mapping costs nothing: the deletes' determinant `GET` already ran, so both
halves of BE-021's rule — clean return under `missing_ok=True`, `NotFound` under
`missing_ok=False` — fall out at zero extra round trips, satisfying that clause's
"free on the miss path" budget.

**What was traded away.** On a SharePoint-backed drive — outside the live tier's
coverage, and the tier where `resourceNotFound` may actually fire — a
misconfigured drive now reads as `NotFound` from a read and `False` from a probe
rather than as `BackendUnavailable`. Drive resolution is unaffected, because
`resolve_drive_id` moved to identity scope in the same change rather than
inheriting the flattening: a store whose drive cannot be resolved at all still
fails as a configuration error, before any operation runs. Three things bound the
remaining cost: a `write`
still escalates, `check_health` still escalates, and GR-031 already documents the
caller-side recipe (`exists("")` on the drive root, which answers `False` when the
drive itself is unreachable). It is the same answer every other backend gives for
an absent container, which is the point.

**The Dafny layer was considered and cannot help here.** It is the repo's
machine-checked interlock for exactly this class of question — "no two stated
properties contradict each other" — so declining it is worth recording rather
than passing over. Three findings against: `sdd/formal/BackendContract.dfy` models
the filesystem as `map<Path, Entry>`, which has no container that could be
absent; `BackendUnavailable` is declared there but carried by no postcondition in
any of the four `.dfy` files; and decisively, Dafny models the *abstract trait*
while this collision is an abstract clause against a backend-specific one —
`sdd/formal/README.md` § "Three shapes of Dafny-section work" already places
per-backend divergence outside the Dafny track. Extending the model could have
pinned the winner after the fact; it could never have surfaced the contradiction.
What did surface it, both times, was running the backend: the two-operation
framing survived six review rounds of the change that wrote BE-021's clause and
was refuted in one command.
