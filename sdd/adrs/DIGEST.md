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

**Config-as-code has absolute priority. No merging, no env var overrides.**

Resolution rules:

1. If `RegistryConfig` is provided in code → use it exclusively
2. If no config is provided → environment variables may be used as a fallback
3. No layering, no merging between sources
4. Backend defaults apply last (within a single config source)

### [ADR-0003](0003-fsspec-is-implementation-detail.md): fsspec Is an Implementation Detail

**fsspec is an implementation detail, never exposed in the public API.**

- Backend adapters *may* use fsspec internally (e.g., S3 via `s3fs`, Azure via `adlfs`)
- The `Backend` ABC is our own contract — it does not extend or depend on fsspec
- The `unwrap()` escape hatch allows extensions to access native handles (including fsspec filesystems) when they knowingly accept the coupling

```python
# Extension that needs native access:
fs = backend.unwrap(fsspec.AbstractFileSystem)  # explicit, type-safe
```

### [ADR-0004](0004-empty-path-semantics.md): Empty Path Semantics in Store

Split path resolution in `Store` into two tiers:

1. **`_full_path(path)`** — accepts empty string `""` to mean "the store root." If `root_path` is set, returns `root_path`; otherwise returns `""`. Non-empty paths still validate through `RemotePath`.

2. **`_require_file_path(path)`** — rejects empty strings with `InvalidPath`. Used by file-targeted operations where an empty path is nonsensical.

##### Method classification

| Accepts `""` (folder/query ops) | Rejects `""` (file-targeted ops) |
|--------------------------------|----------------------------------|
| `exists` | `read`, `read_bytes` |
| `is_file`, `is_folder` | `write`, `write_atomic` |
| `list_files`, `list_folders` | `delete` |
| `get_folder_info` | `delete_folder` |
| | `get_file_info` |
| | `move`, `copy` |

##### Rationale for `delete_folder("")` rejection

Even though `delete_folder` is a folder operation, deleting the store root is destructive and almost certainly unintended. It is rejected with `InvalidPath("Cannot delete the store root")`.

### [ADR-0005](0005-native-path-resolution.md): Bidirectional Path Resolution via `to_key`

Introduce `to_key` at two levels:

1. **`Backend.to_key(native_path) -> str`** — concrete ABC method (identity default) that strips the backend's own root/prefix, replacing the scattered `_rel_path` / `relative_to` patterns.
2. **`Store.to_key(path) -> str`** — public method composing backend conversion with store-root stripping.

Store listing methods also strip `root_path` from returned paths so `FileInfo.path` round-trips back into other Store methods.

##### 1. `Backend.to_key(native_path: str) -> str`

Concrete method on the Backend ABC (identity default). Converts a
backend-native path to a backend-relative key by stripping the backend's own
root/prefix.

- **Local:** strips filesystem root → `"/tmp/store/data/file.txt"` → `"data/file.txt"`
- **S3:** strips bucket prefix → `"my-bucket/data/file.txt"` → `"data/file.txt"`
- **SFTP:** strips base_path → `"/srv/sftp/data/file.txt"` → `"data/file.txt"`

Replaces the existing scattered `_rel_path` / `relative_to` patterns with a
single, consistent hook.

##### 2. `Store.to_key(path: str) -> str`

Public method. Composes backend conversion with store-root stripping:

```text
backend.to_key(native_path)  →  strip root_path prefix  →  store-relative key
```

Example:
```python
store = Store(backend=sftp, root_path="data")
store.to_key("/srv/sftp/data/reports/q1.csv")  # → "reports/q1.csv"
```

##### 3. Round-trip fix

Store listing methods (`list_files`, `list_folders`, `get_file_info`,
`get_folder_info`) strip `root_path` from returned paths so that `FileInfo.path`
is directly usable as input to other Store methods.

##### Key design choices

1. **Same name at both levels** — `to_key` at Backend and Store. Clear intent,
   composable.

2. **Concrete method, not abstract** — existing backends inherit the identity
   default. Only backends with custom roots override.

3. **Pure and deterministic** — no I/O, no side effects. Testable in isolation.

4. **Store owns the round-trip guarantee** — the Store layer strips `root_path`,
   not the backend. Backends only know about their own root.

### [ADR-0007](0007-docs-src-literate-nav.md): Three-Tier Documentation Architecture with docs-src/ and Literate Nav

##### Principle: three-tier content architecture

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
| Site landing pages, section indexes, API ref layout | `docs-src/` | Site-specific |
| Dynamic index templates (specs, ADRs) | `docs-src/**/_index.tmpl` | Site-specific |
| Section navigation ordering | `docs-src/**/_nav.yml` | Site-specific |

##### The `docs-src/` directory

MkDocs reads `docs-src/` as its `docs_dir`.  It contains:

- **Include wrappers** that pull content from source directories via
  `include-markdown` (e.g., `changelog.md` includes `../CHANGELOG.md`).
- **Directive pages** for `mkdocstrings` API reference and `pymdownx.snippets`
  example embeds.
- **Static authored pages** like `api/index.md` (API overview) and
  `examples/index.md` (examples overview) — curated site content that has
  no meaningful standalone existence on GitHub.
- **Templates** (`_index.tmpl`) whose static preamble is authored in Markdown;
  dynamic rows are injected by the build hook.
- **Navigation files** (`_nav.yml`) declaring the ordered list of pages in
  each section.  The build hook reads these recursively to assemble the
  site-wide `SUMMARY.md`.

##### Build process

The MkDocs "literate" plugin stack replaces the monolithic build script:

- **`mkdocs-gen-files`** runs `scripts/gen_pages.py` during the build to
  create virtual pages (spec/ADR/RFC wrappers, filled templates, link-
  rewritten pages, copied assets) and assemble `SUMMARY.md` from the
  per-section `_nav.yml` files.
- **`mkdocs-literate-nav`** reads the generated `SUMMARY.md` for navigation,
  eliminating the static `nav:` block in `mkdocs.yml`.
- **`mkdocs-section-index`** maps section landing pages to their parent
  nav entry.

No pre-build step is required.  No `docs/` directory is generated on disk.

##### Navigation convention

Each directory in `docs-src/` may contain a `_nav.yml` file:

```yaml
# docs-src/backends/_nav.yml
- Local: local.md
- S3: s3.md
- S3-PyArrow: s3-pyarrow.md
- SFTP: sftp.md
- Azure: azure.md
```

- Entries are `label: file.md` for leaf pages.
- Entries ending with `/` (e.g., `Specs: specs/`) are subsections — the build
  hook recurses into that directory's `_nav.yml`.
- Sections without a `_nav.yml` that match a scanned directory (`design/specs`,
  `design/adrs`) are populated automatically from the filesystem scan.
- Adding a page to a section means creating the `.md` file and adding one
  line to the section's `_nav.yml`.  No Python is touched.

##### Where to put new content — decision rule

> If you can read it on GitHub and it makes sense without MkDocs, it belongs
> in a source directory.  If it is authored prose that only makes sense as
> part of the documentation site, it belongs in `docs-src/`.  If it is pure
> build mechanics (scanning, templating, link rewriting), it belongs in the
> build hook.

> supersedes ADR-0006.

### [ADR-0008](0008-extension-architecture.md): Extension Namespace Contract (`ext.*`)

The `ext.*` namespace contract for stateless utility extensions:

