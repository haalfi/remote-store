# RFC-0017: One contract kernel over thin drivers

## Status

Draft. Filed from
[audit-021](../audits/audit-021-contract-placement.md) at the user's
direction; not yet tracked by a backlog item, which is minted when the audit's
proposals are dispositioned. If accepted it graduates to an ADR amending
[ADR-0001](../adrs/0001-architecture-store-registry-backends.md) (the `Backend`
layer splits in two) and to amendments of spec 003 (the contract clauses move
from per-backend obligations to kernel behaviour, with the driver's obligations
stated in their place), spec 029 (the async surface), and the custom-backend
guide.

**Date:** 2026-09-28. Every figure below is pinned to `8fa22d6` and is either
quoted from audit-021 with its derivation, or names its command here. The tree
moves on every merge: re-run rather than quote.

## Summary

Today every backend class implements the 21-method `Backend` surface by hand
and, inside each method, re-derives the contract's cross-cutting clauses: root
refusal, closed guard, wrong-type reclassification, absent-container tolerance,
the first-page listing bound, the file-ancestor gate and error mapping. That is
13 classes × 21 methods, and audit-021 attributes 45 of the 71 user-impacting
defects of the last six releases (63%) to one clause missed on one method of
one class. This RFC proposes that the surface be implemented **once**, in a
kernel that is itself the `Backend`, over a per-backend `Driver` of about ten
wire primitives, one `classify(exc)` function and one `container_absent(exc)`
predicate. Error mapping then happens at a single choke point that wraps every
driver call, every listing page and every stream. `Store`, `Registry`,
capabilities, `ext/`, `aio/` and the conformance suite keep their interfaces,
and the suite is the migration's safety net. Two consolidations ride with it:
one S3 driver instead of two shipped lanes and a parked third, and one Azure
implementation instead of a hand-written sync/async pair.

## Motivation

### The bug population is the contract, re-implemented

Audit-021 § H-1 carries the register and the figures; the two that decide the
design are these. **The same clause is fixed N times:** 17 of 71 entries name
two or more classes, and BUG-259 touched eleven classes on two halves of one
rule. **The fix lands per method, so it is missed per method:** BUG-249 was
three listing methods on one class left unwrapped "against fifteen methods
that do wrap"; BUG-280 is the same shape on `LocalBackend`; BUG-293 is twelve
`except` arms on one class; BUG-276 is seven sites in five files.

The eight shared guard helpers are called at 200 sites across 11 files, the
source carries 395 `except` handlers, and `Store` catches nothing: the
never-leak invariant of BE-021 is asserted 13 times inside backends and zero
times at the boundary every call crosses. BE-021 itself is 496 lines of prose
stating what one function should do.

### The remedies already tried were tests and spec text, and they were tried in full

The bug-prevention research (2026-04-03) and the contract-completeness research
(2026-04-05) diagnosed the same cross-product and prescribed extended
conformance cells and tightened clauses. The conformance suite reached 323
test functions and BE-021 its 496 lines; cluster A still produced 35 defects in
six releases. A test fails only on the cell it covers, and the research's own
estimate of the product was ~1,890 cells. Removing the backend axis from the
product is the change that alters the count; covering the product does not.

### The repo is already half way there

`_flat_ns.py` (495 lines of guards applied by injection), `_S3Base`,
`_ErrorMappingStream(mapper=...)`, `_safe_wrap` and `AsyncBackendSyncAdapter`
were each introduced after a bug cluster, and each halved the next cluster on
the classes it reached. None reaches all 13 classes and none owns the method
bodies. This RFC finishes that move rather than starting a new one.

## Proposal

### D1. A `Driver` protocol of wire primitives

A driver maps one-to-one onto its wire protocol and carries no path, root,
type, closed or mapping logic:

```python
class Driver(Protocol):
    name: str
    namespace: Literal["flat", "hierarchical"]
    capabilities: CapabilitySet          # what the wire offers, not what the kernel adds

    def head(self, key: str) -> Entry | None: ...     # file metadata, None if absent; raises native
    def get(self, key: str) -> BinaryIO: ...          # raises native
    def put(self, key: str, content, *, overwrite: bool, metadata) -> WriteResult: ...
    def delete(self, key: str) -> None: ...
    def list_page(self, prefix: str, *, delimiter: str | None, cursor) -> Page: ...
    def rename(self, src: str, dst: str) -> None: ...   # optional: only if the wire has one
    def copy(self, src: str, dst: str) -> None: ...     # optional
    def mkdir(self, key: str) -> None: ...              # hierarchical only
    def probe(self) -> None: ...                        # health; raises native

    def classify(self, exc: Exception) -> RemoteStoreError: ...   # the one mapping function
    def container_absent(self, exc: BaseException) -> bool: ...  # narrow wire-shape predicate
    def connection_dead(self, exc: BaseException) -> bool: ...   # for the stream wrapper's is_fatal
```

