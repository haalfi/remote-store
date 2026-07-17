# ADR digest

<!-- doc: repo-only -->

Compiled from 30 ADR(s) by `scripts/gen_adr_digest.py`. Do not edit by hand; run `hatch run gen-adr-digest`.

## Accepted

### [ADR-0001](0001-architecture-store-registry-backends.md): Architecture - Store, Registry, Backends

Three-layer architecture:

1. **Store** — user-facing, immutable, folder-scoped. All operations use relative paths. Delegates all I/O to a backend. Thin wrapper with path scoping and capability gating.

2. **Registry** — owns backend lifecycle. Lazily instantiates backends from config. Shares backend instances across stores. Acts as context manager for cleanup.

3. **Backend (ABC)** — encapsulates all storage-specific behavior. Declares capabilities. Maps native errors to normalized types. Never exposed directly to end users.

### [ADR-0002](0002-config-resolution-no-merge.md): Configuration Resolution - No Merging

**Config-as-code has absolute priority. No merging, no env var overrides.**

### [ADR-0003](0003-fsspec-is-implementation-detail.md): fsspec Is an Implementation Detail

**fsspec is an implementation detail, never exposed in the public API.**

### [ADR-0004](0004-empty-path-semantics.md): Empty Path Semantics in Store

Split path resolution in `Store` into two tiers:

1. **`_full_path(path)`** — accepts empty string `""` to mean "the store root." If `root_path` is set, returns `root_path`; otherwise returns `""`. Non-empty paths still validate through `RemotePath`.

2. **`_require_file_path(path)`** — rejects empty strings with `InvalidPath`. Used by file-targeted operations where an empty path is nonsensical.

### [ADR-0005](0005-native-path-resolution.md): Bidirectional Path Resolution via `to_key`

Introduce `to_key` at two levels:

1. **`Backend.to_key(native_path) -> str`** — concrete ABC method (identity default) that strips the backend's own root/prefix, replacing the scattered `_rel_path` / `relative_to` patterns.
2. **`Store.to_key(path) -> str`** — public method composing backend conversion with store-root stripping.

Store listing methods also strip `root_path` from returned paths so `FileInfo.path` round-trips back into other Store methods.

### [ADR-0007](0007-docs-src-literate-nav.md): Three-Tier Documentation Architecture with docs-src/ and Literate Nav

Supersedes ADR-0006's two-tier model.  Content lives in one of three places,
determined by its nature:

1. **Source directories** — content readable on GitHub without MkDocs
   (`README.md`, `guides/`, `sdd/`, `examples/`, `src/`).
2. **`docs-src/`** — site-specific authored content: landing pages, index
   pages, `include-markdown` wrappers, `mkdocstrings` directives, `.tmpl`
   templates for dynamic index pages, and per-section `_nav.yml` files.
   Checked into version control.
3. **Build hook (`scripts/gen_pages.py`)** — pure mechanics: filesystem
   scanning, template filling, link rewriting, navigation assembly.
   No authored prose.

> supersedes ADR-0006.

### [ADR-0008](0008-extension-architecture.md): Extension Namespace Contract (`ext.*`)

The `ext.*` namespace contract for stateless utility extensions:

- **Location** — extensions live in `src/remote_store/ext/<name>.py` (single module) or `src/remote_store/ext/<name>/` (sub-package); `ext/__init__.py` re-exports nothing, each extension is imported directly.
- **Public API only** — extensions use only the public `Store` / `Backend` API (no private-attribute access); `Store.unwrap(type_hint)` is the sanctioned escape hatch.
- **Module exports** — every extension module defines `__all__`.
- **Lifecycle** — extensions never own the `Store`; they must not close it or use it as a context manager.
- **Error propagation** — `CapabilityNotSupported` must propagate to the caller, never be suppressed.

### [ADR-0009](0009-glob-three-tier-design.md): Glob - Three-Tier Design

Three tiers of pattern matching, with clear escalation:

1. **`list_files(pattern=…)`** — simple `fnmatch` name filtering at the Store level; works on every backend with `LIST`, no new capability.
2. **`store.glob(pattern)`** — native backend glob, gated on `Capability.GLOB` (only Local implements it initially).
3. **`ext.glob.glob_files(store, pattern)`** — portable full recursive glob; uses `store.glob()` when available, else falls back to `list_files` + client-side regex.

### [ADR-0010](0010-observe-proxy-pattern.md): Observe - Proxy Subclass Pattern

