# ADR digest

<!-- doc: repo-only -->

Compiled from 31 ADR(s) by `scripts/gen_adr_digest.py`. Do not edit by hand; run `hatch run gen-adr-digest`.

## Accepted

### [ADR-0001](0001-architecture-store-registry-backends.md): Architecture - Store, Registry, Backends

Three-layer architecture:

1. **Store** — user-facing, immutable, folder-scoped. All operations use relative paths. Delegates all I/O to a backend. Thin wrapper with path scoping and capability gating.

2. **Registry** — owns backend lifecycle. Lazily instantiates backends from config. Shares backend instances across stores. Acts as context manager for cleanup.

3. **Backend (ABC)** — encapsulates all storage-specific behavior. Declares capabilities. Maps native errors to normalized types. Never exposed directly to end users.

```text
User → Store → Backend (ABC) → Local/S3/Azure/SFTP
         ↑
      Registry (lifecycle, config, factory)
```

### [ADR-0002](0002-config-resolution-no-merge.md): Configuration Resolution - No Merging

- **Config-as-code has absolute priority.** A `RegistryConfig` built in code
  is used exclusively, with no layering or merging between configuration
  sources. Chosen so the same code yields the same behavior regardless of host
  environment (determinism; test isolation from stray env vars). *Reverse if*
  determinism becomes a net liability: a first-class multi-source/override
  requirement emerges that user-side pre-processing genuinely cannot serve.
- **Environment variables are never read automatically.** The Registry performs
  no env-var fallback: constructing without a config yields an empty
  `RegistryConfig`, not an env-sourced one. Any env-var sourcing is explicit,
  user-side pre-processing (`resolve_env()`, Pydantic `BaseSettings`) that
  produces the final dict *before* construction; once the config is constructed,
  no further env lookups occur (spec 021 § CFG-021). *Reverse if* a built-in
  env-driven bootstrap is deliberately adopted (which also reopens the
  determinism decision above).
- **Backend defaults apply last, within a single config source.** "No merging"
  forbids combining across sources; it does not forbid a backend filling its
  unset options from its own defaults inside one source. *Reverse if*
  backend-default resolution moves out of config resolution.

### [ADR-0003](0003-fsspec-is-implementation-detail.md): fsspec Is an Implementation Detail

**fsspec is an implementation detail, never exposed in the public API.**

- **Backend adapters may use fsspec internally** (e.g. S3 via `s3fs`, Azure via
  `adlfs`), or boto3, paramiko, or raw stdlib. The implementor chooses; nothing
  in the public API reveals which.
- **The `Backend` ABC is our own contract, not fsspec's.** It does not extend or
  depend on fsspec. A separate ABC earns its maintenance cost because ours is
  deliberately stricter than fsspec's interface: capability-driven,
  error-normalized, streaming-first. That stricter contract is the reason to
  hide fsspec rather than re-export it.
- **Native handles stay reachable through a type-safe, explicit escape hatch**
  (`unwrap()`), so extensions that knowingly accept backend coupling keep full
  access without being forced onto the normalized surface. The `unwrap()` API
  contract lives in spec 003 § BE-022; this ADR owns only the decision to keep
  fsspec behind it.

*Reverse if* our ABC's stricter guarantees stop earning their cost: e.g. fsspec
gains equivalent capability negotiation and error normalization, so a separate
contract would duplicate the ecosystem rather than add over it.

### [ADR-0004](0004-empty-path-semantics.md): Empty Path Semantics in Store

Split path resolution in `Store` into two tiers:

- **`_full_path(path)` accepts `""` (and `"."`) as the store root.** Folder and
  query operations resolve an empty path to the store root instead of raising;
  non-empty paths still validate through `RemotePath`, so PATH-008 is untouched.
  *Reverse if* `RemotePath` is changed to accept `""` directly, making the
  second tier redundant.
- **`_require_file_path(path)` rejects `""` for file-targeted operations.** An
  empty path to a file operation is nonsensical, so it fails early with
  `InvalidPath` rather than reaching a backend. *Reverse if* any file operation
  gains meaningful root semantics (none exists today).
- **`delete_folder("")` is rejected even though it is a folder operation.**
  Deleting the store root is destructive and almost certainly unintended, so it
  is the deliberate exception to the folder-op accept rule and raises
  `InvalidPath`. *Reverse if* an explicit "empty the store" workflow is ever
  needed; that must be a distinct, guarded entry point, never a bare empty path.

The authoritative, per-method roster of which operations accept vs. reject the
root is spec-rate and lives in spec 001 § STORE-002, which tracks method
additions as the API grows.

### [ADR-0005](0005-native-path-resolution.md): Bidirectional Path Resolution via `to_key`

- **A `to_key` primitive at two levels, `Backend.to_key` and `Store.to_key`,
  same-named by design (clear intent, composable).** Both the broken listing
  round-trip and external-path conversion reduce to one operation: stripping a
  layer's own root. `Backend.to_key` strips the backend's native root/prefix;
  `Store.to_key` composes that with stripping `root_path` to yield a
  store-relative key. *Reverse if* a use case needs a path transform that is not
  root-stripping; then `to_key` is the wrong primitive, not merely
  under-featured.
- **`Backend.to_key` is a concrete ABC method with an identity default.** Only
  backends with a custom root override it; every other backend inherits the
  identity, so the change is zero-behavioral for them: the
  backward-compatibility invariant. *Reverse if* the identity default ever
  yields a wrong key for an un-overridden backend, which would mean the default
  is unsafe and the method must become abstract.
- **`to_key` is pure, deterministic, and total (no I/O, no side effects).** That
  purity is what makes a concrete default safe to inherit and lets the inverse
  round-trip hold. *Reverse if* a backend's native→key mapping genuinely
  requires I/O, breaking totality.
- **The Store owns the round-trip guarantee.** The Store layer strips
  `root_path`; backends only know their own root. The path-returning listing
  methods (`list_files`, `get_file_info`, `get_folder_info`) strip `root_path`
  so returned paths feed back into Store methods without double-prefixing;
  `list_folders` returns immediate subfolder *names* and is unaffected (spec 010
  § NPR-015). *Reverse if* backends must become root-aware for another reason,
  making a single Store-level strip point insufficient.

Exact signatures, per-backend stripping examples, the composition sequence, and
the full methods-that-strip enumeration are spec-rate and live in spec 010
(NPR-003, NPR-006/007/008, NPR-010/011, NPR-014/015).

### [ADR-0007](0007-docs-src-literate-nav.md): Three-Tier Documentation Architecture with docs-src/ and Literate Nav

##### A third content tier (supersedes ADR-0006)

Content lives in one of **three** tiers, chosen by its nature, replacing
ADR-0006's binary "source directory or build script" rule:

- **Source directories** (`README.md`, `guides/`, `sdd/`, `examples/`, `src/`):
  anything readable on GitHub without MkDocs.
- **`docs-src/`**: site-only authored prose with no standalone existence on
  GitHub, such as API-reference overviews, section landing pages, and example
  indexes. Version-controlled.
- **Build hook**: pure mechanics (scanning, template filling, link rewriting,
  nav assembly). No authored prose.

**Why the third tier:** ADR-0006's two-way rule left authored prose that only
makes sense inside the published site with no home, so ~100 lines of it were
trapped as Python string literals in the build script: undiscoverable, hard to
edit, hard to review. The tier exists to house exactly that category.

*Reverse if* site-only authored prose stops being a distinct category
(everything becomes either GitHub-readable source or pure mechanics),
collapsing back to ADR-0006's two tiers.

##### The placement rule