- **Location** — extensions live in `src/remote_store/ext/<name>.py` (single module) or `src/remote_store/ext/<name>/` (sub-package); `ext/__init__.py` re-exports nothing, each extension is imported directly.
- **Public API only** — extensions use only the public `Store` / `Backend` API (no private-attribute access); `Store.unwrap(type_hint)` is the sanctioned escape hatch.
- **Module exports** — every extension module defines `__all__`.
- **Lifecycle** — extensions never own the `Store`; they must not close it or use it as a context manager.
- **Error propagation** — `CapabilityNotSupported` must propagate to the caller, never be suppressed.

##### Extension location

Extensions live in `src/remote_store/ext/<name>.py` (single module) or
`src/remote_store/ext/<name>/` (sub-package for complex extensions).
The `ext/__init__.py` re-exports nothing; each extension is imported
directly by the user or by `remote_store.__init__`.

##### Public API only

Extensions MUST use only the public `Store` and `Backend` API.  Direct
access to private attributes (e.g., `store._backend`) is forbidden.
`Store.unwrap(type_hint)` is the approved escape hatch for native
backend access.

##### Module exports

Every extension module defines `__all__` listing its public symbols.

##### Lifecycle rules

Extensions do not own `Store` lifecycle.  They must never call
`store.close()` or use the Store as a context manager.  The caller owns
the Store and is responsible for its lifecycle.

##### Error propagation

`CapabilityNotSupported` raised by Store methods MUST propagate to the
extension's caller.  Extensions must not catch and suppress it.

##### Capability-probe exception pattern

The rule "CapabilityNotSupported MUST propagate" has one documented
exception: the **capability-probe** pattern.  Extensions MAY catch
`CapabilityNotSupported` when probing for an **optional native backend**
during initialization, provided:

1. The probe is for an **optional feature**, not a required operation.
2. A graceful fallback exists (e.g., Tier 2/3 I/O paths in `ext.arrow`).
3. The catch is narrowly scoped to expected exceptions (e.g.,
   `(CapabilityNotSupported, TypeError, OSError)` for cloud backends).
4. A comment explains the probe, exceptions caught, and fallback strategy.
5. The catch MAY be annotated with `# noqa: BLE001` as a documentation marker
   if the implementation uses a broad catch; the annotation is optional if the
   catch is already narrow and specific.

**Example:** `ext.arrow` Tier 1 probe (`src/remote_store/ext/arrow.py`
line 177).  The `StoreFileSystemHandler.__init__` probes for a native PyArrow
backend via `store.unwrap(pafs.FileSystem)`.  If the backend doesn't
support unwrap or the type doesn't match, the probe gracefully falls back
to Tier 2/3 (full-file materialization or byte-range reads).

Any new extension using this pattern MUST cite this section and document
the fallback strategy explicitly in comments.

##### Export rules

> Superseded by ADR-0013 — optional-dependency extensions are no longer
> re-exported from `remote_store.__init__`. Import them directly from
> `remote_store.ext.<name>`.

Two patterns, determined by dependency requirements:

1. **Pure Python (no extra dependencies).**
   Exported unconditionally from `remote_store.__init__`.  Users get
   the symbols with `import remote_store` or
   `from remote_store import <name>`.

2. **Optional dependency (requires an extra).**
   The extension module guards its dependency import at the top level
   with a `try/except ModuleNotFoundError` that raises a helpful error:

   ```python
   # In ext/<name>.py:
   try:
       import pyarrow as pa
   except ModuleNotFoundError as _exc:
       raise ModuleNotFoundError(
           "PyArrow is required for the arrow extension. "
           "Install it with: pip install 'remote-store[arrow]'"
       ) from _exc
   ```

   `remote_store.__init__` conditionally re-exports these symbols with
   a silent `try/except ImportError` guard so that `from remote_store
   import pyarrow_fs` works when the dependency is installed, but core
   package import never fails:

   ```python
   # In remote_store/__init__.py:
   try:
       from remote_store.ext.arrow import StoreFileSystemHandler, pyarrow_fs
       __all__ += ["StoreFileSystemHandler", "pyarrow_fs"]
   except ImportError:
       pass
   ```

##### Dependency rules

- Core `remote-store` stays zero-dependency.
- Optional dependencies are declared as extras in
  `pyproject.toml [project.optional-dependencies]`.
- Extension code must not import optional dependencies at the top level
  in `TYPE_CHECKING` blocks without a guard, since mypy may still
  evaluate those imports.

##### Development lifecycle

New extensions follow the SDD pipeline:

1. RFC in `sdd/rfcs/` (proposal and design discussion).
2. Spec in `sdd/specs/` (contract and invariants).
3. Tests in `tests/test_<name>.py` with `@pytest.mark.spec("ID")`.
4. Implementation in `src/remote_store/ext/<name>.py`.
5. Guide in `guides/` and docs wiring in `docs-src/`.
6. CHANGELOG and BACKLOG updated in the same commit.

Tests live at `tests/test_<name>.py` (flat, not `tests/ext/`).

##### Third-party extensions

External packages should use the naming convention
`remote-store-<name>` (PyPI package name).  They should:

- Use only the public Store/Backend API.
- Use `register_backend()` for backend registration (if applicable).
- Use `Store.unwrap()` for native handle access.
- For backend extensions: reuse the conformance test suite by importing
  and parameterizing it.

Entry-point based plugin discovery is deferred until third-party
extensions emerge and the discovery mechanism can be designed with
real use cases.

##### Future patterns (not yet designed)

The current convention covers **stateless utility extensions** —
standalone functions that accept a Store and return results.  Planned
extensions will require additional patterns:

- **`ext.notify`** (ID-024) needs a hook/interceptor mechanism to wrap
  Store operations.  Likely a decorator or proxy Store pattern:
  `store = instrument(store, on_read=..., on_error=...)`.
- **`ext.cache`** (ID-025) needs a wrapping/proxy pattern that sits
  between the caller and the Store, intercepting reads and caching
  results.
- **Streaming atomic writes** (ID-026) needs a context manager protocol
  integrated with the Store.

These patterns will be designed as separate ADRs when the extensions
are implemented.  This ADR's rules (public API only, `__all__`,
dependency management, test location) apply to all extension types;
the additional patterns will layer on top.

### [ADR-0009](0009-glob-three-tier-design.md): Glob - Three-Tier Design

Three tiers of pattern matching, with clear escalation:

1. **`list_files(pattern=…)`** — simple `fnmatch` name filtering at the Store level; works on every backend with `LIST`, no new capability.
2. **`store.glob(pattern)`** — native backend glob, gated on `Capability.GLOB` (only Local implements it initially).
3. **`ext.glob.glob_files(store, pattern)`** — portable full recursive glob; uses `store.glob()` when available, else falls back to `list_files` + client-side regex.

##### Tier 1: `list_files(pattern=…)` — simple name filtering

```python
store.list_files("logs", pattern="*.log")
```

- `pattern` is an `fnmatch` pattern matched against each file's **name**.
- Applied at the `Store` level — works with every backend that has `LIST`.
- No new capability required.
- Covers the most common use case: "give me the CSVs in this folder."

##### Tier 2: `store.glob(pattern)` — native backend access

```python
store.glob("**/*.csv")  # only if backend supports GLOB
```

