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
per backend class: 35 contract clauses re-applied per class, 10 the SFTP
session lifecycle. The contract is implemented by 13 concrete classes and
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
  source and `unasync` generates `DriverBackend`, so async-native drivers stay
  first-class. *Reverse if* the generated twin needs hand edits that the
  generator cannot express, which would make it a second hand-maintained
  kernel.
- **Sync Azure callers get a generated sync driver.** The single async Azure
  driver is the source; the hand-written sync `AzureBackend` is replaced at
  D3 step 4 with its behaviour kept. The adapter route was rejected for what
  it takes from sync callers (RFC-0017 § Impact). *Reverse if* the generation
  cannot map the Azure SDK's sync and async surfaces.
- **Classification stays inside each driver** (Open Question 6):
  `classify(exc, op=..., key=...)`, invoked by the kernel at its choke point,
  which then sets `path` and `backend` and guarantees a non-empty message. The
  wire-signal alternative reaches four of the eight driver-kept items at the
  cost of one primitive spanning every wire's vocabulary. *Reverse if* the D8
  step 4 re-audit finds mapping-content defects recurring across drivers.
- **Spec contradictions are adjudicated before the step that encodes them**
  (Open Question 4). BUG-240 is the one audit-021 counts and is decided before
  step 1: DEPTH-003's reading wins, the one `BackendContract.dfy` verifies.
- **The formal model is extended before kernel code** (Open Question 7): the
  root rule (BE-029), the close posture (BE-020) and the absent container
  (BE-021 § Reach), placed as RFC-0017's Open Question 7 answer states.
- **Migration is one class per PR behind the conformance suite**, and a
  retiring class is deleted in the PR that registers its replacement (RFC-0017
  D8 step 3), benchmarked against
  [`acceptance-band.md`](../../benchmarks/results/acceptance-band.md).

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
  its dismissal of async-first: the types stay separate, and the kernel behind
  them is written async-first with the sync twin generated, which is Option E
  applied to the kernel alone rather than to every backend.
- **[ADR-0025](0025-async-to-sync-backend-adapter.md)**, *capability
  translation*: its "reverse if a native async seekable-read op is added" is
  triggered by the driver's `get_range` primitive. The adapter keeps serving
  hand-wrapped async backends; it is not the sync route for Azure.

## Consequences

- **Positive:** each contract clause is implemented once, so a clause fixed is
  fixed for every migrated class; RFC-0017 assigns 10 of cluster A's 35 items
  to the kernel outright and 13 of the 71 to the session layer.
- **Positive:** concrete classes go from 13 to 10, and adding a backend means
  writing wire primitives and a classifier rather than 21 methods.
- **Negative:** a kernel defect regresses every migrated class at once. It is
  bounded by migrating one class per revertable PR behind the suite, and by
  the formal model only for the clauses it covers.
- **Negative:** a code-generation step, with its committed output and a drift
  check, becomes part of the build of the sync kernel and the sync Azure
  driver.
- **Negative:** users of `S3Backend` and `S3PyArrowBackend` by class name, and
  `unwrap(s3fs.S3FileSystem)` callers, break at D3 step 2; `ext.arrow` loses
  its Tier-1 native probe on S3 there.
- **Neutral:** `Store`, `Registry`, the error hierarchy and capabilities keep
  their interfaces.
