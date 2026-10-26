# ID-272 — Backend breadth: Apache OpenDAL as a transport under remote-store's contract layer
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and advisory
prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Framing (maintainer, 2026-10-26)

**OpenDAL is a transport layer; remote-store is a contract layer.** OpenDAL
answers *whether* a service can do an operation. remote-store answers *how* that
operation behaves (consistency, atomicity, cost, errors, write-result
provenance) and checks it with conformance. The work keeps that wording in its
spike report, its RFC and any user-facing positioning page. The goal is breadth
in backends: every OpenDAL service a candidate driver, without giving up the
contract.

## Gate

Class P under [RFC-0024](../rfcs/rfc-0024-spec-first-reset.md) § R3: paused
until kernel and driver work resumes (RFC-0024 D10), and then built against the
v1 observable-semantics specs ([BK-485](bk-485-spec-first-reset.md)), not the
0.33 backends. In the kernel/driver shape
([ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md)), OpenDAL is a
candidate thin driver beneath the contract kernel. The kernel line is frozen on
`frozen/kernel-driver` ([RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md)).

## Evidence (2026-10-26)

- **Repo side, measured.** `rg -i opendal` over the tree finds nothing: no spec,
  ADR, research note or doc names it. `FEATURES.md` § Backends
  (`BEGIN_GENERATED:backends_main`) lists nine sync backend types and
  § Native async backends lists three classes.
- **OpenDAL side, from recall, unverified.** Not fetched from
  <https://opendal.apache.org/> or <https://github.com/apache/opendal> when this
  was written; re-derive every point before acting on it:
  Apache top-level project, Rust core, Python binding `opendal` on PyPI,
  an `Operator` API (read, write, stat, list, delete, copy, rename) in async
  and blocking flavours, 50+ services (S3, Azure Blob, GCS, fs, SFTP, HDFS,
  WebDAV, OneDrive, GDrive, Dropbox, SQL and KV stores), layers for retry,
  logging, tracing, metrics and timeouts, a per-service capability struct,
  and an `ErrorKind` vocabulary. The Python binding is believed to expose fewer
  layers and less typing than the Rust core.

## Where the two differ (analysis, advisory)

The contract side: `FEATURES.md` states per-backend read-after-write,
atomicity, cost and retry behaviour, `WriteResult` field provenance and a typed
error vocabulary, and the conformance suite checks them. Not known to have an
OpenDAL counterpart: `RegistryConfig` (TOML, YAML, Pydantic, `${ENV}`
resolution, `Secret` masking), `Store.child()`, `write_atomic`/`open_atomic`
with a stated per-backend guarantee, the SQL backends, and the `ext.*` surface.
OpenDAL wins on backend breadth, raw throughput (Rust core) and project bus
factor.

## Prescription (advisory, presumed stale)

Pipeline, each step after the gate above opens:

1. **Spike.** An OpenDAL-backed driver over the Python binding, S3 and fs
   services first, run against the v1 conformance suite. Output: a
   per-service table of which contract clauses OpenDAL keeps, and what the
   driver must add on top to keep the rest.
2. **RFC.** Decides from that table between: an OpenDAL driver behind an extra
   (breadth for every service, capability-gated by what conformance measured);
   delegating some own drivers (S3, Azure, SFTP) to it; positioning only (an
   explanation page next to fsspec and obstore, plus a migration note); or
   decline (`BACKLOG-DONE.md` § Decided against, the table as diagnosis).
3. **Specs.** The driver's spec under the v1 spec set, ground per
   [`sdd/observe/ground-register.md`](../observe/ground-register.md).
4. **Driver, tests, docs**, per the RFC's chosen outcome, each its own item.

Effort L covers the spike and the RFC; steps 3 and 4 are follow-up items.
