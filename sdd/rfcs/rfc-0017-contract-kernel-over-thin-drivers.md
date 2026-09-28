# RFC-0017: One contract kernel over thin drivers

## Status

Draft. Filed from
[audit-021](../audits/audit-021-contract-placement.md) at the user's
direction; not yet tracked by a backlog item, which is minted when the audit's
proposals are dispositioned. If accepted it graduates to an ADR amending
[ADR-0001](../adrs/0001-architecture-store-registry-backends.md) (the `Backend`
layer splits in two) and to amendments of: spec 003 (the contract clauses move
from per-backend obligations to kernel behaviour, with the driver's obligations
stated in their place); spec 005 (ERR-001's `path` and `backend` are set by the
kernel); spec 009 (SFTP-010's connection tiers become D5's `Session`); spec 022
(temp-and-promote becomes kernel behaviour); spec 026 (`probe()` against
PING-011); spec 029 (the async surface); spec 036 (seekable read derived from
`get_range`); spec 037 (the `max_depth` algorithm decided once); the
per-backend specs (AZ-, S3-, S3PA-, GR-, SQL-BLOB-) wherever a clause describes
class behaviour the kernel now owns; the formal layer (D7); and the
custom-backend guide. The ripple-check's "Store or Backend ABC" row names the
conformance suite as the safety net; it is one only once those specs agree
with the kernel, which is why the amendments are listed here and not left to
D3.

**Date:** 2026-09-28. Every figure below is pinned to `8fa22d6` and is either
quoted from audit-021 with its derivation, or names its command here. The tree
moves on every merge: re-run rather than quote.

## Summary

Today every backend class implements the 21-method `Backend` surface by hand
and, inside each method, re-derives the contract's cross-cutting clauses: root
refusal, closed guard, wrong-type reclassification, absent-container tolerance,
the first-page listing bound, the file-ancestor gate and error mapping. That is
10 sync classes × 21 methods plus 3 async classes × 19, and audit-021
attributes 45 of the 71 user-audience defects of the last six releases (63%)
to rules stated once and re-implemented per class: 35 a contract clause
re-applied per class, 10 the SFTP session lifecycle. Of those 45, by the split
in § What each cluster-A bug becomes, 18 are owned outright by the kernel this
RFC proposes, 5 are split between kernel and driver, 10 stay in the driver's
classifier or resource logic, 2 wait on a spec decision, and 10 are D5's
session layer. This RFC proposes that the surface be implemented **once**, in
a kernel that is a concrete `Backend`, over a per-backend `Driver` of about a
dozen wire primitives, one `classify(exc, op, key)` function and one
`container_absent(exc, op)` predicate. Error mapping then happens at a single
choke point that wraps every driver call, every listing page and every
stream, and that guarantees the error's `path`, `backend` and a non-empty
message whatever the driver returned. `Store`, `Registry`, capabilities,
`ext/`, `aio/` and the conformance suite keep their interfaces, and the suite
is the migration's safety net once the specs in § Status agree with the
kernel. Two consolidations ride with it:
one S3 driver instead of two shipped lanes and a parked third, and one Azure
implementation instead of a hand-written sync/async pair.

## Motivation

### The bug population is the contract, re-implemented

Audit-021 § H-1 carries the register and the figures; the two that decide the
design are these. **The same clause is fixed N times:** 14 of cluster A's 35
entries name two or more classes, and BUG-259 changed eight classes on two
halves of one rule that binds eleven. **The fix lands per method, so it is
missed per method:** BUG-249 was three listing methods on one class left
unwrapped "against fifteen methods that do wrap"; BUG-280 is the same shape on
`LocalBackend`; BUG-293 is twelve `except` arms across the two Azure classes;
BUG-276 is seven sites in five files.

The eight shared guard helpers are called on 164 lines across 10 files and
wrapped per class 22 times (audit-021 commands (e) and (g)), the source
carries 395 `except` handlers, and `Store` catches nothing: the never-leak
invariant of BE-021 is asserted 13 times inside backends and zero times at
the boundary every call crosses. BE-021 itself is 496 lines of prose stating
what one function should do.