- Capability-gated on `Capability.GLOB`.
- Like `unwrap()`: opt-in direct access to a backend-specific feature.
- Only `LocalBackend` implements it (via `pathlib.Path.glob()`).
- Users who call this **know** their backend and want native semantics.

##### Tier 3: `ext.glob.glob_files(store, pattern)` — portable full glob

```python
from remote_store.ext.glob import glob_files
glob_files(store, "data/**/*.csv")
```

- Full recursive glob patterns (`**`, wildcards in directory segments).
- Delegates to `store.glob()` when GLOB is available, otherwise falls
  back to `list_files` + client-side regex matching.
- The recommended API when `list_files(pattern=)` isn't enough and
  you want code that works across all backends.

##### Pattern syntax

- `*` — any characters except `/`
- `**` — zero or more path segments (recursive)
- `?` — single non-separator character
- `[abc]` — character class
- `[!abc]` — negated character class

`list_files(pattern=…)` uses stdlib `fnmatch` (complete, well-tested).
`ext.glob` uses a regex converter that supports the full syntax above.

##### Non-Local backends

S3, S3-PyArrow, SFTP, Azure, and Memory do not declare
`Capability.GLOB` in this iteration. They can add native
glob implementations in future releases (S3 and Azure have
prefix-optimized listing that could be leveraged).

### [ADR-0010](0010-observe-proxy-pattern.md): Observe - Proxy Subclass Pattern

Use **Option A (proxy subclass)** with a mandatory **drift-protection
test** that asserts `ObservedStore` overrides every public method of
`Store`. This catches missing overrides at CI time.

The drift-protection test inspects `Store.__dict__` for public callable
members and verifies that `ObservedStore.__dict__` contains an override
for each one. This is specified as OBS-007 in the spec.

##### Reusability

The proxy subclass pattern established here is reusable for future
wrappers such as `ext.cache` (ID-025). The drift-protection test
technique generalises: any proxy subclass of `Store` can include an
analogous assertion.

##### Naming

The extension is named `ext.observe` (not `ext.notify` from the
original backlog). "Observe" better describes the read-only,
side-effect-free nature of the hooks — they observe operations but do
not intercept or modify them. The factory function is `observe()`.

### [ADR-0011](0011-retry-per-backend-native.md): Retry - Per-Backend Native Configuration

Use **Option B (per-backend native configuration)**.

1. Backends own their transport — retry is a transport concern.
2. The policy replaces SDK defaults, avoiding retry multiplication.
3. Minimal API surface: one frozen dataclass, one constructor parameter.
4. No new core dependencies — `tenacity` stays in the SFTP `sftp` extra.

##### RetryPolicy dataclass

A frozen dataclass in `_config.py` with five fields:

- `max_attempts` (int, default 3): Total attempts including initial.
  Set to 1 to disable retry.
- `backoff_base` (float, default 1.0): Base delay in seconds.
- `backoff_max` (float, default 60.0): Ceiling for exponential backoff.
- `jitter` (float, default 1.0): Max random jitter per delay.
- `timeout` (float | None, default None): Total wall-clock limit.

A `RetryPolicy.disabled()` classmethod returns `RetryPolicy(max_attempts=1)`.

##### Backend mapping

Each backend translates the policy into its native retry mechanism:

- **SFTP:** Replaces hardcoded tenacity decorator with policy-driven
  `stop_after_attempt`, `wait_exponential`, `wait_random`, optionally
  `stop_after_delay`.
- **S3:** Maps to `botocore.config.Config(retries={"max_attempts": N,
  "mode": "standard"})` merged into `client_options`.
- **Azure:** Maps to `ExponentialRetry(retry_total=N-1,
  initial_backoff=base, random_jitter_range=jitter)` set as
  `retry_policy` in client options.
- **S3-PyArrow:** Maps to both PyArrow C++ side (`max_attempts`) and
  s3fs side (same as S3).
- **Local/Memory:** Do not accept `retry` parameter — TypeError if
  provided (correct: retry is meaningless for local I/O).

##### BackendConfig integration

`BackendConfig` gains a `retry: RetryPolicy | None = None` field.
`Registry._get_backend()` merges `retry` into `options` before
constructing the backend. `from_dict()` parses `retry` from nested
dicts in the config.

##### Scope

The policy controls **connection retry** (SFTP) and **SDK-level
operation retry** (S3, Azure). Application-level retry (reconnect
mid-operation, idempotency checks) is out of scope and could be
addressed by a future `ext/retry.py` middleware.

### [ADR-0012](0012-async-store-backend-api.md): Async Store / Backend API — Hybrid Model

Use **Option C (Hybrid)**: `AsyncBackend` ABC + `SyncBackendAdapter` +
`AsyncStore`.

1. **Separate async types.** `AsyncBackend` (ABC) and `AsyncStore` are
   distinct types from `Backend` and `Store`. No shared base class — they
   serve separate use cases. Follows the httpx pattern (separate `Client`
   / `AsyncClient`, shared config types).

2. **Auto-wrapping.** `AsyncStore` accepts both `AsyncBackend` and sync
   `Backend`. If given a sync `Backend`, it auto-wraps via
   `SyncBackendAdapter`. Users get async immediately with existing
   backends, no manual wrapping needed.

3. **`read()` returns `AsyncIterator[bytes]`.** There is no standard
   `AsyncBinaryIO` in Python. `AsyncIterator[bytes]` is the idiomatic
   async streaming pattern (used by httpx, aiohttp). `read_bytes()`
   remains the convenience method returning `bytes`.

4. **`aclose()` naming.** Follows the Python convention for async
   cleanup: `aclose` on async generators, `asyncio.StreamWriter`, and
   redis-py. `__aexit__` calls `aclose()`.

5. **`asyncio` only.** No anyio or trio dependency. The rationale is
   simplicity (fewer abstractions, easier debugging), not dependency cost
   — our async audience (FastAPI, Starlette, httpx users) already has
   anyio transitively. Can be revisited without breaking changes.

6. **Iterator materialization.** `SyncBackendAdapter` materializes
   `list_files()`, `list_folders()`, `glob()`, and `iter_children()` in
   a thread (collects to list, then yields). Cannot stream across thread
   boundaries. Native async backends (Phase 2) stream properly.

7. **Non-I/O methods stay sync.** `to_key()`, `unwrap()`,
   `native_path()`, `capabilities`, `name` — no I/O, no reason to be
   async.

8. **Phased rollout.** Phase 1: core surface (`AsyncBackend`,
   `SyncBackendAdapter`, `AsyncStore`, `AsyncMemoryBackend`). Phase 2:
   native async backends. Phase 3: async extensions. Each phase gets its
   own spec.

9. **Zero new runtime deps in Phase 1.** Uses only stdlib `asyncio`.
   Optional async deps (asyncssh) come in Phase 2 as extras.

### [ADR-0013](0013-drop-optional-extension-reexports.md): Drop Optional-Extension Re-exports from `__init__.py`

Remove the conditional `try/except ImportError` re-export blocks for all
optional-dependency extensions (`arrow`, `otel`, `pydantic`, `yaml`) from
`remote_store/__init__.py` and `__all__`.

Users import optional extensions from their canonical module path:

```python
from remote_store.ext.arrow import pyarrow_fs
from remote_store.ext.otel import otel_hooks, otel_observe
from remote_store.ext.pydantic import from_pydantic
from remote_store.ext.yaml import from_yaml
from remote_store.ext.dagster import dagster_io_manager
```