> Readable on GitHub without MkDocs goes in a **source directory**. Authored
> prose meaningful only as part of the docs site goes in **`docs-src/`**. Pure
> build mechanics go in the **build hook**.

The full content-type-to-location map is reference material owned by the
placement authority, [`AUTHORING.md`](../AUTHORING.md); this rule applies it
rather than restating it.

##### The build hook tier holds mechanism, never prose

The build hook replaced ADR-0006's monolithic script with a literate MkDocs
plugin stack that carries no authored content and no hand-maintained
navigation: section ordering lives beside the content in `_nav.yml`, not in a
central `nav:` block. The mechanism itself (plugin choices,
`_nav.yml`-to-`SUMMARY.md` assembly, link rewriting) is specified in
[spec 047](../specs/047-docs-framework-tooling.md) (DOCFRAME-001, DOCFRAME-007)
and pinned in `pyproject.toml`. This ADR fixes only the tier's boundary:
mechanics carry no authored prose.

*Reverse if* the "mechanics tier carries no authored content" boundary is
itself abandoned. The concrete mechanism is spec 047's to evolve; ADR-0027 has
since narrowed it to a single bridge.

> supersedes ADR-0006.

### [ADR-0008](0008-extension-architecture.md): Extension Namespace Contract (`ext.*`)

The `ext.*` namespace contract for stateless utility extensions: standalone
functions that accept a `Store` and operate on it. Framework concerns
(interfaces, hooks, lifecycle management, plugin discovery) are out of scope and
get their own ADRs when built.

- **Location.** Extensions live in `src/remote_store/ext/<name>.py` (single
  module) or `src/remote_store/ext/<name>/` (sub-package for complex ones);
  `ext/__init__.py` re-exports nothing, so each extension is imported directly.
  *Reverse if* a plugin-discovery mechanism (deferred) requires a registry in
  `__init__`.
- **Public API only.** Extensions use only the public `Store` / `Backend` API;
  private-attribute access (`store._backend`) is forbidden. `Store.unwrap(type_hint)`
  is the sanctioned escape hatch for native backend handles. *Reverse if* a
  required capability becomes impossible to express through the public API.
- **Module exports.** Every extension module defines `__all__`. *Reverse if*
  the project drops explicit export lists project-wide.
- **Lifecycle.** Extensions never own the `Store`: they must not close it or
  use it as a context manager. The caller owns lifecycle. *Reverse if* an
  extension legitimately needs to own a Store it constructs (a different
  pattern, warranting a new ADR).
- **Error propagation.** `CapabilityNotSupported` must propagate to the caller,
  never be suppressed, so callers see an honest capability boundary rather than
  a silent wrong result. *Reverse if* the capability model stops using
  exceptions to signal unsupported operations.
- **Zero-dependency core.** Core `remote-store` takes no third-party
  dependencies; optional deps are declared as extras in `pyproject.toml`.
  Extension code must guard optional-dependency imports (including inside
  `TYPE_CHECKING` blocks, which mypy still evaluates) rather than importing them
  unconditionally. This constraint is why the optional-dependency extension
  category exists at all. *Reverse if* the zero-dependency-core promise is
  abandoned.

##### Capability-probe exception pattern

`CapabilityNotSupported` MAY be caught in exactly one case: an extension
**probing for an optional native backend at initialization**, where a graceful
fallback exists (e.g. `ext.arrow` Tier 1 native fast-path falling through to
Tier 2/3 I/O). The catch must be narrowly scoped to the expected exceptions and
commented. This is the sole sanctioned exception to "must propagate," and it is
bounded to *optional* features with a fallback; a probe for a *required*
operation must still propagate. Any new extension using this pattern must cite
this section and document its fallback strategy in comments. *Reverse if*
capability probing moves to an explicit `supports()`-style API that removes the
need to catch.

The exact exception tuple, the `# noqa: BLE001` marker, and the concrete probe
live in the code (`ext/arrow.py`) and in spec `014-pyarrow-filesystem-adapter`
§ PA-001, which points here for rationale.

##### Deferred and relocated

- **Optional-extension re-exports.** Removed, superseded by **ADR-0013**.
  Optional-dependency extensions are imported from `remote_store.ext.<name>`,
  never re-exported from `remote_store.__init__`. Pure-Python extensions remain
  unconditionally exported.
- **Stateful patterns.** Hook/interceptor (`ext.notify`), proxy/wrapping
  (`ext.cache`), and context-manager streaming writes are not covered here; each
  is designed in its own ADR when the extension is built. The rules above
  (public API only, `__all__`, dependency guarding, error propagation) apply to
  all extension types.
- **Authoring pipeline, test location, third-party naming (`remote-store-<name>`),
  and plugin discovery** live in CONTRIBUTING § "Adding an Extension", the
  operational checklist. Entry-point discovery stays deferred until real
  third-party extensions exist.

### [ADR-0009](0009-glob-three-tier-design.md): Glob - Three-Tier Design

Three tiers of pattern matching, each covering a case the tier below cannot.
A single lowest-common-denominator API and a two-tier design were both
rejected: a bare `store.glob()` throws on most backends (a discoverability
pit), and simple name filtering should not require an extension.

- **Tier 1 (`list_files(pattern=…)`): `fnmatch` name filtering at the Store
  level.** Works on every backend with `LIST`, no new capability; covers the
  common "give me the CSVs in this folder" case. *Reverse if* every backend
  gains cheap recursive matching, collapsing the need for higher tiers.
- **Tier 2 (`store.glob(pattern)`): native backend glob, gated on
  `Capability.GLOB`.** Like `unwrap()`, opt-in direct access to a
  backend-specific feature for users who know their backend and want native
  semantics. The gate exists because native glob support is **unequal** across
  backends; only backends with a genuine native implementation declare `GLOB`
  (the current roster is spec-rate; see spec 018 § GLOB-005/018/019/020).
  *Reverse if* native glob becomes universal, making the gate meaningless.
- **Tier 3 (`ext.glob.glob_files(store, pattern)`): portable full recursive
  glob.** Delegates to `store.glob()` when `GLOB` is available, else falls back
  to `list_files` + client-side matching. This fallback is why the design is
  three tiers, not two: portable recursive glob cannot be guaranteed at the
  Store level. *Reverse if* a portable recursive glob can be guaranteed for
  every backend, letting Tier 3 fold into the Store API.

Pattern grammar, exact signatures, and the `fnmatch`/regex-converter mechanics
are spec-rate and live in spec 018 (Overview, GLOB-001, GLOB-005, GLOB-006,
GLOB-009, GLOB-014).

### [ADR-0010](0010-observe-proxy-pattern.md): Observe - Proxy Subclass Pattern

Use **Option A (proxy subclass)**: `ObservedStore(Store)` explicitly overrides
every public method, guarded by a **mandatory drift-protection test** (OBS-007)
that fails CI if any public `Store` method lacks an override.

- **Why a real subclass, not a `__getattr__` proxy (Option B).** An explicit
  subclass keeps `isinstance(observed, Store)` true, preserves static typing and
  IDE navigation, and keeps the instrumentation legible; a `__getattr__` wrapper
  auto-picks-up new methods but loses all three. *Reverse if* the maintenance cost
  of explicit overrides ever outweighs that benefit (for example, if `Store`
  grows large and volatile).
- **The drift test is what makes Option A viable.** Option A's one hazard is that
  a newly added `Store` method silently inherits the un-instrumented base and
  bypasses hooks; OBS-007 catches that at CI. The test is a hard requirement for
  any proxy subclass of `Store`, not an optional extra.
