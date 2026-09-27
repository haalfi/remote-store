# BK-381 — `check_backend_order` never tests an enumeration naming fewer than six backends
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Both of the gate's scanners discard a segment as prose before ordering is
tested when `_distinct(found)` is below `_MIN_BACKENDS`, which is 6. So **any**
enumeration naming fewer than six distinct backends is invisible to it,
ordered or not — including our own conda recipe `about` summary, which names
four. Measured by importing the module: `backends_in("Local, S3, SFTP, Azure")`
returns those four and `is_ordered(...)` is **`False`**, yet the gate is green,
because `_distinct` is 4 against `_MIN_BACKENDS` 6.
Split from BK-370, which closed the other half of that exposure: the conda
feedstock can no longer drift from our recipe, because the copy is generated
and the published one is watched. **Our recipe can still drift from the
README**, and this is what would notice.
Fix shape is the item's cost: lifting `_MIN_BACKENDS` widens the gate to every
enumeration in the repository at once, so the work is a per-surface membership
opt-in rather than a constant change — and membership itself is a judgement
[`CONTRIBUTING.md` § Adding a New Backend](../../CONTRIBUTING.md#adding-a-new-backend)
deliberately declines to make, since the API reference splits its tables and
the README abridges on purpose. Whatever lands has to say which surfaces are
held to membership and which only to order.