This makes all optional-dependency extensions consistent — including
dagster, which was already using this pattern.

The rest of ADR-0008 (public-API-only rule, `__all__`, lifecycle rules,
error propagation, dependency rules, development lifecycle, third-party
conventions) remains in effect.

> amends ADR-0008 (clause).

### [ADR-0014](0014-middleware-path-1-proxy-store-stream-wrappers.md): Middleware Architecture — Path 1 (ProxyStore + Stream Wrappers)

**We choose Path 1 (ProxyStore base + stream wrappers).**

ProxyStore is a delegation base class, not a middleware framework. It
centralizes the private-attribute coupling (`_backend`, `_root`,
`_owns_backend`) and provides default delegation for all Store methods.
Subclasses override only the methods they intercept.

##### Rationale

1. **Only observe + cache compose today.** Retry is already shipped as
   per-backend native configuration (ADR-0011, `RetryPolicy`). Circuit
   breaker, rate limiting, and fault injection are post-v1 ideas with
   no committed timeline. Two proxy wrappers do not justify a dispatch
   framework.

2. **Progress and checksums are stream concerns, not Store concerns.**
   `ProgressReader(store.read("file.bin"), callback)` is the right
   abstraction — it composes with any `BinaryIO`, requires no Store
   wrapping, and correctly skips cache hits (no stream to wrap).

3. **No breaking changes.** `observe()` and `cached_store()` factories
   keep their existing signatures and return types. ProxyStore is an
   internal base class, not a public API.

4. **The refactor from Path 1 to Path 2 is internal-only.** If a third
   policy-like proxy becomes necessary, migrating from ProxyStore to
   `_MiddlewareProxy` does not break public API. But we do not build
   that infrastructure speculatively.

##### What we build

| Module | Contents |
|--------|----------|
| `_proxy.py` (internal) | `ProxyStore` base class with `_wrap_child()` hook |
| `ext.streams` (new) | `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter` |
| `ext.integrity` (new) | `checksum()`, `verify()` — pure functions returning strings |

##### What we do NOT build

- No `ProgressStore` or `ChecksumStore` proxy wrappers.
- No `_before_*` / `_after_*` / `_short_circuit_*` hooks on ProxyStore.
- No category dispatch, no middleware merging, no public middleware API.
- No changes to `Store.read()` or `Store.write()` signatures for
  progress or checksums.
- No data model changes (`ContentDigest`, `FileInfo.digest`/`etag`) —
  those ship separately under ID-008 when backends populate them.

##### ProxyStore contract

`ProxyStore(Store)` is an internal abstract base class. It is not part
of the public API and must not be subclassed by user code.

**Construction:** `__init__(self, inner: Store)` copies `_backend`,
`_root`, and `_owns_backend` from the inner store. Exposes
`inner: Store` as a read-only property.

**Delegation:** Every public `Store` method has a default implementation
that delegates to `self._inner.<method>(...)`. Subclasses override only
the methods they intercept. Drift-protection tests (from ADR-0010)
verify that ProxyStore covers the full Store API surface.

**`_wrap_child()` hook:** `ProxyStore.child(subpath)` calls
`self._inner.child(subpath)` to create the inner child, then calls
`self._wrap_child(inner_child) -> Store` to let the subclass wrap it.

- The base `_wrap_child()` raises `NotImplementedError` — subclasses
  must provide an implementation.
- `CachedStore._wrap_child()` returns a new `CachedStore` with the same
  TTL, max_entries, and backend config.
- `ObservedStore._wrap_child()` returns a new `ObservedStore` with the
  same hooks.
- Subclasses must not return `None`. The return value must be a `Store`.

This fixes BUG-003: `cached_store(s).child("sub")` now returns a
`CachedStore`, not a plain `Store`.

##### Migration trigger for Path 2

Move to merged middleware only when one of these becomes true:

- Three or more store-level concerns must compose on the same operation path.
- Ordering between wrappers becomes product-significant, not just internal.
- One concern must short-circuit another in a general way.
- Adding a new concern would require broad override duplication again.

### [ADR-0015](0015-proxystore-publicly-documented.md): Document ProxyStore in the Public API Reference

Export `ProxyStore` from `remote_store` and document it in the API
reference. The class remains an internal delegation base by design:
it centralises private-attribute coupling (`_backend`, `_root`,
`_owns_backend`) and default delegation. It is not a middleware
framework and gains no new hooks or dispatch machinery.

The rest of ADR-0014 (delegation model, `_wrap_child()` hook, stream
wrappers, integrity functions, migration trigger for Path 2) remains
in effect.

> amends ADR-0014 (clause).

### [ADR-0017](0017-seekable-read-on-store-api.md): Seekable Read on Store API

Add `read_seekable()` to `Backend` and `Store` as a concrete (non-abstract)
method alongside the existing `read()`.

##### `Backend.read_seekable(path) -> BinaryIO`

Default implementation: delegates to `read()`. If the returned stream is
already seekable, returns it directly. Otherwise, spools into a
`SpooledTemporaryFile` (same logic as the removed `ext.seekable`).

Backends MAY override to provide an optimized implementation:

- **AzureBackend**: returns `_AzureRangeReader` — a seekable
  `io.RawIOBase` where each `readinto()` issues a single HTTP Range
  request via `download_blob(offset=, length=)`.
- **HttpBackend**: could implement HTTP Range in the future (not in
  this change).

##### `Store.read_seekable(path) -> BinaryIO`

Delegates to `backend.read_seekable()` with path resolution, capability
checks, and logging — same pattern as `Store.read()`.

##### Arrow integration

`StoreFileSystemHandler.open_input_file()` calls `store.read_seekable()`
instead of `store.read()` for the Tier 3 path. This gives PyArrow a
seekable, random-access-optimized handle on all backends without
materializing the full file.

##### Removal of `ext.seekable`

`ext.seekable.seekable_read()` is removed (never released — introduced
after v0.19.0 in ID-100). Its functionality is subsumed by
`Store.read_seekable()`. The `SEEKABLE_READ` capability shifts meaning:
it now indicates that `read_seekable()` is zero-overhead (no spooling
needed, the backend natively returns seekable streams).

##### `ProxyStore` cascade

`ProxyStore.read_seekable()` delegates to `self._inner.read_seekable()`.
`ObservedStore` hooks around it. `CachedStore` inherits the default.

> supersedes ADR-0016.

### [ADR-0018](0018-sqlalchemy-two-class-architecture.md): SQLAlchemy Backend — Two-Class Architecture with Shared Base

**Option B — Two concrete backends, shared base.**

```
_SQLAlchemyBaseBackend(Backend)   # private, not exported
├── SQLBlobBackend                # v1 — full read-write KV store
└── SQLQueryBackend               # v2 — read-only query materializer
```

##### Engine lifecycle: owned vs borrowed

The base accepts exactly one of `url: str` or `engine: Engine`:

- `url` → creates and **owns** the engine. `close()` disposes it.
- `engine` → **borrows** it. `close()` is a no-op.

This lets standalone scripts get automatic cleanup while web apps share
their connection pool.

##### Folder semantics: virtual prefixes

