# BUG-257 — `GraphBackend` restarts the first-page bound at every folder of a recursive walk
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

BE-021 § Reach requires a container 404 arriving after a listing has received a
page to propagate rather than end the iteration. `GraphBackend` keys that bound
per **HTTP request** — `_iter_child_items` in
`src/remote_store/aio/backends/_graph/backend.py` sets its `started` flag
inside one request — while `_walk_files` issues one request per folder, so
every subfolder listing starts the bound over at `False`.
Measured with `respx` against the real backend: `list_files("", recursive=True)`
where the root `/children` returns `[a.txt, sub/]` and `sub`'s `/children`
returns 404 **returns `["a.txt"]` cleanly** — a truncated listing that reads as
complete. Reproduced with both `itemNotFound` and `resourceNotFound` bodies,
which matters because listings run at item scope where `graph_error_for` maps
any 404 to `NotFound`, so a genuinely deleted drive produces this.
The control passes: page 1 followed by a 404 on the `@odata.nextLink` **does**
raise `NotFound`, so the single-listing bound is correct and only the walk is
not.
**Pre-existing, and surfaced by a spec edit rather than by a code change.**
BUG-246 wrote the first-page bound into § Reach; before that no clause decided
the mid-scan case and this was undecided behaviour rather than a breach.
BUG-248 had brought Graph to the clause's other rows in the same section, which
is why it appears on both sides of § 1's paragraph.
The fix shape is `S3Boto3Backend.list_files`, where one `_listing_errors`
cursor wraps the whole breadth-first walk so a 404 on any sub-prefix
propagates: hoist the flag out of `_iter_child_items` and thread it through
`_walk_files`. **The fix lands once**, unlike the Azure case: `GraphBackend` is
a single class and sync access goes through `AsyncBackendSyncAdapter`
([ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)), not a second copy of
the walk. Only the *cells* need a sync lane.

## Correction, 2026-09-26

"§ 1's paragraph" above was a `BACKLOG.md` § 1 preamble paragraph that counted
the classes diverging from BE-021's absent-container clause. The ADR-0040 § 1
pilot removed it, because the list it mirrored is authoritative where it lives:
BE-021 § Known divergences in
[`specs/003-backend-adapter-contract.md`](../specs/003-backend-adapter-contract.md).
