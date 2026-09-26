# BUG-280 — `LocalBackend`'s three listing methods leak a raw `PermissionError`
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

BE-021 is the never-leak invariant this breaches
([003-backend-adapter-contract.md](../specs/003-backend-adapter-contract.md)),
and the spec already records BUG-249 — the S3 twin, described further down
this entry — against it.
Reproduced by constructing a `LocalBackend` on any root holding one file,
patching `pathlib.Path.iterdir` to raise
`PermissionError(13, "Permission denied")`, and calling each method:

| call | answer |
|---|---|
| `list_files` | raw `PermissionError` |
| `list_folders` | raw `PermissionError` |
| `iter_children` | raw `PermissionError` |
| `read_bytes` | mapped (never reaches `iterdir`) |
| `delete` | mapped (never reaches `iterdir`) |

A caller catching `RemoteStoreError` around a listing gets nothing, and the
exception carries no `path` or `backend`. `LocalBackend` maps this correctly
everywhere else — it catches bare `except PermissionError:` at 14 sites, 11
raising `PermissionDenied` outright — so this is three unguarded methods, not a
design position.
**Exactly the shape of [BUG-249](../BACKLOG-DONE.md)**, which fixed the same three
method names on `S3Boto3Backend` leaking a raw `botocore.ClientError`, and of
`TestSFTPBug146ListingEioRaises`, which pins the SFTP twin. The listing methods
are the repeat offender because they are generators whose body runs outside the
caller's `try`, which is the thing worth fixing once across backends rather
than a third time in isolation.
**Found by BUG-275's closing measuring member** while checking that PR's
narrowed cross-backend claim. That claim is about errno symmetry and survives
this — both errnos leak identically — so it was correctly out of that PR's
scope; `BACKLOG-DONE.md`'s BUG-275 entry records the measurement and says
plainly that the two backends are not equivalent across the whole surface.

## Moved from the § 1 preamble

Verbatim from the section preamble the pilot removed: one clause of its
`Closes when` list, which read "§ 1 closes when … [this clause]".

a listing does not leak its driver's exception on the
one backend where it still does (BUG-280)
