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