Use **Option A (proxy subclass)** with a mandatory **drift-protection
test** that asserts `ObservedStore` overrides every public method of
`Store`. This catches missing overrides at CI time.

### [ADR-0011](0011-retry-per-backend-native.md): Retry - Per-Backend Native Configuration

Use **Option B (per-backend native configuration)**.

### [ADR-0012](0012-async-store-backend-api.md): Async Store / Backend API — Hybrid Model

Use **Option C (Hybrid)**: `AsyncBackend` ABC + `SyncBackendAdapter` +
`AsyncStore`.

### [ADR-0013](0013-drop-optional-extension-reexports.md): Drop Optional-Extension Re-exports from `__init__.py`

Remove the conditional `try/except ImportError` re-export blocks for all
optional-dependency extensions (`arrow`, `otel`, `pydantic`, `yaml`) from
`remote_store/__init__.py` and `__all__`.

> amends ADR-0008 (clause).

### [ADR-0014](0014-middleware-path-1-proxy-store-stream-wrappers.md): Middleware Architecture — Path 1 (ProxyStore + Stream Wrappers)

**We choose Path 1 (ProxyStore base + stream wrappers).**

### [ADR-0015](0015-proxystore-publicly-documented.md): Document ProxyStore in the Public API Reference

Export `ProxyStore` from `remote_store` and document it in the API
reference. The class remains an internal delegation base by design:
it centralises private-attribute coupling (`_backend`, `_root`,
`_owns_backend`) and default delegation. It is not a middleware
framework and gains no new hooks or dispatch machinery.

> amends ADR-0014 (clause).

### [ADR-0017](0017-seekable-read-on-store-api.md): Seekable Read on Store API

Add `read_seekable()` to `Backend` and `Store` as a concrete (non-abstract)
method alongside the existing `read()`.

> supersedes ADR-0016.

### [ADR-0018](0018-sqlalchemy-two-class-architecture.md): SQLAlchemy Backend — Two-Class Architecture with Shared Base

**Option B — Two concrete backends, shared base.**

### [ADR-0020](0020-orchestrate-iterative-convergence.md): Orchestrate Iterative Convergence Model

Replace the single-pass model with an **iterative convergence model** that
adds plan refinement, consolidation, and review loops — with complexity-based
mode selection to avoid unnecessary overhead.

> supersedes ADR-0019.

### [ADR-0021](0021-graph-sdk-choice.md): Microsoft Graph SDK Choice — `httpx` + `msal`

Build the backend on `httpx` (async client) plus `msal` for token
acquisition and cache serialization.

### [ADR-0022](0022-graph-auth-model.md): Microsoft Graph Auth Model — Dual Flows Behind a Token-Provider Protocol

The backend depends on a **token-provider callable**, not a concrete
auth class. Two variants cover sync and async call sites:

- `Callable[[], str]` — synchronous provider.
- `Callable[[], Awaitable[str]]` — async provider.

### [ADR-0023](0023-async-monitor-polling.md): Async Monitor-URL Polling — Backend-Local in `_graph`

Ship the polling logic **backend-local** in
`src/remote_store/aio/backends/_graph/monitor.py` (a module inside
the Graph sub-package, alongside `backend.py` / `http.py` /
`transfer.py` / `auth.py`), or inline in `backend.py` if it stays
under ~100 lines. The Graph backend lives under `aio/backends/`
because it is async-native (matching `aio/backends/_azure.py`); the
poller follows. It is part of the Graph sub-package, not a shared
facility. No public API surface and no Store-level capability is
introduced.

### [ADR-0024](0024-resource-locked-error.md): `ResourceLocked` Error Type

Add `ResourceLocked` as a new concrete error type in
`src/remote_store/_errors.py`, alongside the other canonical errors.
It inherits directly from `RemoteStoreError` per the flat hierarchy
rule (ERR-008): one level deep, no intermediate categories.

### [ADR-0025](0025-async-to-sync-backend-adapter.md): Async-to-Sync Backend Adapter (`AsyncBackendSyncAdapter`)

Introduce a new class `AsyncBackendSyncAdapter` under
`remote_store.aio` that implements the sync `Backend` ABC by
delegating to an `AsyncBackend` running on a private event loop in a
dedicated background thread. Do **not** invert `SyncBackendAdapter`;
the execution direction is different enough that two distinct adapters
are clearer than one parameterised bridge.