`Entry` and `Page` are two small frozen records: what `head` returns and what
one listing page returns (keys, common prefixes, next cursor). The optional
methods are declared by presence; the kernel derives `move` from `rename` where
present and from `copy` + `delete` otherwise, and declares `ATOMIC_MOVE` from
that.

### D2. One kernel is the `Backend`

A concrete class in core implements today's 21 public methods over a driver.
It owns, once:

- root refusal from the key (BE-029, both predicates as `_flat_ns` now states
  them), and the closed guard, in the order spec 003 fixes;
- the wrong-type probes on the error path, the absent-container tolerance, and
  the first-page listing bound (BE-021), including its page-not-item rule;
- the file-ancestor gate and its fail-open policy, decided once (BUG-292);
- the `max_depth` reference algorithm, so sync and async cannot disagree
  (BUG-240);
- the temp-and-promote protocol for `write_atomic` and `open_atomic`, with the
  displace-and-restore fallback SFTP now carries alone;
- error mapping at a single choke point: every driver call, every `list_page`
  iteration and every stream handed back by `get` passes through
  `driver.classify`, and a `RemoteStoreError` already typed passes through
  untouched (BUG-293).

The kernel is generic over the driver, so a custom backend is a driver, and
the conformance suite runs against the kernel-over-driver exactly as it runs
against a backend today.

### D3. Migration, one class at a time, behind the unchanged suite

The kernel lands beside the existing classes. Each class becomes a driver in
its own PR, green when the conformance suite passes unchanged for its fixture.
Order, by how much shared shape already exists: the flat-namespace family
first (`S3Boto3Backend`, `AzureBackend`, `SQLBlobBackend` already share
`_flat_ns`), then `LocalBackend` and `MemoryBackend`, then `SFTPBackend` with
D5, then `GraphBackend`. The old `Backend` ABC stays importable as the kernel's
public face throughout; nothing above it changes.

### D4. One driver per service

- **S3.** Promote the parked `S3Boto3Backend` (ID-202) as the S3 driver: it
  is standalone, boto3-only, and the lane spec 003 already cites as "the shape
  a fix takes" for the first-page bound. Deprecate `S3Backend` (s3fs) and
  `S3PyArrowBackend`; `ext.arrow` gives PyArrow a filesystem over any `Store`,
  which is the surface `S3PyArrowBackend` exists for. ID-202's own revisit
  list names "the `_S3Base` refactor" as the Ship increment; the kernel is that
  refactor.
- **Azure.** Keep one async-native driver and serve sync callers through
  `AsyncBackendSyncAdapter` (ADR-0025), as `GraphBackend` already does. The
  hand-written sync class is retired.

Concrete classes go from 13 to 10, and the driver surface to about 10 drivers
× 10 primitives instead of 13 classes × 21 methods.

### D5. A session layer for connection-oriented drivers

A `Session` owns connect, the retry budget, liveness, dead-client invalidation
and one `run(op)` entry, so an operation is a function of a live client and
cannot re-enter the budget (BUG-274, 278), cannot evaluate a lazy client
outside the mapper (BUG-279), and can see connect-time context (BUG-273). SFTP
is the first user; the SQL drivers (pool, dropped table as `BackendUnavailable`)
and Graph (token, monitor) follow.

### D6. Sync and async

The kernel is one more sync/async pair. Two options, to be decided before D3
starts: write it once in async and generate the sync twin with `unasync`
(the urllib3 and httpx approach), or write it sync and serve async-native
drivers through the existing adapter with its thread hop. The first keeps
async-native drivers first-class; the second is less machinery. Open Question 1.

### What each open cluster-A bug becomes

Of the 13 open cluster-A items, 12 stop being possible rather than being
fixed: BUG-276, 279, 280, 293, 245 (one classifier per driver, applied at one
boundary); BUG-255, 257 (one listing loop owns the bound); BUG-256 (one
`probe()` per driver, and the kernel decides what `ping` owes); BUG-260, 253,
292 (root spelling, ancestor walk and fail-open decided once); BUG-240 (one
`max_depth` algorithm). BUG-273 needs D5.

