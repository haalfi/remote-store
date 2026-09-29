# ADR-0042: One Contract Kernel over Thin Drivers

## Status

| Field         | Value                                  |
| ------------- | -------------------------------------- |
| Status        | Proposed                               |
| Supersedes    | —                                      |
| Superseded by | —                                      |
| Amends        | ADR-0001, ADR-0011, ADR-0012, ADR-0025 |

Proposed by BK-387 with RFC-0017's Open Questions 1, 4, 6 and 7 answered by
the maintainer. **Accepted in the PR that lands the first backend on this
design** (RFC-0017 D3 step 1, the kernel over the Memory drivers), not before:
the design is decided now and proven by its first migration. The amendments
below take effect on acceptance; until then the four amended records stand
unchanged.

## Context

[Audit-021](../audits/audit-021-contract-placement.md) attributes 45 of the 71
user-audience defects from v0.28.0 onward to rules stated once and implemented
per backend class: 35 defects on 11 contract clauses re-applied per class,
and 10 on the SFTP session lifecycle. The contract is implemented by 13 concrete classes and
enforced zero times at the boundary every call crosses; the earlier remedies,
more conformance cells and more spec text, did not close the class.
[RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md) proposes the
remedy and carries the design, its per-item assignment of the 35 cluster-A
defects, and every figure with its derivation. This record decides it.

## Decision

Section references are to RFC-0017, which carries the rationale.

- **One kernel implements `Backend` over a thin `Driver`** (D1, D2). The
  driver supplies wire primitives, declared capabilities and a classifier.
  The kernel owns the cross-cutting clauses and one error-mapping choke
  point. Direct `Backend` subclassing keeps working. *Reverse if*
  kernel-owned defects recur at the per-class rate audit-021 measured.
- **The kernel is written once in async** (D6, Open Question 1). `unasync`
  generates the sync surface both runtimes share. A small hand-written sync
  layer adds what async lacks: `read_seekable`, `open_atomic` and a `BinaryIO`
  `read`. *Reverse if* the generated part needs hand edits.
- **Every remote driver owns its lifecycle through a `Session`** (D5). The
  `Session` owns connect, connect retry where the wire separates connect from
  operation, liveness and invalidation behind one
  `run(op)`, and the kernel runs every remote operation through it. Local and
  Memory have none. *Reverse if* a driver's lifecycle cannot be separated
  from its operations.
- **One driver per service** (D4). S3's is the boto3 driver, registered as
  `"s3"`; s3fs and PyArrow's S3 filesystem stop being backend layers.
  Azure's is async. Sync Azure callers get a sync driver generated from it,
  with the stream primitives hand-written, and it replaces the sync
  `AzureBackend`. *Reverse if* the boto3 driver cannot reach D4's option
  parity, or the generation cannot map Azure's two SDK surfaces.
- **Classification stays in each driver** (Open Question 6). The kernel calls
  `classify(exc, op, key)` at its choke point, then sets `path` and
  `backend` and guarantees a message. *Reverse if* mapping-content defects
  recur across drivers.
- **`max_depth` applies only when `recursive`** (Open Question 4). This is
  DEPTH-003's reading, the one `BackendContract.dfy` verifies. ASYNC-014's
  contrary wording (BUG-240) is not the contract.
- **The formal model covers the root rule, the close posture and the absent
  container** (Open Question 7). BE-029, BE-020 and BE-021 § Reach become
  verified clauses before kernel code.

The migration order, retirement gates and benchmarks are process, and they
live in D3 and D8.

## Amendments on acceptance

- **[ADR-0001](0001-architecture-store-registry-backends.md)**, *Backend
  (ABC)*: the backend layer splits in two, the kernel implementing the
  contract and the driver carrying the storage-specific wire. Its consequence
  "adding a backend = implement the ABC" becomes "implement a `Driver`";
  subclassing `Backend` directly stays valid and is no longer the documented
  route.
- **[ADR-0011](0011-retry-per-backend-native.md)**, *retry is a transport
  concern*: for every remote driver whose wire separates connect from
  operation, the **connect** budget moves to its `Session` (RFC-0017 D5);
  per-operation retry stays each driver's native
  mechanism, as that record decides.
- **[ADR-0012](0012-async-store-backend-api.md)**, *separate async types* and
  its dismissal of Option E: the types stay separate, and the dismissal is
  narrowed rather than reversed. By driver kind, the sync surface is:
  - **sync drivers** (Memory, Local, SFTP, the SQL pair, S3, HTTP; Memory
    also keeps an async driver of its own): served by the sync kernel, whose
    shared surface is generated as native sync source from the async kernel
    and whose sync-only surface is hand-written (the Decision above);
  - **async drivers with a generated sync twin** (Azure): served by that
    twin, generated except for its stream-returning primitives, through the
    sync kernel, with no runtime wrapper;
  - **async-only drivers** (Graph): reached by sync callers through
    `AsyncBackendSyncAdapter` over the async kernel, the runtime wrapper
    ADR-0012's Option E describes, as they are today.

  Async-first source is taken for the kernel and the Azure driver. Option E's
  runtime wrapper stays where ADR-0025 already uses it.
- **[ADR-0025](0025-async-to-sync-backend-adapter.md)**, its scope: the
  adapter stays the sync route for async-only backends (Graph), and is not the
  route for Azure, which gets a generated sync driver. Its capability
  translation is unchanged. The "reverse if a native async seekable-read op is
  added" does not fire, because `get_range` is a driver primitive and the
  async surface gains no seekable-read operation.

## Consequences

- **Positive:** each contract clause is implemented once, so a clause fixed is
  fixed for every migrated class; RFC-0017 assigns 10 of cluster A's 35 items
  to the kernel outright and 13 of the 71 to the session layer.
- **Positive:** hand-written concrete classes go from 13 to 10 (the sync
  Azure driver, generated but for its stream primitives, comes on top of
  them), and adding a backend means
  writing wire primitives and a classifier rather than 21 methods.
- **Negative:** a kernel defect regresses every migrated class at once. The
  formal model bounds it only for the clauses it covers; how migration
  contains the rest is RFC-0017 D3's.
- **Negative:** a code-generation step, with its committed output and a drift
  check, becomes part of the build of the sync kernel and the sync Azure
  driver.
- **Negative:** users of `S3Backend` and `S3PyArrowBackend` by class name, and
  `unwrap(s3fs.S3FileSystem)` callers, break at D3 step 2; `ext.arrow` loses
  its Tier-1 native probe on S3 there. Users of sync `AzureBackend` by class
  name break at D3 step 4 unless the generated replacement keeps the name,
  which that step decides.
- **Neutral:** `Store`, `Registry`, the error hierarchy and capabilities keep
  their interfaces.