- **Named `ext.observe`, not `ext.notify`.** "Observe" describes the read-only,
  side-effect-free nature of the hooks; the factory is `observe()`. *Reverse if*
  the hooks ever gain interception or mutation semantics, at which point
  "notify"/"intercept" naming fits.

The `__dict__`-introspection mechanism of the drift test and the `observe()`
signature are spec-rate and live in [spec 019](../specs/019-ext-observe.md)
(OBS-002, OBS-007).

### [ADR-0011](0011-retry-per-backend-native.md): Retry - Per-Backend Native Configuration

Use **Option B: per-backend native retry configuration**, a `RetryPolicy` that
maps to each backend's own retry mechanism.

- **Retry is a transport concern, so backends own it.** Each backend translates
  one `RetryPolicy` into its native mechanism (SFTP tenacity, S3 botocore, Azure
  `ExponentialRetry`, S3-PyArrow both sides); Local and Memory reject `retry`
  because it is meaningless for local I/O. *Reverse if* a cross-cutting retry
  concern emerges that no single backend can own (e.g. mid-operation reconnect
  spanning backends).
- **The policy replaces SDK defaults rather than stacking on them,** so retries
  do not multiply. That was the flaw in Option A (a Store-level tenacity wrapper)
  and Option C (an `ext/` retry proxy), both of which compose on top of SDK
  retry. *Reverse if* a use case genuinely needs layered retry at two levels.
- **One configuration point: a single frozen dataclass and one constructor
  parameter.** `BackendConfig` carries it and the Registry merges it in, keeping
  the surface minimal and discoverable. *Reverse if* the single knob cannot
  express a required policy and users are pushed back to `client_options`.
- **No new core dependency.** `tenacity` stays confined to the `sftp` extra, not
  the zero-dependency core. *Reverse if* a core-level retry mechanism becomes
  unavoidable.

Application-level retry (mid-operation reconnect, idempotency checks) is out of
scope, and could later be a composing `ext/retry.py` middleware.

The `RetryPolicy` fields and defaults, the `disabled()` factory, the per-backend
SDK mappings, the Local/Memory `TypeError`, and the `BackendConfig`/`from_dict`
wiring are spec-rate and live in [spec 025](../specs/025-retry-policy.md)
(RET-001, RET-003, RET-004 through RET-006, RET-010 through RET-014).

### [ADR-0012](0012-async-store-backend-api.md): Async Store / Backend API — Hybrid Model

Use **Option C (Hybrid)**: `AsyncBackend` ABC + `SyncBackendAdapter` +
`AsyncStore`.

1. **Separate async types.** `AsyncBackend` (ABC) and `AsyncStore` are distinct
   from `Backend` and `Store`, with no shared base, because they serve separate
   use cases (the httpx `Client`/`AsyncClient` pattern). *Reverse if* a shared
   base removes more duplication than the type separation costs.

2. **Auto-wrapping.** `AsyncStore` accepts both an `AsyncBackend` and a sync
   `Backend`, auto-wrapping the latter via `SyncBackendAdapter`, so async users
   get immediate value with existing backends and no manual wrapping. *Reverse
   if* implicit wrapping hides a correctness or performance cost that an explicit
   wrap would surface.

3. **`read()` returns `AsyncIterator[bytes]`.** There is no standard
   `AsyncBinaryIO` in Python, and `AsyncIterator[bytes]` is the idiomatic async
   streaming shape (httpx, aiohttp); `read_bytes()` stays the `bytes`
   convenience. *Reverse if* a standard async binary-file protocol emerges.

4. **`asyncio` only, no anyio or trio.** Chosen for simplicity (fewer
   abstractions, easier debugging), not dependency cost; the async audience
   already has anyio transitively. *Reverse if* a supported runtime needs
   trio/anyio semantics asyncio cannot express (a non-breaking change).

5. **Non-I/O methods stay sync.** Operations with no I/O have no reason to be
   async. *Reverse if* one gains an I/O dependency.

6. **Phased rollout.** Phase 1 ships the core surface, Phase 2 native async
   backends, Phase 3 async extensions, each with its own spec. *Reverse if*
   delivering the surface whole beats staging it.

7. **Zero new runtime deps in Phase 1.** Phase 1 uses only stdlib `asyncio`,
   preserving the core's zero-dependency floor; optional async deps (asyncssh)
   arrive as Phase 2 extras. *Reverse only* by deliberately abandoning the
   zero-dependency-core promise.

The `aclose()` naming and wiring, the exact non-I/O method roster, and the
`read_bytes` contract are spec-rate and live in
[spec 029](../specs/029-async-store-backend-api.md) (ASYNC-007, ASYNC-020,
ASYNC-022, ASYNC-023, ASYNC-034). `SyncBackendAdapter`'s iterator materialization
is a realized consequence of auto-wrapping, covered under Consequences.

### [ADR-0013](0013-drop-optional-extension-reexports.md): Drop Optional-Extension Re-exports from `__init__.py`

Remove the conditional `try/except ImportError` re-export blocks for all
optional-dependency extensions (`arrow`, `otel`, `pydantic`, `yaml`) from
`remote_store/__init__.py` and `__all__`. Each `try` block eagerly imports the
extension and its dependency at `import remote_store` time (Dagster alone costs
~2-5 s), penalising users who never call it, and no source, test, or example
imports these symbols from the top level.

Users import optional extensions from their canonical module path, e.g.
`from remote_store.ext.arrow import pyarrow_fs`. This makes every
optional-dependency extension consistent, including dagster, which already used
this pattern. The full removed-symbol list is in the CHANGELOG "Removed" entry.

*Reverse if* top-level convenience imports are wanted back: a module-level
`__getattr__` in `__init__.py` (Python 3.7+) can expose the symbols lazily
without the eager-load cost, rather than re-introducing the `try/except`
pattern.

This amends only ADR-0008's export rules; the rest of ADR-0008 (public-API-only,
`__all__`, lifecycle, error propagation, dependency rules) remains in effect.

> amends ADR-0008 (clause).

### [ADR-0014](0014-middleware-path-1-proxy-store-stream-wrappers.md): Middleware Architecture — Path 1 (ProxyStore + Stream Wrappers)

**Choose Path 1: a `ProxyStore` delegation base plus stream-level wrappers,
not a middleware framework (Path 2).** `ProxyStore` centralizes the
private-attribute coupling (`_backend`, `_root`, `_owns_backend`) and default
delegation shared by `ObservedStore` and `CachedStore`; subclasses override
only the methods they intercept. Progress and checksums ship as `BinaryIO`
wrappers (`ext.streams`) and pure functions (`ext.integrity`), never as Store
proxies. *Reverse when* a third policy-like proxy must compose (see the
migration triggers below); the Path 1 → Path 2 refactor is internal-only and
breaks no public API, so it is safe to defer rather than build speculatively.

**Why Path 1, not a dispatch framework**

- **Only observe + cache compose today.** Retry already ships as per-backend
  native config (ADR-0011, `RetryPolicy`); circuit-breaker, rate-limiting, and
  fault-injection are post-v1 with no committed timeline. Two wrappers do not
  justify dispatch machinery.
- **Progress and checksums are stream concerns, not Store concerns.** A
  `BinaryIO` wrapper composes with any stream, needs no Store wrapping, and
  correctly skips cache hits (no stream to wrap).
- **No breaking changes.** `observe()` and `cached_store()` keep their
  signatures and return types; `ProxyStore` is a base class, not a new public
  surface.

**Scope: what Path 1 delivers**

