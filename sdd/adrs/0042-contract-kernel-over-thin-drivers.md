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

- **One kernel implements the `Backend` surface over a thin `Driver`.**
  RFC-0017 D1 and D2: the driver supplies wire primitives, declared
  capabilities and one classifier; the kernel owns the cross-cutting clauses
  and one error-mapping choke point over every call, page and stream. `Backend` stays
  the abstract contract type and direct subclassing keeps working. *Reverse if*
  D8 step 4's re-audit finds kernel-owned items recurring at the rate
  audit-021 measured per class, which would show the placement did not move
  the defects.
- **The kernel is written once in async and the sync twin is generated**
  (RFC-0017 D6, first option; Open Question 1). `AsyncDriverBackend` is the
  source, and `unasync` generates what the two surfaces share. A small
  hand-written sync layer supplies what they do not share: `read_seekable`
  (over `get_range`), `open_atomic` (over `open_write`) and `read`'s
  `BinaryIO`, since the async ABC has no such methods and streams an iterator.
  Async-native drivers stay first-class. *Reverse if* the generated part needs
  hand edits, which would make it a second hand-maintained kernel.
- **A session layer owns the connection lifecycle** (RFC-0017 D5, audit-021
  H-2). A `Session` owns connect, the connect-retry budget, liveness and
  dead-client invalidation behind one `run(op)` entry. SFTP and Graph are its
  users; the SQL drivers are not. *Reverse if* SFTP's driver shows the
  lifecycle cannot be separated from its operations.
- **One driver per service; for S3 it is the boto3 one** (RFC-0017 D4).
  `S3Boto3Backend` becomes the single S3 driver, registered under `"s3"`,
  and s3fs and PyArrow's S3 filesystem stop being backend layers, so
  `S3Backend` and `S3PyArrowBackend` have no successor on the kernel. Async
  S3 callers keep `SyncBackendAdapter`'s auto-wrap. *Reverse if* the boto3
  driver cannot reach the option parity RFC-0017 D4 lists for what the s3fs
  lane forwards today.
- **Sync Azure callers get a generated sync driver.** The single async Azure
  driver is the source; `unasync` generates the primitives the two SDKs
  share, and the stream-returning ones (`get` and `get_range` returning
  `BinaryIO` where the async driver streams an iterator) are hand-written. It
  replaces the hand-written sync `AzureBackend`, with its behaviour kept. The
  adapter route was rejected for what it takes from sync callers (RFC-0017
  § Impact). *Reverse if* the generation cannot map the Azure SDK's sync and
  async surfaces.
- **Classification stays inside each driver** (Open Question 6):
  `classify(exc, op=..., key=...)`, invoked by the kernel at its choke point,
  which then sets `path` and `backend` and guarantees a non-empty message. The
  wire-signal alternative reaches four of the eight driver-kept items at the
  cost of one primitive spanning every wire's vocabulary. *Reverse if* the D8
  step 4 re-audit finds mapping-content defects recurring across drivers.
- **`max_depth` applies only when `recursive`** (Open Question 4): the kernel
  encodes DEPTH-003's reading, the one `BackendContract.dfy` verifies, and
  ASYNC-014's contrary wording (BUG-240) is not the contract.
- **The formal model covers the root rule, the close posture and the absent
  container** (Open Question 7): BE-029, BE-020 and BE-021 § Reach join the
  verified clauses the kernel is written against, placed as RFC-0017's Open
  Question 7 answer states.

How the design is reached (migration order, retirement gates, benchmarks) is
process, and lives in RFC-0017 D3 and D8, not here.

## Amendments on acceptance

- **[ADR-0001](0001-architecture-store-registry-backends.md)**, *Backend
  (ABC)*: the backend layer splits in two, the kernel implementing the
  contract and the driver carrying the storage-specific wire. Its consequence
  "adding a backend = implement the ABC" becomes "implement a `Driver`";
  subclassing `Backend` directly stays valid and is no longer the documented
  route.
- **[ADR-0011](0011-retry-per-backend-native.md)**, *retry is a transport
  concern*: for connection-oriented drivers the **connect** budget moves to the
  `Session` (RFC-0017 D5); per-operation retry stays each driver's native
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
