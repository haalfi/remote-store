# BUG-255 — A container deleted mid-listing truncates the listing silently on the two s3fs lanes
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`ListObjectsV2` answers an absent prefix with `200 KeyCount=0`, so the only 404
a listing can raise is the container's — which is why reading that 404 as "the
container is absent, so it holds nothing" is safe on the *first* page. It is not
safe on the second: by then the listing has already yielded items, so the
container demonstrably existed, and a 404 means it was deleted underneath the
scan. Measured with a stub serving a valid first page carrying a
`NextContinuationToken` and `NoSuchBucket` on the second:
| Backend | `list_files("", recursive=True)` |
| --- | --- |
| S3, S3-PyArrow | yields 0 items, then returns cleanly |
| S3-Boto3, Azure, Async Azure | raises `NotFound` after the first page — fixed by BUG-246 |

Measured for `list_files` on a page of keys; re-measured for all five listings
on both page shapes (keys-only and prefixes-only) once the bound moved onto the
page, which is the parametrisation
`TestTheAbsentBucketToleranceIsBoundedToTheFirstPage` and its two Azure twins
now carry.
The two s3fs lanes report a *complete* listing that is not complete — the other
three rows are the control, and are what the fix looks like. The caller most hurt
is the one doing list-then-delete or list-then-sync: it sees a short list, treats
the absent entries as absent, and deletes or fails to copy data that was there.
**Pre-existing on the two s3fs lanes**, which is what makes this an item rather
than a BUG-249 residue: they truncated this way before that change and still do.
**The two s3fs lanes are what this item is left holding.** BUG-246
and BUG-249 briefly put `S3Boto3Backend` and both Azure adapters onto this
truncation — the boto3 lane by replacing a leaked `ClientError` with a
swallowed 404, the Azure adapters by adding a swallow where the flat lane
previously raised — and then bounded the tolerance to the first page on all
three. The bound is keyed on a **page** having come back, which is the second
thing that PR got wrong and had to re-measure: keyed on a yielded *item*, as it
first shipped, every listing stayed blind on the page shapes its own filter
empties, so a folders-only first page still truncated `list_files` and a
keys-only one still truncated `list_folders`. **Four** of the five listings per
lane were blind — `list_files`, `list_files-recursive`, `list_folders` and
`glob`, measured by putting the item-keyed source back under the current tests
and counting failures (12, across the three lanes); `iter_children` yields both
kinds and so has no blind page shape, which is why it is the control. The Azure
HNS branches carry the bound too, and are executed: an ADLS Gen2 `List Path`
wire stub reaches all ten of them without Docker, which retired the claim that
only the Docker-gated fixture could. SQLBlob is not affected (one `SELECT`, no
pages).
**A correction worth keeping**, because it cost a round: that PR first recorded
the Azure rows as pre-existing, on the strength of a base-versus-head
measurement that was broken — the base run set `PYTHONPATH` to a worktree root,
and this package lives under `src/`, so the import silently fell back to the
editable install and measured *head* twice. Re-run with `PYTHONPATH` pointing
at `<worktree>/src` and the module's `__file__` printed, the base revision
raises. The lesson is the repo's own: a verification that can fail silently is
worse than none.
The fix shape is settled and already implemented on the other three lanes: a
first-page bound — tolerate the container 404 only while nothing has been
yielded, and let a later one propagate. `_flat_ns._ListingCursor` is the shared
piece; `S3Boto3Backend._listing_errors` is the worked example. What remains is
applying it to `_S3Base`'s s3fs-backed listings and pinning it per lane, which
closes the divergence rather than opening one. Take the bound from the worked
example rather than from this paragraph's first sentence: it is keyed on a page
having come back, not on an item having been yielded.