### The remedies already tried were tests, static checks and spec text

The bug-prevention research (2026-04-03) and the contract-completeness research
(2026-04-05) diagnosed the same cross-product. The first prescribed seven
deliverables, of which six exist (`_safe_wrap`, the property-based tests, ruff
`BLE`, the extended conformance cells, the `ResourceWarning` sites; audit-021
§ H-1 names each one's location) and one, an AST check over broad `except`
arms in the backends, was deferred and never built. The second prescribed
tightened clauses, and BE-021 reached 496 lines; the conformance suite reached
323 test functions. Cluster A still produced 35 defects in six releases, 13 of
them closed in v0.31.0 alone (audit-021 § Summary carries the per-release
series and its cascade confound). A test fails only on the cell it covers, and
the contract-completeness research's own estimate of the product
(`research-backend-contract-completeness.md` § 3) was ~1,890 cells at 7
backends and 18 methods, ~3,510 by the same formula at 13 classes, treating
the three async twins as classes. Removing the backend axis from the product
is the change that alters the count; covering the product does not. The
unbuilt static check is taken up under § Alternatives.

### The repo is already half way there

`_S3Base` (RFC-0005, BK-011), `_flat_ns.py` (ID-211; 495 lines of guards
applied by injection), `_safe_wrap` (BUG-159), `_ErrorMappingStream(mapper=...)`
and `AsyncBackendSyncAdapter` (ADR-0025) each share one piece of the contract
across some classes. None reaches all 13 and none owns the method bodies.
RFC-0005 is the direct antecedent: it extracted `_S3Base` as deduplication and
stopped at the S3 family. This RFC finishes that move rather than starting a
new one.

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
    def probe(self) -> None: ...                      # health; must touch the container; raises native

    # Optional, declared by presence; the kernel derives capabilities from them.
    def get_range(self, key: str, offset: int, length: int | None) -> BinaryIO: ...  # -> SEEKABLE_READ
    def open_write(self, key: str, *, metadata) -> WriteHandle: ...                  # -> native open_atomic
    def rename(self, src: str, dst: str) -> None: ...                                 # -> ATOMIC_MOVE
    def copy(self, src: str, dst: str) -> None: ...
    def mkdir(self, key: str) -> None: ...                                            # hierarchical only

    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError: ...  # the one mapping function
    def container_absent(self, exc: BaseException, *, op: Op) -> bool: ...          # narrow wire-shape predicate
    def connection_dead(self, exc: BaseException) -> bool: ...                       # for the stream wrapper's is_fatal
```

`Entry`, `Page` and `WriteHandle` are small records: what `head` returns, what
one listing page returns (keys, common prefixes, next cursor), and a writable
handle on a wire-side temporary that the kernel promotes or discards. `Op` is
an enum of the public operations plus the kernel's internal scopes (`probe`,
`identity`, `monitor`), so a driver can classify by what asked: today every
classifier already takes `path` (ERR-001), Graph's `classify_graph_error`
takes a `scope` that decides whether a `404` is an absent item or an absent
drive ([ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md),
BK-266), and Azure routes listings and file operations through different
context managers. A `classify(exc)` with no scope could not reproduce either
and would re-open BUG-248; the scope is therefore part of the primitive, and
the driver, not the kernel, decides what an identity-scope failure means.

The optional methods are declared by presence. The kernel derives `move` from
`rename` where present and from `copy` + `delete` otherwise, and declares
`ATOMIC_MOVE` from that; derives `SEEKABLE_READ` from `get_range` (Azure's
range reader, RFC-0003's PyArrow path) and otherwise spools, as the ABC
default does today; and implements `open_atomic` over `open_write` where
present and otherwise by spooling to a local temporary and one `put` at exit,
which is the adapter's synthesis in ADR-0025 and a second copy of every large
payload. A driver that omits `get_range` or `open_write` therefore loses a
data path it may have today; § Impact names the two classes where that
happens.

### D2. One kernel is the `Backend`

A concrete class in core implements today's 21 public methods over a driver.
It owns, once:

- root refusal from the key (BE-029, both predicates as `_flat_ns` now states
  them), and the closed guard, in the order spec 003 fixes;
- the wrong-type probes on the error path, the absent-container tolerance, and
  the first-page listing bound (BE-021), including its page-not-item rule;
- the file-ancestor gate and its fail-open policy, decided once (BUG-292);
- the `max_depth` reference algorithm, decided once (Open Question 4 names
  BUG-240 as the contradiction to adjudicate before the kernel encodes it);
- the temp-and-promote protocol for `write_atomic` and `open_atomic`, with the
  displace-and-restore fallback SFTP now carries alone;
- error mapping at a single choke point: every driver call, every `list_page`
  iteration and every stream handed back by `get` or `get_range` passes
  through `driver.classify(exc, op=..., key=...)`; a `RemoteStoreError`
  already typed passes through untouched (BUG-293); and the kernel
  post-processes what comes back, setting `path` and `backend` (ERR-001) and
  synthesising a message from the exception class when the driver returned a
  blank one (ERR-009, BUG-276, BUG-264), so a classifier's omission cannot
  reach the caller as an empty string;
- the absent-container rule applied per operation scope, not per exception:
  the tolerant answers BE-021 § Reach decides are given only for the
  operations it names, and identity-scope calls (`write`, `probe`, drive-id
  resolution, the copy/move monitor) hand the driver an `Op` it may escalate,
  which is ADR-0038's ruling kept rather than overridden;
- the file-ancestor pre-check as a kernel option with today's default: the
  opt-in `reject_write_under_file_ancestor` moves from each flat-namespace
  class to the kernel's constructor, default off as now, and the walk runs in
  the kernel before any `put` when set. Hierarchical drivers get the check
  from the wire, because the kernel creates parents through `mkdir` before
  every `put`, so a file ancestor fails at `mkdir` whatever the payload size
  (BUG-253).

**What `Backend` is afterwards.** `Backend` stays the abstract contract type
every caller and every test names; the kernel is one concrete subclass,
`DriverBackend(Backend)`, constructed over a `Driver`. Subclassing `Backend`
directly stays valid and keeps passing the conformance suite; it is
deprecated as the way to add a backend, not removed. The consequences for the
in-tree subclasses that are not among the 13, enumerated by
`rg '^class \w+\((Backend|AsyncBackend)\)' src tests examples`: `_S3Base`
retires with its two lanes (D4); `AsyncBackendSyncAdapter` stays a direct
subclass, since it is the sync face of an async driver and not a backend of
its own (D6 decides whether it also becomes the sync kernel);
`DafnyOracleBackend` stays a direct subclass by design, because an oracle
must not share the implementation it checks (D7); the test fakes in
`tests/ext/test_arrow.py` and `tests/test_info.py` and the doubles under
`tests/aio/` stay as they are; `RedisBackend` in
`examples/snippets/custom_backend_guide.py` is rewritten as a driver, which
is the guide amendment § Status names.

The kernel is generic over the driver, so a custom backend is a driver, and
the conformance suite runs against the kernel-over-driver exactly as it runs
against a backend today.

### D3. Migration, one class at a time, behind the unchanged suite

The kernel lands beside the existing classes. A class that migrates becomes a
driver in its own PR, green when the conformance suite passes unchanged for
its fixture. Not every class migrates; the fate of each of the 13 is fixed
here so that D3 and D4 cannot disagree:

| Class | Fate | Order |
|---|---|---|
| `S3Boto3Backend` | migrate (first driver; it is the parked ID-202 lane) | 1 |
| `SQLBlobBackend`, `SQLQueryBackend` | migrate | 2 |
| `AsyncAzureBackend` | migrate (the one Azure driver) | 3 |
| `AzureBackend` (sync) | retire, unmigrated: replaced by the adapter over the Azure driver once step 3 is green; deprecation cycle, then deleted | after 3 |
| `S3Backend`, `S3PyArrowBackend` | retire, unmigrated: deprecation cycle after step 1 is green and the D4 throughput measurement is published; deleted with `_S3Base` | after 1 |
| `LocalBackend`, `MemoryBackend`, `AsyncMemoryBackend` | migrate | 4 |
| `SFTPBackend` | migrate, together with D5 | 5 |
| `GraphBackend` | migrate | 6 |
| `ReadOnlyHttpBackend` | migrate | 7 |

The three retiring classes stay hand-written 21-method `Backend` subclasses
through their deprecation cycle, coexist with the kernel for at least one
release, and are outside the acceptance measurement, which names the migrated
classes only. Nothing above `Backend` changes at any step.

### D4. One driver per service

- **S3.** Promote the parked `S3Boto3Backend` (ID-202) as the S3 driver: it
  is standalone, boto3-only, and the lane spec 003 already cites as "the shape
  a fix takes" for the first-page bound. Deprecate `S3Backend` (s3fs) and
  `S3PyArrowBackend`. The PyArrow lane exists for data-path throughput: its
  docstring reads "Uses PyArrow's C++ S3 filesystem for data-path operations
  (higher throughput)" and RFC-0003 tuned that path, so retiring it is a
  performance change for its users, stated under § Impact. `ext.arrow` keeps
  the PyArrow *filesystem interface* over any `Store` but at Python-level
  I/O, not the C++ path. ID-202's own revisit list names "the `_S3Base`
  refactor" as the Ship increment; the kernel is that refactor.
- **Azure.** Keep one async-native driver and serve sync callers through
  `AsyncBackendSyncAdapter` (ADR-0025), as `GraphBackend` already does. The
  hand-written sync class is retired. This settles the sync Azure path
  whatever D6 decides, because after D4 there is no sync Azure driver for a
  sync kernel to call, and it moves every sync Azure caller onto the
  adapter's documented semantics, four of which are regressions against the
  sync class today and are listed under § Impact with the same measure-first
  treatment as the S3 lane. The one way to avoid them is to generate a sync
  Azure driver from the async one, since the Azure SDK ships mirrored sync
  and `.aio` clients; that is D6's first option applied to the driver as well
  as the kernel, and Open Question 1 now covers both.

Concrete classes go from 13 to 10, and the driver surface to about 10 drivers
× about a dozen primitives instead of 10 classes × 21 methods plus 3 × 19.

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

### D7. The formal layer is the kernel's reference, and the oracle stays outside it

`sdd/formal/BackendContract.dfy` already states, verified, most of what D2
moves into the kernel: BE-008's precondition order, BE-021's canonical mapping
table, BE-014 and BE-015 on a missing path, DEPTH-001's reference algorithm,
BE-018's move atomicity and SIO-001's acquire-then-wrap (the Dafny-tagged
spec IDs `check_formal_trace.py` lists). The kernel is therefore written
against that contract rather than against the thirteen implementations, and
its first driver-independent test is the existing conformance run of
`DafnyOracleBackend` beside the kernel over a `MemoryDriver`: the two must
answer every cell alike. `DafnyOracleBackend` itself stays a direct `Backend`
subclass and is never migrated, because an oracle that shared the kernel
would check nothing. Whether the kernel over `MemoryDriver` becomes the
refinement target the Dafny `MemoryBackend` model proves against, replacing
the hand-written `MemoryBackend` as the verified reference, is Open
Question 7.

### What each cluster-A bug becomes

D1 keeps `classify` inside each driver, so the kernel moves where the
classifier is *invoked* and what the kernel does with its result; it does not
move what the classifier *maps*. The 35 cluster-A items therefore split four
ways, and the split is the figure a disposition needs beside the 63%. Each
row is a by-hand reading of the item's register entry, so it is disputable
item by item.

| Outcome | Closed (22) | Open (13) | Total |
|---|---|---|---|
| **Kernel-owned**: the defect cannot recur because the kernel applies the rule once (missed wrap or guard, root and absent-container semantics, listing bound, path normalisation, closed guard, message and attribute guarantee) | BUG-254, 259, 247, 246, 249, 248, 243, 242, BK-324, BK-301 | BUG-276, 279, 280, 293, 255, 257, 260, 253 | 18 |
| **Split**: the leak or the invocation is the kernel's, the type or content stays the driver's | BUG-264 (message synthesised by the kernel; the arm's content is the driver's), BK-358 (the stream wrapper's catch set becomes the kernel's; the `BackendUnavailable` verdict is the driver's), BK-359 (message and log record kernel; stall detection driver), BK-266 (self-op copy and the auth leak kernel; the probe scope driver), BK-298 (use-after-close kernel; credential ownership driver) | — | 5 |
| **Driver-kept**: classifier content or driver resource logic the kernel does not reach | BUG-275 (errno arm), BUG-265 (connect-time shapes, until D5), BK-316 (non-OpenSSH shapes), BUG-231 (a probe that touched nothing), BUG-222 (429/5xx/401 rows), BK-263 (credential in a message), BK-306 (session release) | BUG-256 (what `probe()` touches), BUG-245 (constructor leak; Open Question 5), BUG-273 (needs D5) | 10 |
| **Needs a spec decision first** | — | BUG-240 (Open Question 4), BUG-292 (BE-008 must choose narrow, warn or strict; the kernel then applies it once) | 2 |

Two consequences. `probe()` is made a required primitive rather than an
overridable no-op, so a driver cannot inherit a health check that contacts
nothing (BUG-231's shape), but what it touches stays the driver's. And the
ten driver-kept items are the argument for the wire-signal alternative under
§ Alternatives, which would move the mapping rows into the kernel too at the
cost of a second, larger primitive; Open Question 6.

## Alternatives Considered

- **More conformance cells, tighter spec text.** Tried (§ Motivation). Covers
  the product one cell at a time; the product stays.
- **The deferred static check** (`check_error_handling.py`, deliverable 6 of
  the bug-prevention research): an AST pass flagging a broad `except` arm
  that returns silently without inspecting `errno`, type or status. Cheap,
  and worth building whether or not this RFC is accepted, since cluster A's
  broad-arm members (BUG-293, 276, 275, 264, 222, 242, BK-316) are its
  target. It does not reach the missed-wrap or missed-guard shape (BUG-249,
  280, 279, 259, 247, 246, 243, 248, 254, 255, 257, 260, 253, BK-324), which
  is the larger half of the cluster, because those are absences rather than
  arms. Complementary, not a substitute.
- **RFC-0005's route, extended.** Deduplicate per family (`_S3Base` was its
  result). Removes copies within a family and leaves the per-class method
  bodies, so a clause is still applied per family rather than once; the
  prior art this RFC generalises.
- **A normalised wire-signal primitive instead of `classify`.** The driver
  returns `WireSignal(status, errno, service_code, message, connection_dead)`
  for a native exception, and the kernel owns BE-021's row table and maps it.
  This reaches the ten driver-kept items above (BUG-222's missing rows,
  BUG-275's errno arm, BK-316's errno-less shapes) and makes the mapping
  rows one table. It costs a primitive that must express every wire's
  vocabulary at once (S3 service codes, Azure `HttpResponseError` codes,
  Graph's scoped `404`, paramiko's shapes with no errno, SQLAlchemy dialect
  errors), which is the part of BE-021 that grew per backend for a reason.
  Not chosen here; kept as Open Question 6 because the driver-kept count is
  large enough that a disposition may prefer it.
- **A last-resort mapper at the `Store` boundary only.** Closes the never-leak
  breaches (BUG-249, 280, 279, 245) and nothing else: root, absent-container,
  wrong-type and the listing bound are semantics, not mapping, and would still
  be implemented 13 times. Cheap, and worth doing first as a stop-gap if D3 is
  delayed; not a substitute.
- **Mixins per clause.** Keeps the method bodies per class and adds a
  resolution-order puzzle; the 164 call lines become 164 `super()` calls.
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
  `ext/` unchanged. `Backend` remains the abstract contract type;
  `DriverBackend` is the kernel. New public names: `Driver`, `DriverBackend`,
  `Entry`, `Page`, `WriteHandle`, `Op`, `Session`.
- **Backwards compatibility:** additive for existing `Backend` subclasses,
  which keep working and keep passing conformance; the custom-backend guide
  and the conformance registry move to drivers, and direct subclassing is
  deprecated as the documented route, so the migration guide owes a section
  for backend authors. Breaking for users of `S3Backend`, `S3PyArrowBackend`
  and sync `AzureBackend` as class names once D4 lands; each keeps a
  deprecation cycle. `Store` callers see no change in interface.
- **Performance:** the kernel issues the same probes the per-backend code
  issues today, with the file-ancestor pre-check staying opt-in (D2), and the
  S3 driver drops the s3fs layer. Two retirements change data paths and are
  measured before they are announced, on `benchmarks/test_throughput.py`,
  `benchmarks/test_seekable.py` and `benchmarks/bench_pyarrow_tier1.py`
  against both the old class and the new path:
  - `S3PyArrowBackend` (D4): reads move from PyArrow's C++ S3 filesystem to
    the boto3 driver.
  - sync `AzureBackend` (D4): every sync Azure caller goes through
    `AsyncBackendSyncAdapter`, whose documented semantics (ADR-0025) differ
    from the sync class in four ways: `SEEKABLE_READ` is masked off, so a
    random-access read spools the blob instead of issuing one Range request
    per read as `_AzureRangeReader` does today; `open_atomic` is synthesised
    by spooling over `write_atomic`, so the streaming atomic write becomes a
    local spool plus one upload; a call from a thread with a running event
    loop raises `RuntimeError`, so sync `Store` over Azure stops working
    inside notebooks and `pytest-asyncio` tests; and `unwrap()` raises
    `CapabilityNotSupported` by default. The first two are what D1's
    `get_range` and `open_write` primitives exist to give back if D6 chooses
    a generated sync driver; the last two are the adapter's by design.
- **Risks:** a kernel defect is a regression on every migrated class at once.
  BUG-249 reached one class; its kernel equivalent reaches every driver.
  That is the price of applying a rule once, and it is bounded two ways: the
  kernel is checked against the Dafny oracle (D7) before the first migration,
  and D3 migrates one class per PR behind the unchanged suite. The second
  risk is the fake driver's reach: it exercises kernel × failure mode, not
  driver × wire semantics, so BUG-223's HNS probe, BK-316's non-OpenSSH
  shapes and S3's lack of a rename are driver defects the kernel's test
  cannot see, and the per-backend suites keep them.
- **Testing:** the kernel is tested once against a fake driver that can be
  told to raise any wire shape at any call, which is the kernel half of the
  cross-product the conformance suite could not reach (BK-345, ID-244, ID-251
  become moot for the kernel and reduce to driver cells); the driver half
  stays with the per-backend suites, as § Risks states. The conformance
  suite is unchanged and gates every migration in D3.
- **Effort:** kernel plus first three migrations L; D5 plus SFTP L; D4 M each.
- **What is deleted:** the 164 guard call lines and 22 per-class wrappers,
  most of the 395 `except` arms outside classifiers, two S3 classes, one
  Azure class, and most of BE-021's 496 lines, which become the kernel's
  docstrings.

**Acceptance criterion.** A count of guard lines or `except` arms on a
migrated class is satisfied by construction (a driver has no guard calls, and
an arm moved into `classify` leaves the count without leaving the code), so
the criterion measures outcomes instead. After D3 steps 1 to 3 are green:

1. **Contract coverage.** The fake-driver test covers every cell of the
   BE-021 row × public-operation matrix (six rows × the twelve-operation
   roster in § Reach, plus the never-leak invariant on every operation,
   listing page and stream), and the kernel over `MemoryDriver` answers
   every conformance cell exactly as `DafnyOracleBackend` does (D7). Both
   are enumerable and either passes or does not.
2. **Defect series.** For the two releases after step 3, cluster-A-shaped
   items (audit-021's definition, applied by the same by-hand reading and
   listed) filed against the migrated classes are counted per release and
   split kernel-owned / driver-kept as in § What each cluster-A bug becomes.
   The RFC is accepted if no kernel-owned item is filed against a migrated
   class in that window and the driver-kept count does not exceed the
   pre-migration series for those classes (audit-021 § Summary); it returns
   to Draft otherwise.

The guard-line and `except` counts (audit-021 commands (b) and (g)) are still
re-run and published with the result, as a description of what was deleted,
not as the criterion.

## Open Questions

1. **D6:** generated sync twin, or sync kernel with the adapter for async
   drivers? And if generated, does the generation reach the Azure driver too,
   which is the only way the four adapter regressions under § Impact are
   avoided for sync Azure callers? Decide before D3.
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
5. **Does the choke point cover driver construction?** BUG-245 leaks from
   `SQLBlobBackend`'s constructor, and BE-021's mapping rule is scoped to
   operations today. Either D2 wraps `Driver.__init__` too, or construction
   errors stay per driver and BUG-245 is fixed there.
6. **`classify` or a wire signal?** Ten of the 35 cluster-A items stay in
   the driver under D1 (§ What each cluster-A bug becomes). The wire-signal
   alternative under § Alternatives moves the mapping rows into the kernel
   at the cost of a primitive that must express every wire's vocabulary.
   Decide with D1, before the first driver is written.
7. **Is the kernel over `MemoryDriver` the verified reference?** D7 keeps the
   oracle outside the kernel. Whether the Dafny `MemoryBackend` model's
   refinement target moves from the hand-written `MemoryBackend` to the
   kernel is a formal-layer decision the `verify-formal` lane has to carry.

## References

- Audit: [audit-021](../audits/audit-021-contract-placement.md)
- Related specs: `sdd/specs/003-backend-adapter-contract.md` (BE-021, BE-029),
  `sdd/specs/005-error-model.md` (ERR-001, ERR-009),
  `sdd/specs/009-sftp-backend.md` (SFTP-010),
  `sdd/specs/022-streaming-atomic-writes.md`, `sdd/specs/026-health-check.md`,
  `sdd/specs/029-async-store-backend-api.md`, `sdd/specs/036-seekable-read.md`,
  `sdd/specs/037-depth-limited-listing.md`
- Formal layer: `sdd/formal/BackendContract.dfy`,
  `tests/backends/dafny/_helpers.py` (`DafnyOracleBackend`)
- Related ADRs: [ADR-0001](../adrs/0001-architecture-store-registry-backends.md),
  [ADR-0003](../adrs/0003-fsspec-is-implementation-detail.md),
  [ADR-0025](../adrs/0025-async-to-sync-backend-adapter.md),
  [ADR-0038](../adrs/0038-absent-container-outranks-drive-identity.md)
- Related RFCs: [RFC-0005](rfc-0005-code-deduplication.md) (the `_S3Base`
  extraction this generalises), [RFC-0003](rfc-0003-s3-pyarrow-read-optimization.md)
  (the C++ read path D4 retires)
- Related research: `sdd/research/research-bug-prevention-beyond-testing.md`
  (§ 4 deliverable 6, the unbuilt static check),
  `sdd/research/research-backend-contract-completeness.md`,
  `sdd/research/research-s3-boto3-poc.md` (ID-202)
- Related backlog: BK-366 (bug share undiagnosed), BK-345, ID-244, ID-251
- External: gocloud.dev `blob` driver interface; Rust `object_store` trait
