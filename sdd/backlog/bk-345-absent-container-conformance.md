# BK-345 — BE-021's absent-container rule has no registry-driven gate, so a new backend is silently exempt
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

The rule binds every backend that can delete and whose container can be
absent, and it is verified by six hand-written per-backend suites
(`tests/backends/{s3,azure,azure/aio,sqlblob,sftp,local,graph/aio}/`).
`tests/backends/conformance/` gained nothing, so a seventh such backend
inherits no cell and passes CI without ever meeting the clause.
This is not hypothetical. `GraphBackend` went unexamined through six review
rounds of the change that wrote the rule (BUG-243) and turned out to contradict
it — BUG-248, since closed. A registry-driven cell would have failed on the
first run, and would also have shown the contradiction's real width: BUG-248
was filed as reaching two operations and measured at eleven.
The repo already has the shape for this: [`sdd/TESTING.md`](../TESTING.md)
Rule 13 § "Declaring an exemption" — a self-pruning exemption list where
silence is not consent. The work is a conformance cell parametrised over the
backend registry, plus an explicit exemption entry for the four backends BE-021
names as out of scope (`MemoryBackend` and `AsyncMemoryBackend`, whose
container is an in-process dict; `SQLQueryBackend` and `ReadOnlyHttpBackend`,
which do not declare `DELETE`).
**Depends on ID-244 for the mechanism.** The other dependency, BUG-248 for the
exemption list, is discharged: `GraphBackend` meets the clause on every
operation BE-021 decides, so it is a plain cell rather than an exemption, and
the two *backend operations* that keep Graph's drive-identity escalation
(`write`, `check_health`) are outside what the clause states — as are its two
non-operation callers, drive-id resolution and the copy/move monitor poller,
which a per-backend conformance cell does not reach at all. See
[ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md).
An absent container is not a state most conformance fixtures can reach: the S3
and Azure lanes need a stub that 404s at container level (BUG-243 built those),
SQLBlob needs a dropped table, Local needs its root deleted, and Graph needs a
respx route. That is the same per-fixture arrangement hook ID-244 has to decide
where to bind, so this item consumes that decision rather than making its own.
**Graph's lane cannot be a cassette**, and not by preference: cassettes are
recorded from live Graph, which answers a nonexistent drive with
`itemNotFound` (GR-031's verification note), so the drive-identity code has
never been recorded — `rg -l resourceNotFound tests/backends/cassettes/`
returns 0 files against 53 Graph cassettes carrying a `404`. The `graph_replay`
fixture therefore cannot reach the absent-container state at all, and a
hand-written cassette would fabricate a response the tier has never produced.
This is the item that makes the section's promise stay true for backend seven,
which is why it sits here and not with the coverage work.

## Moved from the § 1 preamble

Verbatim from the section preamble the pilot removed: one clause of its
`Closes when` list, which read "§ 1 closes when … [this clause]". BE-004 and
BE-005 appear only here; the body above scopes the item to BE-021.

a newly
registered backend cannot pass CI without meeting BE-004, BE-005 and BE-021
(BK-345).

## Correction (2026-10-02, BK-389 planning PR)

The work shape above, one conformance cell parametrised over the backend
registry, predates RFC-0017's kernel and is re-scoped by the maintainer's
re-homing at BK-389's split. The kernel applies BE-021 § Reach's
absent-container answers per `Op`, once, so that half is now a fake-driver
kernel cell in BK-389. What stays here is the gate that each driver's
`container_absent` recognises its own wire's absent container: per-driver
cells from D3 step 2, the first driver whose container can be absent (both
Memory drivers are exempt, as above). Until a class migrates, its
hand-written per-backend suite still carries the rule. The ID-244 dependency
stands, and BK-394 now precedes this item because it registers drivers in
the conformance registry. *Corrected 2026-10-15: BK-394 left the registry
constructing `MemoryBackend()`, so the precondition is the first PR that
registers drivers there, as ID-244's entry says.*

## Correction (2026-10-25, RFC-0025)

[RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md) D7 froze the kernel on
`frozen/kernel-driver`, BK-389's fake-driver cells and the D3 steps with it, so
the 2026-10-02 re-scope above no longer holds: the scope is again the one
conformance cell parametrised over the `Backend` registry, as first written.
ID-261, absorbed into BK-389 at that re-scope as fake-driver cells over an
absent container, is absorbed here instead: an absent-container fixture is the
one state that separates BE-029's orders
([ID-261's dossier](id-261-root-order-unobservable.md)).

## Moved out of spec 003, 2026-10-19

Verbatim from `sdd/specs/003-backend-adapter-contract.md` at master
`35ea366`, links re-based to this directory, by BK-456's first stage: the
text stated project state, which a spec does not carry
([`SPEC-DESIGN.md` Rule 7](../SPEC-DESIGN.md#no-project-state)). A dated
record, not kept current.

BE-021, the root measured against an absent container:

> **Ten of the thirteen concrete backends are measured against an absent
> container at the root and all ten meet the row; three are not measured.**
> Meeting it: `LocalBackend`, `SFTPBackend`, `MemoryBackend`,
> `AsyncMemoryBackend`, `SQLBlobBackend`, `S3Backend`, `S3PyArrowBackend`,
> `S3Boto3Backend`, `AzureBackend`, `AsyncAzureBackend`. Unmeasured:
> `GraphBackend`, `ReadOnlyHttpBackend`, `SQLQueryBackend`. Derivation of the
> thirteen: the classes declaring `CAPABILITIES`, excluding the two abstract
> bases and the sync adapter — enumerated by importing every module under
> `remote_store.backends` and `remote_store.aio.backends` and selecting classes
> with `CAPABILITIES` in their own `__dict__`.
>
> **The measurement is per-backend, and that is a stated coverage bound rather
> than a gate.** Conformance's `TestBackendRootPath` runs the row against every
> LIST-capable backend, but with the container *present*; no conformance fixture
> removes one. The backends whose container can go absent under them therefore
> pin the absent state in their own homes:
> `tests/backends/s3/test_denied_probe.py` for the three S3 lanes,
> `tests/backends/azure/test_absent_container.py` and its `aio/` sibling for the
> two Azure classes, `tests/backends/local/test_absent_root.py` for the deleted
> root, `tests/backends/sqlblob/test_absent_table.py` for the dropped table. The
> remaining three — `SFTPBackend`, `MemoryBackend`, `AsyncMemoryBackend` — have
> no container distinct from an empty store (SFTP's `base_path` is created
> lazily, so an untouched store *is* the absent case), and the conformance
> cell's unseeded arm is that measurement.
> **A fourteenth backend is therefore exempt by default at the root exactly as it
> is for the absent-container clause**, which is the gap BK-345 owns; nothing
> here closes it.
>
> The three unmeasured classes are unmeasured for different reasons, and none is
> a divergence: `ReadOnlyHttpBackend` and `SQLQueryBackend` arrange no absent
> container through the `Backend` API at all, and `GraphBackend`'s
> absent-drive answers are its own (GR-031, [ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md)).
>
> The root is absent from § Known divergences below because that list is
> organised by the absent-container *clause* and the root is BE-029's; the
> pointer is here so a reader does not read that list as deciding the root
> either way.