Unlike `MemoryBackend` and `LocalBackend` (which use explicit folder nodes),
`SQLBlobBackend` uses **virtual prefix-based folders** — a "folder" is any
key prefix that has child keys. This matches the S3/Azure pattern and avoids
maintaining a separate folder table or marker rows.

### [ADR-0020](0020-orchestrate-iterative-convergence.md): Orchestrate Iterative Convergence Model

Replace the single-pass model with an **iterative convergence model** that
adds plan refinement, consolidation, and review loops — with complexity-based
mode selection to avoid unnecessary overhead.

##### Three modes

| Mode | When | Flow |
|------|------|------|
| **Simple** | Trivial plan, clear scope | Plan → Execute → Review (1×) → Finish |
| **Standard** | Multi-domain, clear requirements | Plan → Refine (1×) → Execute → Consolidate → Review (1–2×) → Finish |
| **Complex** | Ambiguity, tight coupling, unknowns | Same as Standard, but user confirms before Execute and before each Review round |

The orchestrator selects the mode during planning. The user can override.

##### Flow

```
1. PLAN         — orchestrator drafts architecture plan
2. REFINE       — experts review plan (1 round, parallel)
                  → orchestrator integrates feedback
                  → unresolved points → user decides
3. EXECUTE      — experts implement (parallel or sequential per plan)
4. CONSOLIDATE  — orchestrator collects results:
                  ✓ done  |  ✗ blocked (with reason)  |  ⚠ needs input
                  → blocked: clarify with expert, re-execute
                  → needs input: escalate to user
5. REVIEW       — all experts review all output (parallel)
                  → clean: proceed to finish
                  → issues: experts fix → re-review (max 2 rounds total)
                  → still open after 2: user decides
6. FINISH       — CHANGELOG, BACKLOG, validate, commit, summary
```

**Simple mode** skips steps 2 (Refine) and 4 (Consolidate); review is
single-pass with no loop.

##### Expert responses

Structured when reporting issues (status + blockers + artifacts).
Free-form when clean ("done, no issues"). No over-engineered format.

##### Tie-breaking

The user breaks all ties. The orchestrator never overrides expert
disagreements autonomously — it presents the conflict and asks.

##### What stays from ADR-0019

- 4 domain experts (Store & Backend, Extension, Testing, Documentation)
- Domain boundaries and foundation docs
- Cross-domain files owned by orchestrator (CHANGELOG, BACKLOG, README)
- Bug-fix TDD mode (Testing Expert goes first)
- Ripple-check audit in finalization

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

Introduce a new class `AsyncBackendSyncAdapter` under
`remote_store.aio` that implements the sync `Backend` ABC by
delegating to an `AsyncBackend` running on a private event loop in a
dedicated background thread. Do **not** invert `SyncBackendAdapter`;
the execution direction is different enough that two distinct adapters
are clearer than one parameterised bridge.

The `AsyncBackendSyncAdapter` is the mirror of `SyncBackendAdapter`
(ADR-0012). Together they provide the full bidirectional bridge the
hybrid model needs.

##### Ownership model

- **One loop per adapter instance.** The adapter creates a new
  `asyncio.new_event_loop()` and starts a daemon `threading.Thread`
  that runs `loop.run_forever()`. The loop is private — not shared,
  not exposed, not reused across adapter instances.
- **One thread per adapter instance.** The loop thread is created in
  `__init__` and joined in `close()`. It is dedicated to this adapter;
  no other work is scheduled on it.
- **Thread-safe for concurrent sync callers.** Multiple threads may
  call sync methods on the same adapter concurrently. Each call
  submits an independent coroutine to the loop and blocks on its own
  future. Ordering between concurrent callers is not guaranteed;
  callers that need deterministic ordering must coordinate
  externally (e.g. their own lock or queue).

##### Submission and blocking

- Each sync method wraps the corresponding `AsyncBackend` coroutine
  and submits it via `asyncio.run_coroutine_threadsafe(coro, loop)`.
- The sync method blocks on the returned `concurrent.futures.Future`.
  `Future.result()` propagates the coroutine's return value or
  re-raises its exception.
- Non-I/O methods (`name`, `capabilities`, `to_key`, `native_path`,
  `resolve`, `unwrap`) delegate directly to the wrapped async backend
  without the loop, mirroring `SyncBackendAdapter`'s passthrough.
- I/O methods that return scalars or `None` — `exists`, `is_file`,
  `is_folder`, `read_bytes`, `get_file_info`, `get_folder_info`,
  `move`, `copy`, `delete`, `delete_folder`, **`check_health`** —
  follow the standard submit-and-block pattern. `check_health()`
  is explicitly **not** a no-op: connectivity errors from the
  wrapped async backend must reach the sync caller verbatim.
- `Future.result()` blocks without a per-call timeout. Timeout
  responsibility belongs to the wrapped `AsyncBackend`: backends
  should impose their own timeouts internally (e.g.
  `asyncio.wait_for`) or rely on SDK session-level timeouts.
  The adapter's `close(timeout=…)` provides a global shutdown
  bound; there is no per-operation equivalent.

##### Streaming iterators and open streams

- `read(path)` returns a sync file-like stream whose `read(n)` pumps
  chunks out of the backend's `AsyncIterator[bytes]`. The stream
  holds an internal byte buffer carrying the unread tail of the most
  recently fetched chunk: `read(n)` first drains that buffer, and
  only submits a new `__anext__` coroutine when the buffer is empty
  and more bytes are still required.  This satisfies the `BinaryIO`
  contract that `read(n)` returns at most *n* bytes even when the
  backend yields larger chunks.  The stream exposes `read(n)`,
  `close()`, `seekable()` (returns `False`), and `readable()`
  (returns `True`); `seek`, `tell`, and `fileno` are not provided.
  `close()` submits the async iterator's `aclose()` to the loop.
- `list_files`, `list_folders`, `glob`, `iter_children` return sync
  iterators backed by the same chunk-pull pattern. Materialising the
  full listing up front is **not** acceptable: native-async backends
  exist precisely to stream, and the sync wrapper must preserve that.
- The underlying async iterator handle lives on the loop; every
  step crosses the thread boundary via `run_coroutine_threadsafe`.
- **Single-chunk in-flight invariant.** The adapter has at most one
  outstanding `__anext__` per stream/iterator: no look-ahead, no
  read-ahead pool, no parallel prefetch. The unread tail of the
  most recently fetched chunk (held in the `read()` stream's byte
  buffer described above) is the *only* sanctioned per-stream
  buffer. The bridge must not reintroduce the memory bloat that
  materialising the full listing would cause.

##### Write-side content

The sync `Backend.write()` / `write_atomic()` accept the sync
`WritableContent = BinaryIO | bytes` (`src/remote_store/_types.py`).
There is no sync iterator-of-bytes input — that shape exists only on
the async side as `AsyncWritableContent = bytes | AsyncIterator[bytes]`
(`src/remote_store/aio/_types.py`). The bridge therefore goes
**sync `BinaryIO` → `AsyncIterator[bytes]`**, not the other way:

- `bytes` content is forwarded as-is to the async coroutine.
- `BinaryIO` content is wrapped in an internal `AsyncIterator[bytes]`
  that calls `asyncio.to_thread(stream.read, chunk_size)` per chunk
  inside the submitted coroutine, so the event loop never blocks on
  the caller's blocking file object. The single-chunk in-flight
  invariant from § Streaming applies symmetrically: at most one
  pending `to_thread` per write, no parallel pre-read.