- `ProxyStore` internal base (`_proxy.py`) with a `_wrap_child()` hook.
- New `ext.streams` (progress + checksum `BinaryIO` wrappers) and `ext.integrity`
  (pure checksum/verify functions). The exact class list and per-symbol
  contracts are owned by specs `033-ext-streams` and `034-ext-integrity`.

**Scope: what Path 1 excludes (the boundary against Path 2)**

- No `ProgressStore`/`ChecksumStore` proxies; no before/after/short-circuit
  hooks; no category dispatch, middleware merging, or public middleware API.
- No `Store.read()`/`write()` signature changes for progress or checksums.
- No data-model change (`ContentDigest`, `FileInfo.digest`/`etag`), deferred
  to ID-008.

**ProxyStore contract**

`ProxyStore(Store)` is a delegation base: it adopts the inner store's backend
coupling, delegates every public `Store` method to its inner store by default,
and propagates `child()` through `_wrap_child()`, which subclasses must
implement (the base raises). Construction, delegation, and `_wrap_child()`
mechanics are owned by `src/remote_store/_proxy.py`; the ADR-0010
drift-protection tests hold delegation to the full `Store` surface. *Amended by
ADR-0015:* the original "internal, must not be subclassed by user code" clause
is superseded; `ProxyStore` is now exported and documented so extension
authors can subclass it.

**Migration trigger for Path 2 (reverse this decision when any becomes true)**

- three or more store-level concerns must compose on one operation path;
- wrapper ordering becomes product-significant, not merely internal;
- one concern must short-circuit another in a general way;
- adding a concern would again require broad override duplication.

### [ADR-0015](0015-proxystore-publicly-documented.md): Document ProxyStore in the Public API Reference