### [ADR-0026](0026-strict-gate-on-kwarg.md): Strict-Gate Pattern for Optional Capability Kwargs

When a caller passes an optional kwarg that requires a specific capability,
and the backend does not declare that capability, raise
`CapabilityNotSupported` **before any I/O**. Never silently drop the kwarg.

### [ADR-0027](0027-docs-bridge-single-mechanism.md): Single Bridge with Enforcement, Not Layered Mechanisms

One documentation bridge, kept single by an enforcement gate. Three coupled
sub-decisions:

1. **One bridge, by construction** — `scripts/docs/scan.py:scan_dual_files` is the sole source-discovery function and `render.py:render_dual_pages` the sole render function; other helpers are removed, not deprecated. New content shapes extend this one mechanism rather than adding a parallel one.
2. **Classification next to the file** — each `.md` declares its class via an HTML-comment marker, with a directory-default fallback; a file with no marker and no default is unclassified and fails the gate (G-01). No central manifest that can drift from the files.
3. **Enforcement at PR time** — a check script fails the build if any framework rule is violated, so "use one bridge" cannot silently degrade to a preference.

### [ADR-0028](0028-testing-architecture-kind-stage-replay.md): Testing Architecture with Kind and Stage Axes and HTTP Replay Demotion

The testing architecture rests on five coupled commitments:

1. **Two orthogonal axes** — separate *kind* (pure, mocked, real-local, real-live) from *stage* (1/2/3 by cost); a fixture declares one of each.
2. **Conformance as the cross-backend spine** — one parametrised suite over the public `Store` / `Backend` API that every backend runs; backend-specific behaviour is isolated per backend.
3. **HTTP cassette + replay as a Stage 1 fixture** — a `<backend>_replay` fixture runs the real SDK path against a recorded cassette (Stage 3 records, Stage 1 replays); scoped to HTTP-transport backends only.
4. **Capability gating via native pytest** — parametrize id-filtering plus `pytest.mark.skipif`, no custom `@requires` marker layer.
5. **Explicit cassette refresh** — cassettes regenerate only when a developer runs `pytest --stage=3 --record` and commits the diff; CI never silently re-records.

### [ADR-0029](0029-graph-transfer-blocking-io-offload.md): Offload Graph Transfer Spool I/O off the Event Loop

Dispatch the blocking spool I/O in `transfer.py` through `asyncio.to_thread`:
the range-fallback `_spooled_window` write/seek/read, the `spool_content`
write/tell/seek, and the `_upload_chunks` per-chunk seek+read (bundled into one
`_seek_read` hop). The spool objects are accessed sequentially under `await`, so
single-threaded offload is safe; nothing else holds the reader concurrently.

> amends ADR-0025 (clause).

### [ADR-0030](0030-azure-hns-explicit-declaration.md): Azure HNS Is an Explicit Declaration, Not Auto-Detected

The Azure backend no longer auto-detects HNS. The account's nature is a
**mandatory, explicit** constructor and config input, declared as a required
`hns: bool` on both `AzureBackend` and `AsyncAzureBackend` (no default; a
missing or non-`bool` value raises at construction).

## Superseded

### [ADR-0006](0006-documentation-architecture.md): Documentation Architecture - Source of Truth and Audiences

All publishable content lives in source directories. The `docs/` directory
is **fully generated** — every file is either a wrapper directive or produced
by the build script. `docs/` is gitignored.

> superseded by ADR-0007.

### [ADR-0016](0016-seekable-read-three-tier-design.md): Seekable Read — Three-Tier Design

Apply the ADR-0009 three-tier pattern to seekable reads:

1. **`Capability.SEEKABLE_READ`** — a new capability flag; backends that always return seekable streams from `read()` declare it.
2. **`Store.read()`** — the existing contract; no new method, the flag adds a static guarantee alongside the per-stream `stream.seekable()` check.
3. **`ext.seekable.seekable_read()`** — a portable fallback that wraps a non-seekable stream.

> superseded by ADR-0017.

### [ADR-0019](0019-multi-agent-orchestration.md): Multi-Agent Orchestration Architecture

**Option C — Claude Code native agents.** An orchestrator (the main session)
spawns domain-scoped experts (Backend, Ext, Test, Doc) in parallel via the
Agent tool; each runs with full repo access, and the orchestrator aggregates
their results and handles cross-domain concerns (ripple-checks, CHANGELOG,
BACKLOG, validation).

> superseded by ADR-0020.
