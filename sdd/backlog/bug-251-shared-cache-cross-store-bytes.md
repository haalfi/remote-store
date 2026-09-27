# BUG-251 — A shared `cache_backend=` serves one store's bytes for another's
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`ext.cache` derives keys from `(operation, path)` with nothing identifying the
store, so two `Store`s at different roots sharing one `cache_backend=` collide
on any path they both hold, and the second reader gets the first store's
content. Silent wrong data, not a wrong error type.
**Reproduced**, `hatch run python` against two `LocalBackend` roots each
holding a distinct `same.txt`, sharing one `MemoryCache`:
`store_a.read_bytes("same.txt")` → `b"FROM-STORE-A"`, then
`store_b.read_bytes("same.txt")` → `b"FROM-STORE-A"`. Not Graph-specific —
identical for two S3 buckets or two Azure containers.
Filed from audit-016 L8, which diagnosed it as an aside to ID-123's
key-derivation work. It is not an aside: it needs no `CompositeStore`, it is
reachable on shipped code, and leaving it inside an idea that may legitimately
close as "declined" would retire a data-correctness defect with it.
**Fix shape is open and belongs with ID-121's design**, which is where
identity-derived keys are being decided: the narrow fix is to mix the backend
identity into the key, the wide one is the `ResolutionPlan`-derived scheme
ID-121 carries. Opt-in surface, so no contract risk either way — but decide
whether an unkeyed shared cache should raise rather than silently collide.
**Test shape:** two stores at different roots, one shared cache, same relative
path, assert each reads its own bytes.