- `write_atomic(path, content, …)` follows the identical pattern.
  The `ATOMIC_WRITE` capability gate is enforced by the wrapped
  async backend, not the adapter — the adapter forwards the call
  unchanged and lets the backend raise `CapabilityNotSupported` if
  the gate is closed.
- `open_atomic(path, …)` — abstract on sync `Backend`, with **no
  async analogue** on `AsyncBackend`. The adapter synthesises it as
  a context manager that yields a `SpooledTemporaryFile`; on clean
  `__exit__` the spool is rewound and submitted to the wrapped
  backend's `write_atomic` (a single `bytes`/`BinaryIO` write); on
  exception the spool is dropped and `path` is untouched. The
  capability gate is the same as `write_atomic` — backends without
  `ATOMIC_WRITE` raise `CapabilityNotSupported` when the spool
  flushes. (Synthesising over `write_atomic` rather than extending
  `AsyncBackend` keeps the async ABC unchanged; ID-127 does not need
  an `open_atomic`-shaped Graph operation.)

##### Cancellation

- Cancellation flows from sync to async by calling
  `Future.cancel()` on the `concurrent.futures.Future` returned by
  `run_coroutine_threadsafe`. This schedules `Task.cancel()` on the
  underlying asyncio task.
- Async backends are expected to honour `asyncio.CancelledError`
  normally; cleanup (closing HTTP responses, releasing connections,
  aborting upload sessions) happens inside the async code as usual.
- `concurrent.futures.Future.cancel()` is a best-effort flag, and
  `asyncio.Task.cancel()` only *requests* cancellation — the task
  observes `CancelledError` at the next `await` point and may
  still run cleanup before it actually exits (CPython issues
  python/cpython#103819 and python/cpython#105836 document the
  exact semantics). The adapter's `close()` therefore waits for
  in-flight tasks to drain before stopping the loop; ad-hoc
  per-call cancellation surfaces `CancelledError` to the sync
  caller without a teardown guarantee.
- `KeyboardInterrupt` is **not** specially handled. It propagates
  out of the blocking `Future.result()` like any other exception;
  the in-flight async task is left running and is cancelled when
  the adapter's `close()` runs (or when the daemon thread is
  reaped at process exit). Adding KI-to-cancel translation would
  give this one backend behaviour that no sync backend has, which
  costs more in contract asymmetry than the convenience earns.

##### Behaviour when the caller is in a running loop

- **Default: fail fast.** If a sync method is invoked from a thread
  with a running event loop, the adapter raises a clear
  `RuntimeError` explaining that the sync Store API cannot block a
  running loop and directing the caller to `AsyncStore` instead.
  This keeps the sync contract genuinely sync and prevents
  deadlocks. Aligned with ADR-0012 § Async posture: the sync
  `Store` is **not coroutine-safe**, by design — async callers use
  `AsyncStore`, full stop.
- **Detection.** The adapter checks
  `asyncio.get_running_loop()` (which raises if no loop is running)
  to decide. Detection happens at the entry of every blocking call,
  not at adapter construction, because the caller's loop context is
  per-call.
- **No opt-in nest-asyncio path in v1.** The door is open to add one
  later behind an explicit flag, but the default design does not
  require it and the first release does not ship it. Notebook and
  GUI users are directed to use `AsyncStore` directly.

##### `nest_asyncio` stance

- Not a runtime dependency. Not imported by the adapter.
- If a future compatibility mode is added, it will be an explicit
  opt-in with its own ADR. This ADR commits to *not* relying on
  `nest_asyncio` for correctness.

##### Lifecycle

- `close(timeout: float | None = 30.0)` submits
  `self._async_backend.aclose()` to the loop, waits for in-flight
  tasks to drain, calls `loop.call_soon_threadsafe(loop.stop)`, and
  joins the thread with the supplied bound. The default of 30 s
  matches the existing per-backend network-call ceilings; passing
  `None` waits indefinitely. If the timeout expires, the adapter
  logs a warning at `WARNING` level naming the unfinished tasks and
  returns; the daemon thread is torn down with the process.
- Context-manager protocol (`__enter__` / `__exit__`) delegates to
  `close()` on exit.
- The adapter is a one-shot resource: once closed, further calls
  raise a clear error rather than silently restarting the loop.

##### Error propagation

- Exceptions raised inside the async coroutine are re-raised
  verbatim in the sync caller via `Future.result()`. Traceback
  preservation follows the standard `concurrent.futures` behaviour.
- Error types and the canonical `path` / `backend` attributes
  (ERR-001 in `sdd/specs/005-error-model.md`) are preserved
  exactly: the adapter does not wrap or translate exceptions, and
  the error-mapping rules established by `AsyncBackend`
  implementations under ADR-0012 reach the sync caller unchanged.
- `TimeoutError` from the async layer stays `TimeoutError`;
  `ResourceLocked` (ADR-0024) stays `ResourceLocked`; and so on.

##### `read_seekable` (sync-only convenience)

`read_seekable` is concrete on the sync `Backend` (with a
`SpooledTemporaryFile` fallback over `read()`); it has **no async
analogue** on `AsyncBackend`. The adapter does *not* override it:
the inherited default sees a chunk-pull stream, calls `.seekable()`
(which returns `False`), and spools to disk-or-memory exactly as it
already does for the synchronous backends that emit non-seekable
streams. No new code path is needed; this section exists so the
implementer does not mistakenly wire a no-op.

A future native fast-path (e.g. issuing per-`read()` HTTP `Range`
requests directly through the async backend, mirroring
`AzureBackend`) is out of scope for this ADR. If added, it would
need an explicit async `read_seekable`-shaped operation on
`AsyncBackend` and is tracked as a Graph follow-up.

##### Capability translation

The adapter does **not** blindly forward the wrapped backend's
`CapabilitySet`. The bridge changes the observable shape of two
capabilities and must mask one off:

- **`SEEKABLE_READ` — masked off.** SIO-008 promises that
  `Backend.read()` returns a natively seekable stream. The chunk-pull
  pump returned by this adapter is forward-only; no `seek()`
  accelerator can be honoured without buffering. The adapter strips
  `SEEKABLE_READ` from the forwarded set even when the wrapped
  async backend declares it. Callers that need random access go
  through `read_seekable` and pay the spool cost (above), which is
  the same fallback every non-seekable sync backend already uses.
- **`LAZY_READ` — preserved.** SIO-009 requires `read()` to fetch
  data lazily on demand. The single-chunk in-flight invariant +
  `__anext__`-per-`read(n)` cadence preserves laziness end-to-end:
  the bridge never pre-reads beyond what the sync caller has asked
  for. Forwarded unchanged.
- **`ATOMIC_WRITE`, `ATOMIC_MOVE`, `GLOB`, and the remaining flags**
  — preserved unchanged. The async coroutine performs the operation;
  the bridge only marshals the call. Folder listing and folder
  deletion have no dedicated capability flag; they remain gated by
  `LIST` / `DELETE` on the wrapped backend per the sync `Backend`
  contract (see spec 029 § ASYNC-084).

`resolve()` delegates directly (no I/O, no loop).

