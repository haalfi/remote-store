# ID-244 — A read-only backend cannot reach any WRITE-gated contract cell
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Sibling of [ID-241](../BACKLOG-DONE.md) (shipped), and the same class: a rule
gated so no fixture ever runs it. Here the gate is the **seeding discipline** —
conformance cells that need data call `backend.write`, so they sit behind
`fixture_params(Capability.WRITE)`. Any contract that happens to live in such a
class is therefore unreachable for a read-only backend, *including contracts
that have nothing to do with writing*.
**Measured instance.** SIO-009 (laziness: a LAZY_READ backend must not return a
BytesIO-backed stream) lives in `TestStreamingConformance`, a WRITE-gated class.
`ReadOnlyHttpBackend` is the registry's **only read-only LAZY_READ declarer** —
streaming is the whole justification for its capability set, per
`tests/backends/http/test_config.py::test_capabilities_are_read_metadata_lazy` —
and it was structurally excluded from the only cells asserting that contract.
The two per-backend read tests did not compensate: both assert content and
chunking, which a pre-loaded `BytesIO` satisfies identically.
Pinned per-backend by BK-340 in `test_read_is_lazy_not_bytesio`; that is a patch
over a structural hole, exactly as `tests/backends/sqlquery/test_config.py`'s
root cells were before BK-340 registered a fixture.
**The same hole is why BK-340's own `sqlquery` fixture reaches only 77 cells.**
Its content-bearing surface — read, glob, listing with keys present — is
WRITE-gated end to end, so registering the fixture bought the
capability-independent contract and nothing else.
**This item owns the arrangement-hook decision for BK-345 too.** The fix is a
seeding indirection (a per-fixture `seed` hook the cells call instead of
`backend.write`), and *where it binds* is unmade — on the fixture, on the
helper, or as a capability-neutral rewrite of the affected classes. The answer
decides how much of the conformance suite changes, and a hook whose seeded
content cannot round-trip (SQLQueryBackend materialises result sets, so
`read(k)` never returns the bytes a seeder "wrote") constrains it further: the
hook must express *presence*, not content, or the cells that use it must not
assert content. BK-345 needs the same indirection to make a container absent,
so decide the binding once for both shapes.