- **Export `ProxyStore` from `remote_store` and document it in the API
  reference.** It remains an internal delegation base by design, centralising the
  private-attribute coupling (`_backend`, `_root`, `_owns_backend`) and default
  delegation; it is not a middleware framework and gains no new hooks or dispatch
  machinery. This documents a surface users already see (in the `ObservedStore` /
  `CachedStore` class hierarchy) and that extension authors already need, while
  adding no new API. *Reverse if* a real hook/dispatch surface is ever needed
  (ADR-0014's Path-2 migration), at which point this document-only decision
  reopens and the public contract is redesigned.

The rest of ADR-0014 (delegation model, `_wrap_child()` hook, stream wrappers,
integrity functions, migration trigger for Path 2) remains in effect.

> amends ADR-0014 (clause).

### [ADR-0017](0017-seekable-read-on-store-api.md): Seekable Read on Store API

Add `read_seekable()` to `Backend` and `Store` as a concrete (non-abstract)
method alongside `read()`, superseding ADR-0016's `ext.seekable` approach.

- **A first-class method, not an extension.** Consuming abstractions that control
  the read path (PyArrow's `FileSystem`, Dagster's `IOManager`) will not call an
  extension function, so seekability has to live on the Store/Backend surface to
  reach them at all. *Reverse if* those abstractions gain a way to consume an
  extension helper directly, removing the need for a built-in method.
- **The default spools; backends may override for true random access.** The
  default delegates to `read()` and spools a non-seekable stream into a
  `SpooledTemporaryFile`; a backend like Azure overrides to return a range reader
  that maps each seek+read to a single HTTP Range request. This is the tension
  `ext.seekable` could not resolve: whole-file spooling defeats the byte-saving
  that random access exists for. *Reverse if* one read path can serve both
  sequential and sparse-random access without a per-backend override.
- **`ext.seekable` is removed (never released) and `SEEKABLE_READ` shifts
  meaning.** Its whole-file-spool behaviour is subsumed by the default; the
  capability now signals that `read_seekable()` is zero-overhead (the backend
  natively returns seekable streams), still useful for branching at setup time.
  *Reverse if* the original "`read()` returns seekable" meaning is needed again.

Exact signatures, the spool mechanic, the `_AzureRangeReader` override, Store
delegation, the Arrow call site, and the `ProxyStore` cascade are spec-rate and
live in [spec 036](../specs/036-seekable-read.md) (SEEK-002, SEEK-003, SEEK-005,
SEEK-006, SEEK-008, SEEK-009). A future `HttpBackend` Range implementation is
noted in Consequences.

> supersedes ADR-0016.

### [ADR-0018](0018-sqlalchemy-two-class-architecture.md): SQLAlchemy Backend — Two-Class Architecture with Shared Base

**Option B: two concrete backends over a shared private base.**

```
_SQLAlchemyBaseBackend(Backend)   # private, not exported
├── SQLBlobBackend                # v1, full read-write KV store
└── SQLQueryBackend               # v2, read-only query materializer
```

- **Two classes, not one `mode` flag.** The blob and query use cases have
  fundamentally different invariants (read-write vs read-only), capability sets,
  and dependencies (`[sql]` vs `[sql-query]`); a `mode="blob"|"query"` parameter
  would spread `if mode == ...` branching through every method. *Reverse if* the
  two use cases converge on one invariant set and dependency footprint.
- **A shared base, not two independent classes.** `_SQLAlchemyBaseBackend`
  centralises engine lifecycle, health check, error mapping, and SQLite
  detection, avoiding Option C's duplication while each subclass keeps its own
  Backend contract and evolves independently. *Reverse if* the shared surface
  shrinks to near nothing, making the base pure indirection.
- **The base is private.** It is not exported or documented for users, so it
  stays free to evolve. *Reverse if* third parties need to subclass it to build
  their own SQL backend.

The engine `url`-vs-`engine` (owned vs borrowed) lifecycle and the virtual
prefix-based folder model are spec-rate and live in
[spec 040](../specs/040-sql-blob-backend.md) (SQL-BLOB-001, SQL-BLOB-025,
SQL-BLOB-041, SQL-BLOB-061).

### [ADR-0020](0020-orchestrate-iterative-convergence.md): Orchestrate Iterative Convergence Model

**Adopt an iterative convergence model, replacing the single-pass model.**
Planning, execution, and post-processing are wrapped in feedback loops (plan
refinement before execution, result consolidation after, and expert
cross-review), so experts act on each other's *actual output*, not the plan
alone. That gap is what single-pass could not close for coupled, multi-domain
work. *Reverse if* the loops stop catching cross-domain mismatches that
single-pass missed, so the loop overhead no longer pays for itself.

**Gate loop depth on task complexity, via three modes (Simple / Standard /
Complex).** Trivial single-domain work runs plan → execute → review with no
refinement or consolidation; multi-domain work adds both; ambiguous or
tightly-coupled work additionally requires user confirmation before executing
and before each review round. The loops *are* the model's cost, so trivial
tasks must be able to opt out of them. The orchestrator picks the mode; the
user overrides. *Reverse if* one mode serves in practice (collapse the tiers)
or a failure class appears that the three do not cover.

**Bound review to a fixed maximum number of rounds; the user resolves anything
still open after the cap.** A hard round cap guarantees termination instead of
unbounded convergence. *Reverse if* the cap routinely discards unresolved real
issues rather than surfacing them to the user.

**The user is the sole tie-breaker.** The orchestrator presents expert
disagreements and waits; it never adjudicates them autonomously, keeping a
human as final authority on contested changes. *Reverse only* as a deliberate
authority change (if orchestration is ever trusted to resolve domain conflicts
without a human), never as a tuning tweak.

**Carry forward ADR-0019's delegation structure; replace only its control
flow.** Domain-expert delegation, per-domain boundaries and foundation docs,
orchestrator-owned cross-domain files (CHANGELOG, BACKLOG, README), and bug-fix
TDD ordering (Testing Expert first) are unchanged. *Reverse per those
mechanisms' own records* (ADR-0019 and its amendments) if the delegation
structure itself is revisited.

The concrete step sequence, per-mode flow, consolidation status legend, exact
round cap, expert-response format, and the current expert roster are
operational contract, not decision rationale. They live in the `/orchestrate`
skill (`.claude/skills/orchestrate/SKILL.md`) and the persona files
(`.claude/agents/`), which are edited when the process is tuned.

> supersedes ADR-0019.

### [ADR-0021](0021-graph-sdk-choice.md): Microsoft Graph SDK Choice — `httpx` + `msal`

- **Build on `httpx` + `msal`.** Use `httpx`'s async client for the HTTP
  transport and `msal` for token acquisition and cache serialization.
  `httpx` is already an optional runtime dependency, and `msal` is
  Microsoft's supported, lightweight auth library.
- **Hand-written REST surface.** Construct an `httpx.AsyncClient`
  internally and treat Graph as a narrow REST surface with hand-written
  request helpers, pagination, and error mapping.
- **Reject `msgraph-sdk`.** Adopting an SDK adds transitive weight (the
  Kiota runtime plus `azure-identity`) without removing the hard parts the
  backend must hand-write against this narrow surface regardless:
  resumable uploads, async-operation polling, mid-read URL refresh.
  **Reverse** if the backend later grows to a materially broader Graph
  surface (mail, calendar, groups), where the SDK's coverage would start
  to earn its weight.
- **`Office365-REST-Python-Client` out of scope.** Legacy SharePoint
  REST is not a goal (RFC-0010).

### [ADR-0022](0022-graph-auth-model.md): Microsoft Graph Auth Model — Dual Flows Behind a Token-Provider Protocol

The backend authenticates through a **token-provider callable**, not a
concrete auth class. The decisions:

- **Token-provider callable, two shapes.** The backend accepts
  `Callable[[], str]` (sync) or `Callable[[], Awaitable[str]]` (async)
  and never couples to MSAL through its constructor. Users who obtain
  tokens another way (managed identity, corporate broker, custom refresh)
  supply their own callable. **Reverse** (via a new ADR) only if the
  backend needs auth features a bare token-returning callable cannot
  express — per-request scope selection, token metadata, or tight MSAL
  coupling.
- **Built-in `GraphAuth` helper.** Wraps MSAL and exposes both callable
  shapes, covering two flows: **client-credentials** (app-only,
  admin-consented `Files.ReadWrite.All` / `Sites.ReadWrite.All`) and
  **device-code** (delegated, interactive). GR-006 / GR-007 specify each
  flow's config fields.
- **Lazy invocation.** The provider is called on first request and once
  more on a `401 InvalidAuthenticationToken` (one-shot refresh + retry,
  GR-029); the backend caches no token. Callers who bring their own
  provider load none of `msal` / `msal-extensions` / `platformdirs`.
- **Credential masking on two surfaces.** `client_secret` is a `Secret`
  (masked in `__repr__`) and auto-wrapped from config via
  `_SENSITIVE_KEYS`; the `Authorization` bearer is redacted from logs and
  never enters exception text. Mechanisms: GR-035, SEC-003 / SEC-004 /
  SEC-007.
- **Config-built backends get a default `GraphAuth`.** The registry
  builds one from static config (ADR-0001); user-supplied callables are
  expressible only through direct construction. The `graph` extra's pins
  live in `pyproject.toml` (ADR-0021 records the SDK choice).

##### Token cache: why `PersistedTokenCache`

`GraphAuth` persists the MSAL cache through
`msal_extensions.PersistedTokenCache` (a cross-process lock plus a
dirty-read retry, no atomic rename) and wraps it to swallow-and-log
persistence failures, so a cache error degrades to re-acquisition rather
than breaking an in-flight `read` / `write`. Two facts a reviewer needs
to keep or reverse this choice:

- It replaced a hand-rolled `SerializableTokenCache` + truncate-at-open
  flush, under which a concurrent reader could observe a torn cache and
  be forced to re-login (BK-291).
- A bare temp-file + `os.replace` was rejected because on Windows
  `os.replace` raises `PermissionError` (`WinError 5`) when the
  destination is held open by a concurrent reader; the
  lock-plus-read-retry design sidesteps rename entirely.

The cache path, override rules, and the multi-process-safety contract are
specified by GR-007; the persistence mechanism itself lives in
`_graph/auth.py`.

### [ADR-0023](0023-async-monitor-polling.md): Async Monitor-URL Polling — Backend-Local in `_graph`

- **Ship the poller backend-local.** Put the polling logic in
  `src/remote_store/aio/backends/_graph/monitor.py` (inline in
  `backend.py` if it stays small). It lives under `aio/backends/`
  because the Graph backend is async-native (matching
  `aio/backends/_azure.py`).
- **Not a shared facility (YAGNI).** No second `202`-monitor consumer
  exists today: same-account Azure copy completes server-side without
  polling, and S3 multipart completion uses a different shape (not a
  monitor URL). **Reverse** only when a second backend genuinely needs
  the same shape, measured in a follow-up rather than predicted here; a
  hoisting ADR then supersedes this one.
- **Parser-driven shape.** The poller takes a `status_parser` mapping
  each poll response to `pending` / `succeeded` / `failed`, so the loop
  is already shaped for a second consumer without being a generic helper
  today. Cadence and timeout defaults are the spec's (GR-026).
- **No Store capability.** A capability such as `ASYNC_COPY` would leak
  an implementation detail into the public API and invite callers to
  branch on "is this copy asynchronous?", the wrong question.
  `Store.copy()` is synchronous from the caller's view (ADR-0012); the
  backend presents that result regardless of how it gets there.
- **Not in `ext/`.** Extensions use only the public Store/Backend API
  (ADR-0008); the poller operates on raw HTTP, takes an
  `httpx.AsyncClient`, and serves only the backend implementer.

### [ADR-0024](0024-resource-locked-error.md): `ResourceLocked` Error Type

Add `ResourceLocked` as a new concrete error type. The decisions:

- **A new type, not a reuse.** None of the existing errors fit HTTP
  `423`: the caller is authorised (not `PermissionDenied`), it is not a
  write conflict (not `AlreadyExists`), the backend is reachable (not
  `BackendUnavailable`), and generic `RemoteStoreError` loses the
  actionable "locked now, may clear" signal.
- **Flat under `RemoteStoreError`.** One level deep, no intermediate
  category (ERR-008).
- **`path` + `backend` only; no `lock_owner`.** Graph does not surface
  the lock holder and no other backend emits this today, so a
  speculative field is dropped (no-speculative-API rule). **Reverse
  (widen the class)** only when a backend genuinely surfaces the holder,
  via a covering spec amendment — ERR-013 points back here for exactly
  this reasoning.
- **Terminal; caller-driven retry.** Not retried by the default policy
  (RET-015); callers choose their own cadence.
- **Reusable across backends.** Future equivalents — SharePoint
  check-out, SMB lock conflicts, WebDAV `423` — map to the same type;
  that reuse is why this is a canonical error, not a Graph-local one.
  Graph's `423 resourceLocked` is the only mapped source today (GR-045
  owns the mapping).

### [ADR-0025](0025-async-to-sync-backend-adapter.md): Async-to-Sync Backend Adapter (`AsyncBackendSyncAdapter`)

Introduce `AsyncBackendSyncAdapter`, a class implementing the sync `Backend` ABC
by delegating to a wrapped `AsyncBackend` that runs on a private event loop in a
dedicated daemon thread (**Option D** of the four weighed in Context). It mirrors
`SyncBackendAdapter` (ADR-0012); together they form the full bidirectional bridge
the hybrid model needs.