`unwrap()` is **not** a generic passthrough: an `httpx.AsyncClient`
returned from a sync `unwrap()` is bound to the private loop in the
daemon thread, and using it from the caller's thread will fail or
corrupt loop state. The adapter raises `CapabilityNotSupported`
unless the wrapped backend exposes a sync-safe handle (mirroring
`SyncBackendAdapter.unwrap`'s behaviour for unsupported types). The
async handle remains reachable to coroutines submitted via the same
adapter; callers that need it directly should construct an
`AsyncStore` instead.

##### Module placement

`src/remote_store/_async_to_sync_adapter.py` — in the **core**
module, not under `aio/`. Symmetric with `SyncBackendAdapter`
(which lives in `aio/` because it implements `AsyncBackend`):
this adapter implements the sync `Backend` ABC, so it belongs
with the sync core. Putting it under `aio/` would force every
sync `Store` user that wraps an async backend to import the
`aio/` runtime modules at construction time, inverting the layering
invariant that sync code stays independent of `aio/`.

`AsyncBackend` is imported lazily inside the adapter's `__init__`
to avoid a top-level core → aio import. Public re-export from
`remote_store` follows the `SyncBackendAdapter` re-export pattern
in shape (alongside `Backend`, `Store`).

##### Store-level wiring

The sync `Store` gains a construction path that accepts an
`AsyncBackend` and wraps it with `AsyncBackendSyncAdapter`
automatically — the mirror of `AsyncStore`'s auto-wrap of sync
`Backend` (ADR-0012 § 2). Registry integration for the Graph
backend is specified in spec 044; the adapter itself is backend-
agnostic.

### [ADR-0026](0026-strict-gate-on-kwarg.md): Strict-Gate Pattern for Optional Capability Kwargs

When a caller passes an optional kwarg that requires a specific capability,
and the backend does not declare that capability, raise
`CapabilityNotSupported` **before any I/O**. Never silently drop the kwarg.

##### Naming the pattern: strict gate on kwarg

A *strict gate on kwarg* is a capability that:

1. Does not gate the method — the method works without it.
2. Does gate a specific optional argument — passing that argument requires
   the capability.
3. Raises `CapabilityNotSupported` before any I/O if the backend lacks the
   capability and the argument is supplied.

The validation happens in the Store layer (one place), not in each backend.

##### Precedent (method-level raise-before-I/O gate)

| Capability       | Gate target   | Method(s)         | Spec ref |
| ---------------- | ------------- | ----------------- | -------- |
| `ATOMIC_WRITE`   | whole method  | `write_atomic()`  | AW-002   |

`ATOMIC_WRITE` is not a strict-gate-on-kwarg instance — it gates the
entire method, not an optional kwarg. It appears here because it
established the raise-before-I/O principle that the strict-gate-on-kwarg
pattern inherits. Future contributors should not use this row as a
pattern template.

##### Strict-gate-on-kwarg instances

| Capability       | Gate target        | Method(s)             | Spec ref |
| ---------------- | ------------------ | --------------------- | -------- |
| `USER_METADATA`  | `metadata=` kwarg  | `write*()` variants   | WR-010   |

`USER_METADATA` is the first true strict-gate-on-kwarg instance. New
instances of this pattern go in this table.

##### How to apply the pattern for future capabilities

When designing a new optional kwarg on an existing Store method:

1. Define a new `Capability` enum member for the feature.
2. Add Store-layer validation: if the kwarg is non-`None` / non-default and
   the backend lacks the capability, raise `CapabilityNotSupported`.
3. Add the capability to `CAP-007` (spec 003) under the strict-gate section.
4. Document per-backend declarations in the feature spec (e.g., WR-010).
5. Add negative tests: every non-declaring backend raises on the guarded kwarg.

##### Adapter masking as a defensive application of the strict-gate pattern

`AsyncBackendSyncAdapter` applies the pattern defensively via capability masking.
It strips `USER_METADATA` (and `WRITE_RESULT_NATIVE`) from the inner async
backend's capability set, even when the wrapped backend declares them.  Without
masking, the Store-layer WR-010 gate would pass a non-empty `metadata=` argument
through to the adapter, but the adapter has no forwarding target — the async ABC
does not yet accept `metadata=`.  A silent drop would violate WR-012 (the
`WriteResult.metadata` echo guarantee) without triggering any error.

Masking is the mechanism that keeps the strict-gate invariant intact across
adapter wrapping: the gate fires at the Store layer (`CapabilityNotSupported`)
before the adapter is reached, so no I/O runs and no metadata is silently lost.
This is not an exception to the pattern; it is the same pattern applied one layer
earlier.  When the async ABC grows `metadata=` support (Step 3c), the masking is
removed and the adapter naturally inherits the inner backend's declarations.

### [ADR-0027](0027-docs-bridge-single-mechanism.md): Single Bridge with Enforcement, Not Layered Mechanisms

One documentation bridge, kept single by an enforcement gate. Three coupled
sub-decisions:

1. **One bridge, by construction** — `scripts/docs/scan.py:scan_dual_files` is the sole source-discovery function and `render.py:render_dual_pages` the sole render function; other helpers are removed, not deprecated. New content shapes extend this one mechanism rather than adding a parallel one.
2. **Classification next to the file** — each `.md` declares its class via an HTML-comment marker, with a directory-default fallback; a file with no marker and no default is unclassified and fails the gate (G-01). No central manifest that can drift from the files.
3. **Enforcement at PR time** — a check script fails the build if any framework rule is violated, so "use one bridge" cannot silently degrade to a preference.

The recurring failure across the prior ADRs was not that the chosen mechanism
was wrong; each was reasonable for the case that introduced it. The failure was
that nothing prevented the next mechanism from being added alongside — a "use
one bridge" decision without a check that detects the second bridge degrades to
a preference.

##### One bridge, by construction

`scripts/docs/scan.py:scan_dual_files` is the single source-discovery
function for dual content. `scripts/docs/render.py:render_dual_pages` is
the single render function. Other discovery and render helpers in the
docs pipeline are removed, not deprecated. New content shapes extend
this one mechanism; they do not add a parallel one. Contracts in
[spec 047](../specs/047-docs-framework-tooling.md) DOCFRAME-001,
DOCFRAME-005.

##### Classification next to the file, not in a manifest

Each `.md` file declares its class on itself via an HTML-comment marker.
Absence falls back to a directory-default rule (per
[`AUTHORING.md`](../AUTHORING.md) Rule 1 and its directory-defaults
table); a file with no marker AND no matching default is unclassified
and fails the gate (G-01). A central manifest is auditable but lives
apart from the files it classifies, so additions land in one place and
the manifest in another. The marker cannot drift from the file because
it is part of the file. Contracts in
[spec 047](../specs/047-docs-framework-tooling.md) DOCFRAME-002.

##### Enforcement at PR time

A check script (DOCFRAME-004) fails the build if any framework rule is
violated, including the "one bridge" rule itself. This is the half that
the prior ADRs left out. Without it, the next contributor under
deadline pressure adds the next mechanism and the cycle resumes.

### [ADR-0028](0028-testing-architecture-kind-stage-replay.md): Testing Architecture with Kind and Stage Axes and HTTP Replay Demotion

The testing architecture rests on five coupled commitments:

1. **Two orthogonal axes** — separate *kind* (pure, mocked, real-local, real-live) from *stage* (1/2/3 by cost); a fixture declares one of each.
2. **Conformance as the cross-backend spine** — one parametrised suite over the public `Store` / `Backend` API that every backend runs; backend-specific behaviour is isolated per backend.
3. **HTTP cassette + replay as a Stage 1 fixture** — a `<backend>_replay` fixture runs the real SDK path against a recorded cassette (Stage 3 records, Stage 1 replays); scoped to HTTP-transport backends only.
4. **Capability gating via native pytest** — parametrize id-filtering plus `pytest.mark.skipif`, no custom `@requires` marker layer.
5. **Explicit cassette refresh** — cassettes regenerate only when a developer runs `pytest --stage=3 --record` and commits the diff; CI never silently re-records.

They share rationale: the demotion mechanism only works because the axes are
separated, the gate works only because gating is native, and the scope works
only because the spec calls out where it does not apply. One ADR captures the
bundle; any commitment that later evolves can be superseded individually.

##### Two orthogonal axes: kind and stage

A linear list of "stages" running unit, emulator, live collapses two
distinct concerns. *What the test wires up* is one axis (kind: pure,
mocked, real-local, real-live). *How expensive it is to run* is
another (stage: 1, 2, 3, ordered by cost and required infrastructure).
The architecture separates them. A fixture declares one of each. Spec
contracts in [spec 048](../specs/048-testing-architecture.md) TEST-001.

A linear collapse hides real options. Replay is a real-SDK code path
that runs at Stage 1 cost; a single-axis ordering cannot express that
combination.

##### Conformance as the cross-backend spine; backend-specific tests isolated per backend

Conformance is one parametrised test set referencing only the public
`Store` and `Backend` API. Every backend that exposes the API runs
the full suite. Behaviour that only one backend exhibits, whether
protocol quirks, storage-model semantics, or vendor configuration, is
isolated to that backend's own home, separate from the spine.

Two consequences follow at once. "Add a backend, get conformance for
free" becomes the literal mechanism. And backend-specific tests gain
a home that is not interleaved with the cross-backend suite. Spec
contracts in TEST-002 and TEST-003. Layout in TEST-010.

##### HTTP cassette and replay as a Stage 1 fixture, scoped to HTTP backends

A `<backend>_replay` Stage 1 fixture exercises the real SDK code path
with the HTTP transport stubbed by a recorded cassette. Stage 3 runs
record. Stage 1 runs replay. A Stage-3-discovered behaviour, once
recorded, runs at zero cost in every default CI run. That is the
demotion mechanism the third force in the Context describes.

The mechanism applies to HTTP-transport backends only. Backends that
speak SSH binary or a DB wire protocol are not reachable by available
capture tools without a custom transport adapter, and that work is not
in scope here. For excluded backends, Stage 2 (Docker) is the cheapest
source of truth, with no Stage 3 to Stage 1 demotion path until and
unless dedicated work delivers one. Spec contracts in TEST-007 and
TEST-008.

##### Capability gating uses native pytest mechanisms

Conformance tests gate on cross-backend `Capability` values via
parametrize id-filtering and `pytest.mark.skipif`. No `@requires(...)`
custom marker layer is introduced. A reader can trace from the
parametrize call to the fixture registry without indirection or a
plugin hook.

The cost paid is verbosity in a few helper functions. The cost avoided
is a parallel marker system that needs its own conftest hook,
documentation, and IDE-tooling integration. Spec contracts in
TEST-005.

##### Cassette refresh is explicit

Cassettes regenerate when a developer runs `pytest --stage=3 --record`
and commits the diff. CI does not silently re-record. The refresh is
auditable as a normal PR. Drift between cassettes and real-service
responses is detected by the next manual refresh. A scheduled refresh
job is schedulable later if drift becomes painful. The reverse default,
scheduling from day one, couples the cost-controlled tier to a recurring
job before any empirical drift data exists. Spec contracts in TEST-009.

### [ADR-0029](0029-graph-transfer-blocking-io-offload.md): Offload Graph Transfer Spool I/O off the Event Loop

Dispatch the blocking spool I/O in `transfer.py` through `asyncio.to_thread`:
the range-fallback `_spooled_window` write/seek/read, the `spool_content`
write/tell/seek, and the `_upload_chunks` per-chunk seek+read (bundled into one
`_seek_read` hop). The spool objects are accessed sequentially under `await`, so
single-threaded offload is safe; nothing else holds the reader concurrently.

This realises ADR-0025's own prescription ("`asyncio.to_thread` for hot paths")
in-backend rather than leaving it deferred, and corrects the mischaracterised
example.

> amends ADR-0025 (clause).

### [ADR-0030](0030-azure-hns-explicit-declaration.md): Azure HNS Is an Explicit Declaration, Not Auto-Detected

The Azure backend no longer auto-detects HNS. The account's nature is a
**mandatory, explicit** constructor and config input, declared as a required
`hns: bool` on both `AzureBackend` and `AsyncAzureBackend` (no default; a
missing or non-`bool` value raises at construction).

- `AzureBackend(..., hns: bool)` and `AsyncAzureBackend(..., hns: bool)` —
  there is no default. A backend constructed without `hns`, or with a
  non-`bool` value, raises `ValueError` at construction time (fail loud, never
  silently infer). The declaration must be a real boolean, not a truthy/falsy
  proxy: config env-var resolution yields strings, so a `${VAR}` placeholder
  resolving to `"false"` would otherwise coerce to `True` via `bool(...)` and
  silently re-enable HNS — the very misdetection class this decision removes.
- `_hns` becomes an immutable attribute set from the declared value. No probe,
  no cache, no warn-once state, no per-operation snapshot.

For users who do not know an account's HNS status, a public one-shot helper
discovers it explicitly:

- `AzureUtils.detect_hns(...)` (sync) and `AzureUtils.adetect_hns(...)` (async)
  issue a single `GetAccountInfo` call and return a `bool`. Unlike the former
  implicit probe, these are **fail-loud**: a probe error is mapped to a
  `remote_store` error and raised, not swallowed and degraded to flat
  semantics.

This mirrors the established helper pattern for connection facts that are
discoverable but should not be silently inferred: `SFTPUtils.scan_host_keys`
and `GraphUtils.resolve_drive_id`.

##### Why mandatory rather than a detected default

A detected default reintroduces every failure mode above: the probe can fail,
return stale authorization state, or be denied. A declared value cannot. The
small one-time cost — the user must state a fact they already know, or call
`detect_hns()` once — buys the removal of an entire failure class and makes the
backend's behaviour deterministic from construction.

##### Migration

This is a breaking change: every existing Azure call site must add `hns=`.
Pre-v1 semver permits the change in a minor bump. The migration guide documents
the before/after and the `detect_hns()` discovery recipe.

### [ADR-0031](0031-expert-personas-as-subagent-files.md): Expert Personas as Standalone Subagent Files

Each expert persona is a **standalone Claude Code subagent** in
`.claude/agents/<name>.md` — the single source of truth for that persona.
The `/orchestrate` skill no longer embeds personas; it references each expert by
`subagent_type` (in its Step 4 execute sections) and supplies the per-call task
and mode in the invocation prompt.

- **Repo-root-relative paths.** Personas cite `sdd/TESTING.md` etc. as plain
  paths (agents run with cwd at the repo root).
- **Per-call context via the prompt.** The static persona holds identity, domain,
  constraints, and done-when; the invocation prompt carries the task, the specs
  to trace, and the mode (implement vs review).

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