## Alternatives Considered

- **More conformance cells, tighter spec text.** Tried in full (§ Motivation).
  Covers the product one cell at a time; the product stays.
- **A last-resort mapper at the `Store` boundary only.** Closes the never-leak
  breaches (BUG-249, 280, 279, 245) and nothing else: root, absent-container,
  wrong-type and the listing bound are semantics, not mapping, and would still
  be implemented 13 times. Cheap, and worth doing first as a stop-gap if D3 is
  delayed; not a substitute.
- **Mixins per clause.** Keeps the method bodies per class and adds a
  resolution-order puzzle; the 200 call sites become 200 `super()` calls.
  Rejected.
- **Adopt fsspec's `AbstractFileSystem` as the kernel.** ADR-0003 already
  decided fsspec is an implementation detail, and its derived-method layer
  re-raises `FileNotFoundError` rather than a typed hierarchy, so the mapping
  work would remain. The *shape* is the precedent, not the library:
  `gocloud.dev/blob` (a ~12-method `driver.Bucket`, a portable `blob.Bucket`
  that wraps every call and maps every error through `ErrorCode` at one
  boundary) and Rust `object_store` (a ten-method trait, everything else
  derived) are closer to D1/D2.

## Impact

- **Public API:** `Store`, `Registry`, the error hierarchy, capabilities and
  `ext/` unchanged. `Backend` remains importable and is the kernel. New public
  names: `Driver`, `Entry`, `Page`, `Session`.
- **Backwards compatibility:** breaking for authors of custom backends, who
  implement a driver instead of subclassing `Backend`; pre-1.0 permits it and
  the migration guide owes a section. Breaking for users of `S3Backend`,
  `S3PyArrowBackend` and sync `AzureBackend` as class names once D4 lands;
  each keeps a deprecation cycle. `Store` callers see no change.
- **Performance:** none intended; the kernel issues the same probes the
  per-backend code issues today, and the S3 driver drops the s3fs layer.
- **Testing:** the kernel is tested once against a fake driver that can be
  told to raise any wire shape at any call, which is the cross-product the
  conformance suite could not reach (BK-345, ID-244, ID-251 become moot for
  the kernel and reduce to driver cells). The conformance suite is unchanged
  and gates every migration in D3.
- **Effort:** kernel plus first three migrations L; D5 plus SFTP L; D4 M each.
- **What is deleted:** the 200 guard call sites, most of the 395 `except` arms
  outside classifiers, two S3 classes, one Azure class, and most of BE-021's
  496 lines, which become the kernel's docstrings.

**Acceptance criterion.** After D3 completes for the flat-namespace family,
the three measurements in audit-021 § H-1 are re-run: guard call sites, `except`
handlers outside `classify` functions, and `except` handlers in the kernel's
choke point. The RFC is accepted if the first two fall by at least half on the
migrated classes and the conformance suite passes unchanged for their
fixtures; it returns to Draft otherwise.

## Open Questions

1. **D6:** generated sync twin, or sync kernel with the adapter for async
   drivers? Decide before D3.
2. **`Page` for wires without a page boundary.** BE-021 allows marking items
   as the service returns them; the kernel needs the driver to say which it
   does, or the divergence is stated per driver as today.
3. **`namespace` as a value or as two kernels.** One kernel with a flag keeps
   one choke point; two kernels keep the flat-namespace probes out of the
   hierarchical path. The flag is proposed; the split is the fallback if the
   flag branches more than the three places `_flat_ns` already names.
4. **Which spec contradictions the kernel must adjudicate first.** BUG-240 is
   one; the kernel encodes one answer per clause and cannot land on a clause
   the specs still dispute.

## References

- Audit: [audit-021](../audits/audit-021-contract-placement.md)
- Related specs: `sdd/specs/003-backend-adapter-contract.md` (BE-021, BE-029),
  `sdd/specs/029-async-store-backend-api.md`, `sdd/specs/005-error-model.md`
- Related ADRs: [ADR-0001](../adrs/0001-architecture-store-registry-backends.md),
  [ADR-0003](../adrs/0003-fsspec-is-implementation-detail.md),
  [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md)
- Related research: `sdd/research/research-bug-prevention-beyond-testing.md`,
  `sdd/research/research-backend-contract-completeness.md`,
  `sdd/research/research-s3-boto3-poc.md` (ID-202)
- Related backlog: BK-366 (bug share undiagnosed), BK-345, ID-244, ID-251
- External: gocloud.dev `blob` driver interface; Rust `object_store` trait