**Private loop on a dedicated daemon thread, not `asyncio.run()` per call and not
`nest_asyncio`.** `asyncio` forbids re-entering a running loop, and a fresh loop
per call forfeits the async SDK's connection pools and auth-token cache; a
per-adapter private loop keeps the client alive while sync callers submit
coroutines via `run_coroutine_threadsafe` and block on the returned `Future`.
*Reverse if* the stdlib gains safe nested-loop execution, or the wrapped backends
stop needing cross-call client reuse.

**Two distinct adapters, not one parameterised bridge.** The two boundary
directions differ enough that two named classes read clearer than one flag-driven
bridge. *Reverse if* a single parameterised bridge proves clearer in practice.

**The module lives in the sync core (`src/remote_store/_async_to_sync_adapter.py`),
not under `aio/`.** It implements the sync `Backend`, so it belongs with sync
code; placing it under `aio/` would force every sync `Store` user wrapping an
async backend to import the `aio/` runtime at construction, inverting the
invariant that sync code stays independent of `aio/`. `AsyncBackend` is imported
lazily in `__init__` to keep that core-to-`aio` edge off the top level. *Reverse
if* the sync-independent-of-`aio/` layering invariant is abandoned.

##### Ownership model

One private loop and one daemon thread per adapter instance, never shared or
reused; the adapter is a **one-shot resource**, so a closed adapter raises rather
than restarting the loop. Concurrent sync callers are serialised onto the single
loop, which *manufactures* thread-safety for a loop-safe async backend;
**ordering between concurrent callers is not guaranteed**, so callers needing
order coordinate externally. *Reverse if* a backend needs multi-loop parallelism
one serialising loop cannot give. Exact concurrency bounds and no-crossover
guarantee: spec 029 § ASYNC-089.

##### Streaming iterators and open streams

`read()` and the listing iterators **pump chunks lazily across the boundary and
never materialise** the full stream or listing, since native-async backends exist
to stream and the sync wrapper preserves that. The rule is **at most one
outstanding `__anext__` per stream/iterator** (no read-ahead), the only
per-stream buffer being the unread tail of the last chunk. *Reverse if* a wrapped
backend cannot stream, making materialisation unavoidable. Exact
`BinaryIO`/short-read surface and buffer mechanics: spec 029 § ASYNC-080,
ASYNC-081.

##### Write-side content

The bridge runs **sync `BinaryIO` to `AsyncIterator[bytes]`** (the sync side has
no iterator-of-bytes input), pulling the `BinaryIO` via `asyncio.to_thread` so
the loop never blocks on the caller's file object. **`open_atomic` is synthesised
over the backend's `write_atomic`** (spool, flush on clean exit, drop on error)
rather than adding an `open_atomic`-shaped op to `AsyncBackend`, keeping the async
ABC unchanged and leaving Graph (ID-127) nothing new to implement. The
`ATOMIC_WRITE` gate is enforced by the wrapped backend. *Reverse if* a backend
needs a native incremental async atomic write. Exact spool/flush and
mid-write-failure semantics: spec 029 § ASYNC-085, ASYNC-091.

##### Behaviour when the caller is in a running loop

**Fail fast:** invoked from a thread with a running loop, a blocking method
raises `RuntimeError` pointing the caller to `AsyncStore`, keeping the sync
contract genuinely sync and preventing deadlock (per ADR-0012, sync `Store` is
not coroutine-safe by design). **No `nest_asyncio` in v1**, which would
monkey-patch global `asyncio`; the adapter neither imports nor depends on it.
*Reverse if* notebook/GUI demand justifies an explicit opt-in mode, which ships
behind its own flag and its own ADR. Exact detection point and message stem:
spec 029 § ASYNC-082.

##### Capability translation

The adapter **translates** the wrapped `CapabilitySet` rather than
blind-forwarding it: **`SEEKABLE_READ` is masked off** because the chunk-pull
stream is forward-only (random-access callers fall through to `read_seekable`'s
spool, as every non-seekable sync backend already does); `LAZY_READ` and the rest
pass through unchanged. **`unwrap()` raises `CapabilityNotSupported`** by default
because an async handle bound to the private loop is unsafe from the caller's
thread, unless the backend exposes a sync-safe handle. *Reverse if* a native
async seekable-read op is added, letting `SEEKABLE_READ` pass through. Exact
translation/gating table and unwrap exemption: spec 029 § ASYNC-084, ASYNC-086.

##### Lifecycle

`close(timeout=30.0)` drains in-flight tasks, stops the loop, and joins the
thread within a bounded timeout (default matches the per-backend network
ceilings; `None` waits forever; on expiry it logs a `WARNING` and lets the daemon
thread be reaped at process exit); `__enter__`/`__exit__` delegate to it.
**Errors cross verbatim:** no wrapping or translation, so error types and the
ERR-001 `path`/`backend` attributes (spec 005) reach the sync caller unchanged;
`check_health()` is likewise not a no-op and does not swallow the backend's probe
errors. **Cancellation is best-effort:** `Future.cancel()` only requests
`Task.cancel()`, observed at the next `await`, so `close()` drains before
stopping; `KeyboardInterrupt` is not special-cased, because KI-to-cancel would
give this one backend behaviour no other sync backend has. **No per-call
timeout:** per-operation timeouts are the wrapped backend's responsibility;
`close()` is the only global bound. *Reverse if* per-operation cancellation or
timeout becomes a cross-backend contract. Exact drain order, message stems, and
failure-mode semantics: spec 029 § ASYNC-083, ASYNC-087, ASYNC-088, ASYNC-090,
ASYNC-092, ASYNC-093.

##### Store-level wiring

The sync `Store` gains a construction path that auto-wraps a supplied
`AsyncBackend` in this adapter, mirroring `AsyncStore`'s auto-wrap of a sync
`Backend`. The adapter is backend-agnostic; Graph registry integration lives in
spec 044. *Reverse if* the auto-wrap convenience is removed from the `Store`
constructor.

### [ADR-0026](0026-strict-gate-on-kwarg.md): Strict-Gate Pattern for Optional Capability Kwargs

An optional kwarg that requests a specific backend capability MUST raise
`CapabilityNotSupported` **before any I/O** when the backend does not declare
that capability. Never silently drop the kwarg: a silent drop turns a caller's
durability assumption (correlation IDs and idempotency tokens carried in
`metadata=`) into an untraceable correctness failure discovered later, in a
different service, with the explaining context already gone. *Reverse if* a
future consumer class treats such a kwarg as purely advisory with no downstream
correctness dependence; then silent degradation, not a raise, becomes the
defensible default.

**Strict gate on kwarg (the pattern).** A capability is a *strict gate on
kwarg* when it:

1. does not gate the method, which works without the kwarg;
2. gates one optional argument, so supplying it requires the capability;
3. is enforced once, at the Store layer (not per backend), raising
   `CapabilityNotSupported` before any I/O when the capability is absent and
   the argument is supplied.

`USER_METADATA` gating `metadata=` on `write*()` is the first instance. The
live registry of strict-gate capabilities is CAP-007 (spec 003); each
instance's per-backend contract lives in its feature spec (e.g. WR-010). A new
instance is added by declaring a capability, gating its kwarg at the Store
layer, and registering it in CAP-007, with no new enforcement site. *Reverse if* a
gated argument becomes universally supported across backends; then the gate for
that capability is removed rather than relocated.

### [ADR-0027](0027-docs-bridge-single-mechanism.md): Single Bridge with Enforcement, Not Layered Mechanisms

One documentation bridge, kept single by an enforcement gate. Three coupled
sub-decisions, each stated once:

- **One bridge, by construction.** A single source-discovery function and a
  single render function carry all dual content; other discovery and render
  helpers are removed, not deprecated. New content shapes extend this one
  mechanism instead of adding a parallel one. The function names and the removal
  set are owned by [spec 047](../specs/047-docs-framework-tooling.md)
  (DOCFRAME-001, DOCFRAME-005). *Reverse if* a content shape genuinely cannot be
  served by extending the single bridge, forcing a second mechanism.
- **Classification next to the file, not in a manifest.** Each `.md` declares its
  class via an HTML-comment marker, with a directory-default fallback (per
  [`AUTHORING.md`](../AUTHORING.md) Rule 1); a file with no marker and no default
  is unclassified and fails the gate. The marker cannot drift from the file
  because it is part of it, unlike a central manifest that lives apart from what
  it classifies. Marker contract: spec 047 (DOCFRAME-002). *Reverse if* structured
  per-page metadata is ever needed that an HTML comment cannot carry (moving to
  YAML frontmatter, per Alternatives).
- **Enforcement at PR time.** A check script fails the build if any framework
  rule is violated, including the "one bridge" rule itself. This is the half the
  prior ADRs (0006, 0007, BK-167) left out: without a check that detects the
  second bridge, "use one bridge" silently degrades to a preference, which is
  exactly how the accumulation happened. Gate contract: spec 047 (DOCFRAME-004).
  *Reverse if* the one-bridge rule itself is retired.

### [ADR-0028](0028-testing-architecture-kind-stage-replay.md): Testing Architecture with Kind and Stage Axes and HTTP Replay Demotion

The testing architecture rests on five coupled commitments. They share one
rationale: the demotion mechanism works only because the axes are separated, the
gate works only because gating is native, and the scope holds only because the
spec calls out where it does not apply. One ADR captures the bundle; any
commitment that later evolves can be superseded individually. Spec contracts live
in [spec 048](../specs/048-testing-architecture.md).

- **Two orthogonal axes: kind and stage.** Separate *what a test wires up* (kind:
  pure, mocked, real-local, real-live) from *how expensive it is to run* (stage:
  1/2/3 by cost); a fixture declares one of each. A single linear stage list
  collapses the two and hides real options, notably replay: a real-SDK code path
  that runs at Stage 1 cost, which no single-axis ordering can express (TEST-001).
  *Reverse if* a single axis ever expresses every kind/cost combination in use.
- **Conformance as the cross-backend spine.** One parametrised suite over the
  public `Store` / `Backend` API that every backend runs, so "add a backend, get
  conformance for free" is the literal mechanism; backend-specific behaviour is
  isolated to that backend's own home, not interleaved with the spine (TEST-002,
  TEST-003, TEST-010). *Reverse if* the public API stops being a sufficient
  cross-backend contract.
- **HTTP cassette and replay as a Stage 1 fixture.** A `<backend>_replay` fixture
  runs the real SDK path against a recorded cassette (Stage 3 records, Stage 1
  replays), demoting a Stage-3-discovered behaviour to zero-cost CI. Scoped to
  HTTP-transport backends only: SSH-binary and DB-wire protocols are not reachable
  by available capture tools without a custom transport adapter, so their cheapest
  source of truth stays Stage 2 with no demotion path (TEST-007, TEST-008).
  *Reverse if* a capture mechanism for non-HTTP transports becomes worth its cost.
- **Capability gating via native pytest.** Parametrize id-filtering plus
  `pytest.mark.skipif`, with no custom `@requires` marker layer, so a reader
  traces from the parametrize call to the fixture registry without a plugin hook.
  The cost is verbosity in a few helpers; the cost avoided is a parallel marker
  system with its own conftest hook, docs, and IDE integration (TEST-005).
  *Reverse if* native gating can no longer express the capability matrix.
- **Explicit cassette refresh.** Cassettes regenerate only when a developer runs
  `pytest --stage=3 --record` and commits the diff; CI never silently re-records.
  Scheduling a refresh from day one would couple the cost-controlled tier to a
  recurring job before any empirical drift data exists; a scheduled job is
  additive later if drift becomes painful (TEST-009). *Reverse if* observed drift
  makes manual refresh unreliable.

### [ADR-0029](0029-graph-transfer-blocking-io-offload.md): Offload Graph Transfer Spool I/O off the Event Loop

Dispatch the Graph transfer's blocking spool file I/O off the event loop via
`asyncio.to_thread`, on both the read-path range fallback and the write-path
unknown-length upload. The spool objects are accessed sequentially under `await`,
with nothing else holding the reader concurrently, so single-threaded offload is
safe. *Reverse if* a spool ever gains a concurrent reader: the sequential-access
invariant that makes single-threaded offload safe would no longer hold.

The exact spool methods and per-operation thread hops are code-level and live in
`transfer.py`, with the spool contracts in [spec 044](../specs/044-graph-backend.md)
§ GR-015 (range-fallback spool) and § GR-019 (upload-session spool).

> amends ADR-0025 (clause).

### [ADR-0030](0030-azure-hns-explicit-declaration.md): Azure HNS Is an Explicit Declaration, Not Auto-Detected

**HNS status is a mandatory, explicit declaration, never auto-detected.** Both
`AzureBackend` and `AsyncAzureBackend` take a required `hns: bool` (no default);
`_hns` is set once from it, with no probe, cache, warn-once state, or
per-operation snapshot.

- **Why mandatory rather than a detected default.** The account's HNS status is a
  fixed, deployment-time fact, but the old `GetAccountInfo` probe *guessed* it at
  runtime from a network call that can fail, return stale authorization state
  (e.g. an RBAC-propagation `403`), or be denied by least-privilege credentials.
  That produced sticky misdetection, per-operation re-probe storms, and torn
  reads mid-operation. A declared value cannot fail, so the one-time cost of
  stating a known fact buys removal of the entire failure class and determinism
  from construction. The value must be a real `bool`, not a truthy/falsy proxy,
  because config env-var resolution yields strings and a `"false"` placeholder
  would otherwise coerce to `True` and silently re-enable HNS. *Reverse if* a
  deployment-time-reliable, authorization-independent way to detect HNS emerges.
- **Discovery stays available, but only when asked, and fail-loud.**
  `AzureUtils.detect_hns()` / `adetect_hns()` issue a single `GetAccountInfo`
  call and return a `bool`; unlike the former implicit probe, a probe error is
  raised rather than swallowed and degraded to flat semantics. This mirrors the
  established pattern for connection facts that are discoverable but must not be
  silently inferred (`SFTPUtils.scan_host_keys`, `GraphUtils.resolve_drive_id`).
  *Reverse if* discovery becomes reliable enough to fold back into construction.

The exact constructor signatures, the `ValueError` validation, the real-`bool`
coercion rule, `_hns` immutability, and the `detect_hns`/`adetect_hns` contract
are spec-rate and live in [spec 012](../specs/012-azure-backend.md) (AZ-001,
AZ-005, AZ-006). The breaking migration (every call site adds `hns=`) is in
Consequences.

### [ADR-0031](0031-expert-personas-as-subagent-files.md): Expert Personas as Standalone Subagent Files

Each expert persona is a **standalone Claude Code subagent** in
`.claude/agents/<name>.md`, the single source of truth for that persona.
The `/orchestrate` skill no longer embeds personas; it references each expert by
`subagent_type` and supplies the per-call task and mode in the invocation prompt.

- **Repo-root-relative paths.** Personas cite `sdd/TESTING.md` etc. as plain
  paths (agents run with cwd at the repo root).
