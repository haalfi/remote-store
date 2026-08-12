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

**Eleven** of the operations in those rows are ones BE-021 names verbatim,
counting the `move` source and the `copy` source separately as the clause does
and each delete once per `missing_ok` value: 4 deletes + `read` + `get_file_info`
+ `get_folder_info` + `move` src + `copy` src + `list_files` + `list_folders`.
`read_bytes` and `iter_children` diverged too, as unnamed siblings of named ones,
for 13 in all — 13 + 3 complying probes + `write` accounts for the 17 run. Under
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
is silent about.** Graph classifies a `404` by four scopes:

- **Item scope** — the path-addressed data plane. A `404` is `NotFound` whatever
  its `error.code`.
- **Identity scope** — `resourceNotFound` stays `BackendUnavailable`; any other
  `404` is `NotFound`. It holds `write` — the single roster operation BE-021
  § Reach declines to decide — plus three callers BE-021's roster never reached:
  `check_health`, drive-id resolution, and the copy/move monitor poller.
- **Drive scope** — the bare `/drives/{drive_id}` resource: any `404` is
  `BackendUnavailable`. No call site passes it.
- **Probe scope** — unchanged: every `404` is suppressed to `False`.

**A sibling takes the scope of the operation it delegates to**, not the scope its
own name would suggest — `read_bytes` with `read`, `iter_children` with the
listings — whether or not BE-021 names it.

**The rule is published with its enumeration, not alone.** GR-031 carries a
call-site-to-scope table covering every site, and `tests/backends/graph/aio/test_utils.py`
derives the resolver's row from that module's own call sites rather than a list.

## Consequences

`write` becomes the operation that tells a dead store from a missing file. It is
what a caller runs first against a freshly configured store, so a misconfigured
drive still surfaces as a configuration error rather than as "your file isn't
there" — the failure GR-031 was written to prevent — while every operation the
contract *does* decide answers portably.

**The membership rule had to be stated as delegation because the obvious
phrasing is wrong.** "Identity scope holds what BE-021 does not name" would send
exactly the two operations the eleven-operation measurement surfaced as unnamed —
`read_bytes` and `iter_children` — into identity scope, reintroducing the
escalation on a path BE-021 governs.

**The enumeration is there because arguing the criterion did not converge.**
Three successive review rounds each found a call site on the wrong side of this
rule, by a different route: `resolve_drive_id`'s lookups, then a fifth leg
reaching the classifier through `iter_pages` rather than `graph_send`, then the
monitor poller. Each was right about the site in front of it; none was
exhaustive. A hand-written table cannot catch a site it does not list, which is
why the resolver's row is derived from the source instead — verified by adding a
sixth leg and watching a named cell fail.

**Drive scope is a definition, not a live half of the compromise.** It had no
call site before this change either — the fact is already registered against the
change that introduced the probe scope — because every drive-addressed lookup
either resolves an id, which is identity scope, or goes through
`/drives/{id}/root`, which is path-shaped. It stands as the table's statement of
what a bare drive `404` means, reached only by the table's own tests. So what
GR-031 actually keeps is the four identity-scope groups. **Probe scope** is
likewise retained rather than folded into item scope, which it now answers
identically: it pins BE-004 / BE-005 independently of the rest of the table, so a
future renarrowing at item scope cannot reach the probes.

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
fails as a configuration error, before any operation runs.

Two things bound the remaining cost, and a third recipe needs a qualifier. A
`write` still escalates, and `check_health` still escalates — both unconditionally.
GR-031 also documents a drive-root probe, `exists("")`, and that one is sound
**only when no `base_path` is configured**: `native_path("")` prepends it, so on a
scoped store the probe addresses the `base_path` folder and `False` then means
"drive gone or `base_path` missing". That is the very ambiguity PING-011 was
amended in this change to keep out of `check_health`, so the recipe list is
`write` and `check_health` first, `exists("")` only on an unscoped store.

Otherwise it is the same answer every other backend gives for an absent
container, which is the point.

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