- **Per-call context via the prompt.** The static persona holds identity, domain,
  constraints, and done-when; the invocation prompt carries the task, the specs
  to trace, and the mode (implement vs review).

*Reverse if* the split stops paying off: the personas are never reused outside
`/orchestrate`, or their model-routability (the main loop spawning an expert
outside an orchestration run) proves more harmful than the reuse is worth,
favouring a re-inlined, fully-gated model.

Domain boundaries, the three orchestration modes, the convergence flow, and
cross-domain file ownership (README/CHANGELOG owned by the orchestrator) are
unchanged.

> amends ADR-0019 (clause).

## Superseded

### [ADR-0006](0006-documentation-architecture.md): Documentation Architecture - Source of Truth and Audiences

##### Principle: `docs/` is a representation, never the source

All publishable content lives in source directories. The `docs/` directory
is **fully generated** — every file is either a wrapper directive or produced
by the build script. `docs/` is gitignored.

##### Content homes by type

| Content type | Source location | Audience |
|---|---|---|
| Project introduction, installation, quick start | `README.md` | Both |
| User-facing guides (backends, streaming, patterns) | `guides/` | Package users |
| Runnable code examples | `examples/` | Package users |
| API docstrings | Python source (`src/`) | Both |
| Design specs | `sdd/specs/` | Developers |
| Architecture decision records | `sdd/adrs/` | Developers |
| Design process & overview | `sdd/` (root files) | Developers |
| Contributor workflow | `CONTRIBUTING.md` | Developers |
| Release history | `CHANGELOG.md` | Both |
| Development narrative | `DEVELOPMENT_STORY.md` | Developers |

##### Audience entry points

- **Package users** enter through `README.md` (also the PyPI landing page).
  It links to `guides/` for deeper topics and `examples/` for runnable code.
- **Developers** enter through `README.md` for orientation, then navigate to
  `sdd/` for design context and `CONTRIBUTING.md` for workflow.

##### The `guides/` directory

Top-level directory for all user-facing guide content — any topic that helps
a package user accomplish something. Organized by subject:

```text
guides/
  backends/
    index.md          # comparison table, pluggable architecture
    local.md
    s3.md
    s3-pyarrow.md
    sftp.md
  # future topics added as needed
```

Guides are written as standalone Markdown, readable on GitHub without MkDocs.
The build script wraps them into `docs/` for the published site.

##### Build process

A build script (or MkDocs hook) generates the entire `docs/` tree:

1. Creates wrapper files with `include-markdown` directives pointing to
   source locations (`README.md`, `guides/`, `sdd/`, `examples/`).
2. Generates navigation index pages from `mkdocs.yml` structure.
3. Copies or symlinks assets as needed.

The generated `docs/` directory is excluded from version control via
`.gitignore`.

##### Where to put new content — decision rule

> If you can read it on GitHub and it makes sense without MkDocs, it belongs
> in a source directory. If it only makes sense as part of the site build,
> it belongs in the build script.

> superseded by ADR-0007.

### [ADR-0016](0016-seekable-read-three-tier-design.md): Seekable Read — Three-Tier Design

Apply the ADR-0009 three-tier pattern to seekable reads:

1. **`Capability.SEEKABLE_READ`** — a new capability flag; backends that always return seekable streams from `read()` declare it.
2. **`Store.read()`** — the existing contract; no new method, the flag adds a static guarantee alongside the per-stream `stream.seekable()` check.
3. **`ext.seekable.seekable_read()`** — a portable fallback that wraps a non-seekable stream.

##### Tier 1: `Capability.SEEKABLE_READ`

A new `Capability` enum member. Backends that always return seekable
streams from `read()` declare it. Users query with
`store.supports(Capability.SEEKABLE_READ)`.

Backends declaring `SEEKABLE_READ`: Local, Memory, S3, S3-PyArrow,
SFTP. Backends that do not: Azure (forward-only chunk iterator),
HTTP (response body stream).

##### Tier 2: `Store.read()` — existing contract

No new Store method. The existing `Store.read()` already returns
`BinaryIO`, and `stream.seekable()` already tells the caller whether
the stream supports seeking. The capability flag adds a **static**
guarantee alongside the per-stream dynamic check.

##### Tier 3: `ext.seekable.seekable_read()` — portable fallback

```python
from remote_store.ext.seekable import seekable_read

with seekable_read(store, "report.csv") as f:
    f.seek(0)  # works on any backend
```

Algorithm:

1. Call `store.read(path)`.
2. If `stream.seekable()` is `True`, return as-is (zero-copy).
3. Otherwise, spool into `SpooledTemporaryFile(max_size=max_memory)`:
   content ≤ `max_memory` (default 8 MB) stays in RAM, beyond that
   spills to a temporary file on disk.
4. Return the spool, positioned at byte 0.

If a backend declares `SEEKABLE_READ` but returns a non-seekable
stream, the extension issues a warning and falls back to spooling.

> superseded by ADR-0017.

### [ADR-0019](0019-multi-agent-orchestration.md): Multi-Agent Orchestration Architecture

**Option C — Claude Code native agents.** An orchestrator (the main session)
spawns domain-scoped experts (Backend, Ext, Test, Doc) in parallel via the
Agent tool; each runs with full repo access, and the orchestrator aggregates
their results and handles cross-domain concerns (ripple-checks, CHANGELOG,
BACKLOG, validation).

```
Task (user invokes /orchestrate)
         ↓
    Orchestrator
    (pre-check, plan architecture)
         ↓
┌────────┬────────┬────────┬────────┐
│Backend │  Ext   │ Test   │  Doc   │
│Expert  │Expert  │Expert  │Expert  │
└────────┴────────┴────────┴────────┘
  (parallel, domain-scoped agents)
         ↓
    Orchestrator
    (ripple-checks, CHANGELOG, BACKLOG, validate)
```

##### Two modes

- **Implementation mode** (code changes): experts write code/tests/docs within
  their domain. Orchestrator handles cross-domain files.
- **Review mode** (SDD-only changes): experts review from their domain
  perspective but do not implement. Reports go to the orchestrator for
  aggregation.

##### Expert activation

All code changes activate all 4 experts. Each evaluates from their domain —
the Extension expert always assesses downstream impact on `ext/` even when
extension files aren't directly modified. For SDD-only changes, all 4 review.

##### Aggregation

The orchestrator:
1. Collects expert outputs (files changed, issues found, assessments)
2. Runs ripple-check audit against `CLAUDE-REFERENCE.md`
3. Fixes cross-domain gaps (README, pyproject.toml, nav files)
4. Validates via `hatch run all`

##### Domain boundaries

> **Amended by [ADR-0031](0031-expert-personas-as-subagent-files.md).** The
> per-expert persona definitions (identity, domain, foundation, constraints) now
> live as standalone Claude Code subagents in `.claude/agents/`, referenced by
> the `/orchestrate` skill via `subagent_type`, rather than inline in the skill.
> The domain boundaries themselves are unchanged.

| Expert | Domain | Foundation |
|--------|--------|-----------|
| Store & Backend | `src/remote_store/` (excluding `ext/`) | DESIGN.md + relevant specs/ADRs |
| Extension | `src/remote_store/ext/` | DESIGN.md + relevant specs/ADRs |
| Testing | `tests/` | TESTING.md, DESIGN.md § 11 |
| Documentation | `docs-src/`, `examples/`, `guides/`, docstrings | DOCUMENTATION.md, DESIGN.md § 4 |

README.md and CHANGELOG.md are cross-domain files owned by the orchestrator.
The Documentation Expert assesses their impact but does not write to them.

> superseded by ADR-0020.
