# Research: Store Middleware Architecture

**Date:** 2025-03-17
**Scope:** ID-006 (progress callbacks), ID-008 (checksum verification),
and the broader question of how cross-cutting concerns compose with the
existing proxy-subclass pattern (ADR-0010).

---

## 1. Problem Statement

ID-006 (progress callbacks on `read`/`write`) and ID-008 (checksum
verification on `read`/`write`) are cross-cutting concerns that overlap
with existing extensions:

| Concern | Where it lives today | Where ID-006/008 would add it |
|---------|---------------------|-------------------------------|
| Progress | `ext.transfer` (`on_progress` on `upload`/`download`) | `Store.read()` / `Store.write()` |
| Checksums | `FileInfo.checksum` (metadata only, not verified) | `Store.read()` / `Store.write()` |
| Observation | `ext.observe` (timing, hooks) | — |
| Caching | `ext.cache` (TTL, invalidation) | — |

The worst-case composition today looks like:

```python
observe(cached_store(store, ttl=300), on_read=log_it)
```

Adding ID-006 and ID-008 as separate proxy-subclass wrappers would produce:

```python
observe(
    cached_store(
        checksum_store(
            progress_store(store),
        ),
        ttl=300,
    ),
    on_read=log_it,
)
```

This raises several concerns:

1. **Performance:** Each proxy layer adds a method call per operation.
   Four layers = four `__getattr__`-free but still four Python function
   calls, four `time.monotonic()` measurements, four try/except blocks.
2. **Ordering sensitivity:** Cache must sit outside checksum (otherwise
   cached reads skip verification). Progress must sit inside cache
   (otherwise cache hits still fire progress). Getting the order wrong
   silently breaks semantics.
3. **Iterator materialization:** Both ObservedStore and CachedStore
   materialize iterators (`list()` / `tuple()`) to measure timing or
   cache results. Two layers = two materializations.
4. **Private attribute coupling:** Both wrappers copy `_backend`,
   `_root`, `_owns_backend` from the inner store — fragile and violates
   ADR-0008's "public API only" rule.
5. **`child()` breaks the chain:** `cached_store(s).child("sub")` returns
   a plain `Store`, losing the cache wrapper. Same for ObservedStore.
6. **Method override burden:** Every new Store method requires overrides
   in every proxy. Drift-protection tests catch missing overrides, but
   the boilerplate grows linearly with `(methods × wrappers)`.
7. **Dual progress mechanisms:** `ext.transfer` wraps BinaryIO with
   `_ProgressReader`; ID-006 would add `callback` params to Store. Two
   independent progress systems with no composition story.

---

## 2. Design Options

### Option A: Add ID-006/008 as Store Parameters

Add `on_progress` and `verify_checksum` parameters directly to
`Store.read()` and `Store.write()`.

```python
store.read("file.bin", on_progress=update_bar)
store.write("file.bin", data, verify_checksum=True)
```

**Pros:**
- Zero wrapping, zero layers.
- Obvious API — no composition puzzle.
- `ext.transfer` could delegate to Store's `on_progress`.

**Cons:**
- Widens the core Store API with optional parameters — every backend
  must handle them (or Store must implement them generically).
- Every proxy wrapper must forward these new parameters.
- Checksum verification in Store couples Store to hashing logic.
- Violates the "Store is a thin shim" design (ADR-0001).
- Streaming progress on `read()` returning `BinaryIO` is awkward:
  Store can't track reads on a stream it hands back to the caller.

**Verdict:** Partially viable for `write()` (Store controls the full
data flow), problematic for `read()` (caller controls the stream).

---

### Option B: Separate Proxy-Subclass Wrappers (Status Quo Extended)

Add `ProgressStore` and `ChecksumStore` as new proxy subclasses
following ADR-0010.

**Pros:**
- Consistent with existing pattern.
- Each concern is isolated in its own module.
- Drift-protection tests are proven.

**Cons:**
- All the nesting problems from Section 1.
- Four proxy layers for the full-feature case.
- Ordering is the user's problem.

**Verdict:** Works mechanically but doesn't scale. The nesting depth
and ordering sensitivity become a real usability problem.

---

### Option C: Middleware Pipeline (Single Proxy)

Replace the N-proxy pattern with a single `PipelinedStore` that runs
operations through an ordered list of middleware.

```python
store = pipeline(
    store,
    ChecksumMiddleware(verify=True),
    CacheMiddleware(ttl=300),
    ProgressMiddleware(callback=update_bar),
    ObserveMiddleware(on_read=log_it),
)
```

Each middleware implements a protocol:

```python
class StoreMiddleware(Protocol):
    def on_read(self, ctx: OpContext, next: NextFn) -> BinaryIO: ...
    def on_write(self, ctx: OpContext, next: NextFn) -> None: ...
    def on_list(self, ctx: OpContext, next: NextFn) -> Iterator[FileInfo]: ...
    # ... per operation
```

**Pros:**
- Single wrapper layer — one proxy, one set of private-attribute copies.
- Ordering is explicit and controlled by the pipeline.
- Middleware are simple, focused functions.
- `child()` can propagate the pipeline.

**Cons:**
- Major architectural change — breaks existing ObservedStore / CachedStore API.
- Every middleware needs the full method matrix (same override burden, different shape).
- The `next()` chain is really just nested calls with extra steps.
- Middleware that need state (cache) become awkward as protocol implementations.
- ASGI-style middleware is designed for a single request/response shape; Store has 27
  methods with different signatures — poor fit.

**Verdict:** Intellectually appealing but over-engineered for the actual
problem. The method signature diversity makes a generic pipeline
clumsy. And stateful middleware (cache) needs more than before/after hooks.

---

### Option D: Aspect Composition in a Single Proxy

One proxy wraps the inner Store and composes multiple "aspects" — but
instead of a generic pipeline, each aspect integrates at specific
well-defined hook points. The proxy dispatches to aspects at those points.

```python
store = enhanced(
    store,
    observe=ObserveAspect(on_read=log_it),
    cache=CacheAspect(ttl=300),
    checksum=ChecksumAspect(verify=True),
    progress=ProgressAspect(callback=update_bar),
)
```

**Pros:**
- Single wrapper, single `_backend`/`_root` copy.
- Aspects can be strongly typed (not generic middleware).
- The proxy knows the dispatch order (cache before checksum, etc.).

**Cons:**
- Still need the full method-override matrix in the proxy.
- Aspects that need to short-circuit (cache) need special treatment.
- Tight coupling between the proxy and all aspect types.
- Loses the independent-module benefit of separate extensions.

**Verdict:** Solves the nesting problem but creates a god-object proxy.
The independently-releasable, independently-testable extension modules
are a real strength of the current design. Merging them into one proxy
loses that.

---

### Option E: Stream Wrappers + Extension Hooks (Recommended)

Keep the proxy-subclass pattern for concerns that genuinely need to
intercept Store operations (observe, cache). Move ID-006 and ID-008 to
**stream-level wrappers** and **extension functions** instead of Store
proxies.

#### E.1: Progress (ID-006) — Stream Wrapper

Progress is fundamentally a stream concern, not a Store concern. The
pattern already exists in `ext.transfer._ProgressReader`. Generalize it:

```python
# remote_store.ext.streams (new module)

class ProgressReader:
    """BinaryIO wrapper that fires callback(bytes_read) per read()."""
    def __init__(self, inner: BinaryIO, callback: Callable[[int], None]): ...

class ProgressWriter:
    """Writable wrapper that fires callback(bytes_written) per write()."""
    def __init__(self, inner: BinaryIO, callback: Callable[[int], None]): ...
```

Usage:

```python
# Direct use
stream = ProgressReader(store.read("file.bin"), callback=update_bar)
with stream:
    process(stream)

# Via transfer (already works — refactor to use shared ProgressReader)
upload(store, local, remote, on_progress=update_bar)
```

**Why this works:**
- Progress is a per-stream concern. The stream is the natural boundary.
- No Store wrapping needed. No ordering puzzle.
- `ext.transfer` already does this — we just generalize and export it.
- Works with any `BinaryIO`, including from `open_atomic()`.
- Cache layer is irrelevant: if the data comes from cache, there's no
  stream to wrap (it's already `bytes`). That's correct behavior — a
  cache hit shouldn't fire progress events.

For `write()` the situation is slightly different: Store.write() accepts
`BinaryIO | bytes`. For bytes, progress is meaningless (it's
instantaneous). For BinaryIO, the caller wraps before passing in:

```python
store.write("file.bin", ProgressReader(my_stream, callback=bar))
```

**Convenience:** Add a `read_with_progress()` helper to `ext.streams`:

```python
def read_with_progress(store: Store, path: str,
                       callback: Callable[[int], None]) -> BinaryIO:
    """Read with progress tracking. Caller must close the stream."""
    return ProgressReader(store.read(path), callback)
```

#### E.2: Checksum (ID-008) — Dual Design

Checksums have two distinct use cases:

**Use case A: Verify after transfer (extension function).**
"I downloaded a file — does it match the expected checksum?"

```python
# remote_store.ext.integrity (new module)

def verify(store: Store, path: str,
           expected: str, algorithm: str = "sha256") -> bool:
    """Read file and verify checksum matches expected value."""

def checksum(store: Store, path: str,
             algorithm: str = "sha256") -> str:
    """Compute checksum of a file in the store."""
```

This is a pure function over Store's public API. No wrapping needed.
Works with any store, including cached or observed stores.

**Use case B: Verify during transfer (stream wrapper).**
"I'm uploading — compute checksum as bytes flow through."

```python
class ChecksumReader:
    """BinaryIO wrapper that computes a rolling checksum."""
    def __init__(self, inner: BinaryIO, algorithm: str = "sha256"): ...
    def hexdigest(self) -> str: ...

class ChecksumWriter:
    """Writable wrapper that computes checksum of written bytes."""
    def __init__(self, inner: BinaryIO, algorithm: str = "sha256"): ...
    def hexdigest(self) -> str: ...
```

Usage:

```python
stream = ChecksumReader(store.read("file.bin"))
data = stream.read()
assert stream.hexdigest() == expected_checksum
```

**Use case C: Populate `FileInfo.checksum` across backends.**
This is a backend concern, not a Store concern. Each backend can
populate `FileInfo.checksum` using native APIs:

- S3: ETag (already available in response headers)
- Azure: Content-MD5 header
- Local: compute on `get_file_info()` (opt-in, since it requires reading the file)
- SFTP: `stat` doesn't provide checksums; compute on demand
- HTTP: ETag (already populated)

This can be done incrementally per backend without any Store API change.

#### E.3: Observed + Cached Stay as Proxy Subclasses

ObservedStore and CachedStore genuinely need to intercept operations —
they can't be done as stream wrappers or utility functions. They stay
as proxy subclasses per ADR-0010.

But we fix the private-attribute coupling:

```python
class Store:
    # New: protected constructor for proxy subclasses
    @classmethod
    def _proxy(cls, inner: 'Store') -> 'Store':
        """Create a proxy shell that delegates to *inner*."""
        proxy = object.__new__(cls)
        proxy._backend = inner._backend
        proxy._root = inner._root
        proxy._owns_backend = False
        return proxy
```

This keeps the coupling but makes it explicit and centralized. If
Store's internals change, only `_proxy()` needs updating.

#### E.4: Composition Depth

With Option E, the worst case becomes:

```python
observed = observe(cached_store(store, ttl=300), on_read=log_it)
# Progress and checksum are at the stream level, not store level:
stream = ProgressReader(
    ChecksumReader(observed.read("file.bin")),
    callback=update_bar,
)
```

Two proxy layers max (observe + cache), plus lightweight stream wrappers
that only exist for the duration of the I/O operation. This is
comparable to wrapping a file object with `io.BufferedReader` — standard
Python I/O practice.

---

### Option F: Category-Scoped Middleware + Proxy Subclass (C+B Hybrid)

The 27 Store methods aren't uniform — they fall into distinct categories
that have different interception needs. Instead of one generic pipeline
for everything, define middleware protocols per operation **category**,
and let one thin proxy dispatch through short, focused chains.

**Operation categories:**

| Category | Methods | Interception need |
|----------|---------|-------------------|
| **data-read** | `read`, `read_bytes`, `read_text` | progress, checksum, cache, observe |
| **data-write** | `write`, `write_text`, `write_atomic`, `open_atomic` | progress, checksum, observe, cache-invalidate |
| **browse** | `list_files`, `list_folders`, `iter_children`, `glob`, `exists`, `is_file`, `is_folder`, `get_file_info`, `get_folder_info` | cache, observe |
| **manage** | `delete`, `delete_folder`, `move`, `copy` | observe, cache-invalidate |
| **utility** | `ping`, `close`, `child`, `to_key`, `unwrap`, `native_path`, `supports` | observe (optionally), pass-through |

Each category gets a small protocol:

```python
class ReadMiddleware(Protocol):
    def on_read(self, ctx: ReadContext, next: Callable) -> BinaryIO: ...
    def on_read_bytes(self, ctx: ReadContext, next: Callable) -> bytes: ...

class WriteMiddleware(Protocol):
    def on_write(self, ctx: WriteContext, next: Callable) -> None: ...

class BrowseMiddleware(Protocol):
    def on_list(self, ctx: ListContext, next: Callable) -> Iterator: ...
    def on_check(self, ctx: CheckContext, next: Callable) -> bool: ...
```

The proxy holds one middleware chain per category:

```python
store = middleware_store(
    store,
    read=[CacheRead(ttl=300), ObserveRead(on_read=log_it)],
    write=[ChecksumWrite(verify=True), ObserveWrite(on_write=log_it)],
    browse=[CacheBrowse(ttl=300), ObserveBrowse(on_list=log_it)],
    manage=[ObserveManage(on_delete=log_it)],
)
```

**Pros:**
- Single proxy layer — one `_backend`/`_root` copy.
- Category-scoped protocols are small and focused (3-5 methods each),
  not a 27-method god-interface.
- Ordering is explicit per category (read chain vs write chain).
- Middleware only implements the categories it cares about: cache
  implements `ReadMiddleware` + `BrowseMiddleware`, observe implements
  all four.
- `child()` can propagate the middleware stack.
- New Store methods only require updating the relevant category
  protocol, not every middleware.

**Cons:**
- Still a new architecture — existing ObservedStore/CachedStore would
  need rewriting as middleware implementations.
- Five protocols + dispatch logic is more conceptual surface than the
  current pattern.
- Cache needs short-circuit semantics (return early on hit, skip
  `next()`). That's natural in a middleware chain (`next()` is optional)
  but differs from the observe pattern where `next()` always runs.
- Middleware authors must understand the chain dispatch model.
- Moderate breaking change: `observe()` and `cached_store()` factories
  would either change signature or become wrappers around middleware
  registration.

**When it shines:**
The category-scoped approach avoids the god-object problem of Option D
while still collapsing N proxies into one. It's particularly strong
when multiple concerns touch the same category (e.g., cache + progress
+ checksum all on reads). Each middleware in the chain handles its
concern and calls `next()`:

```python
# Read chain: cache → checksum → progress → inner store
class CacheRead:
    def on_read_bytes(self, ctx, next):
        cached = self.lookup(ctx.path)
        if cached is not _MISSING:
            return cached
        result = next(ctx)               # calls next middleware
        self.store(ctx.path, result)
        return result

class ChecksumRead:
    def on_read_bytes(self, ctx, next):
        result = next(ctx)
        if ctx.expected_checksum:
            verify(result, ctx.expected_checksum)
        return result
```

**Verdict:** The cleanest single-proxy approach. The per-category
protocols keep each middleware focused. The main cost is rewriting
observe and cache as middleware — but the resulting code is likely
shorter than the current proxy overrides. Worth considering if the
proxy-subclass boilerplate is already causing maintenance pain.

---

### Option G: Enhanced E with Shared Proxy Infrastructure

Keep Option E's stream-wrapper approach for progress/checksums, but
additionally reduce the boilerplate in ObservedStore and CachedStore
by extracting their common infrastructure into a shared `ProxyStore`
base class.

**The repetition problem today:**

ObservedStore and CachedStore each independently:
1. Bypass `Store.__init__` and copy `_backend`, `_root`, `_owns_backend`.
2. Override all 27 public methods (even the ~10 that just delegate).
3. Materialize iterators (observe: `list()`, cache: `tuple()`).
4. Break the wrapper chain on `child()`.
5. Maintain a drift-protection test.

The shared base:

```python
class ProxyStore(Store):
    """Base for Store proxies. Handles delegation boilerplate."""

    _inner: Store

    def __init__(self, inner: Store) -> None:
        # Centralized private-attribute coupling (replaces ad-hoc copies)
        self._inner = inner
        self._backend = inner._backend
        self._root = inner._root
        self._owns_backend = False

    # --- Default: delegate everything to inner ---

    def read(self, path: str) -> BinaryIO:
        return self._inner.read(path)

    def read_bytes(self, path: str) -> bytes:
        return self._inner.read_bytes(path)

    def write(self, path: str, content: WritableContent, *,
              overwrite: bool = False) -> None:
        self._inner.write(path, content, overwrite=overwrite)

    # ... all 27 methods delegating to self._inner ...

    def child(self, subpath: str) -> Store:
        """Override in subclass to propagate the proxy."""
        return self._inner.child(subpath)

    @property
    def inner(self) -> Store:
        return self._inner
```

Now ObservedStore and CachedStore only override what they actually
change:

```python
class ObservedStore(ProxyStore):
    """Only overrides methods that need hook dispatch."""

    def __init__(self, inner, *, hooks, around):
        super().__init__(inner)
        self._hooks = hooks
        self._around = around

    # Override only to add timing/hooks — delegate via super()
    def read(self, path: str) -> BinaryIO:
        with self._observe_op("read", path, {}):
            return super().read(path)

    def read_bytes(self, path: str) -> bytes:
        with self._observe_op("read_bytes", path, {}):
            return super().read_bytes(path)

    # Methods that don't need observation? Don't override.
    # ProxyStore handles delegation.
```

Wait — ObservedStore observes **every** method (that's its contract).
So it still overrides everything. The savings come from:

1. **CachedStore pass-through methods disappear.** CachedStore currently
   has ~10 methods that just do `return self._inner.foo(...)`. With
   ProxyStore, those are inherited — only the cached reads and
   invalidating writes need explicit overrides.
2. **`__init__` coupling centralized.** `_backend`/`_root`/`_owns_backend`
   coupling lives in one place.
3. **`child()` propagation** can be implemented once in ProxyStore
   (configurable) instead of duplicated.
4. **Drift-protection test** can be shared: "ProxyStore must override
   every public Store method; subclasses may override a subset."
5. **Iterator materialization helper** in ProxyStore:
   ```python
   def _materialize_iter(self, it: Iterator[T]) -> Iterator[T]:
       """Materialize an iterator for timing/caching, return a fresh iter."""
       items = tuple(it)
       return iter(items)
   ```

**Combined with E's stream wrappers:**

```
User code
  └─ observe(cached_store(store))    ← 2 ProxyStore layers (reduced boilerplate)
       └─ ProgressReader(stream)     ← stream-level, no Store proxy
            └─ ChecksumReader(stream) ← stream-level, no Store proxy
```

**Pros:**
- Keeps the proven proxy-subclass pattern (ADR-0010) — no new dispatch model.
- Reduces CachedStore from ~500 lines to ~300 (pass-throughs eliminated).
- Private-attribute coupling in one place.
- `child()` propagation solvable in the base.
- Stream wrappers (from E) handle progress/checksums at the right level.
- **No breaking change** to public API — `observe()` and `cached_store()`
  factories stay the same.
- New proxy-subclass extensions (future retry, circuit breaker) get
  the base for free.

**Cons:**
- ObservedStore still overrides everything (it observes all ops), so
  its line count doesn't shrink much. The win is mostly in CachedStore
  and future extensions.
- Two-level inheritance (`Store → ProxyStore → CachedStore`) adds one
  layer of indirection.
- `super().read(path)` in ObservedStore calls `ProxyStore.read()` which
  calls `self._inner.read()` — one extra hop, though Python inlines this
  reasonably well.

**Variant G2: ProxyStore with operation-class hooks.**

Instead of subclasses overriding individual methods, ProxyStore offers
category-level hooks that subclasses opt into:

```python
class ProxyStore(Store):

    def _before_read(self, op: str, path: str) -> Any:
        """Called before any read operation. Return context or None."""
        return None

    def _after_read(self, op: str, path: str, result: Any, ctx: Any) -> Any:
        """Called after any read operation. Can transform result."""
        return result

    def _before_write(self, op: str, path: str) -> Any:
        return None

    def _after_write(self, op: str, path: str, ctx: Any) -> None:
        pass

    def _before_browse(self, op: str, path: str) -> Any:
        return None

    def _after_browse(self, op: str, path: str, result: Any, ctx: Any) -> Any:
        return result

    def _short_circuit_read(self, op: str, path: str) -> Any | _MISSING:
        """Return cached value or _MISSING to proceed to inner store."""
        return _MISSING

    # The proxy dispatches through these hooks:
    def read_bytes(self, path: str) -> bytes:
        short = self._short_circuit_read("read_bytes", path)
        if short is not _MISSING:
            return short
        ctx = self._before_read("read_bytes", path)
        result = self._inner.read_bytes(path)
        return self._after_read("read_bytes", path, result, ctx)
```

Now ObservedStore implements `_before_read` / `_after_read` (timing +
hooks) and CachedStore implements `_short_circuit_read` / `_after_read`
(cache lookup / cache store). Neither overrides individual methods.

```python
class ObservedStore(ProxyStore):
    def _before_read(self, op, path):
        return time.monotonic()  # context = start time

    def _after_read(self, op, path, result, ctx):
        elapsed = (time.monotonic() - ctx) * 1000
        self._fire(op, path, {}, ctx, elapsed, None)
        return result

class CachedStore(ProxyStore):
    def _short_circuit_read(self, op, path):
        return self._cache_get((op, path))

    def _after_read(self, op, path, result, ctx):
        self._cache.set((op, path), result, self._ttl)
        return result
```

**Pros over plain G:**
- Zero per-method overrides in either ObservedStore or CachedStore.
- Adding a new Store method means adding it once in ProxyStore's
  dispatch; all subclasses automatically hook into it via category hooks.
- Drift protection becomes unnecessary — hooks are called by the base,
  not by per-method overrides.

**Cons:**
- `_before` / `_after` / `_short_circuit` is essentially a mini
  middleware system baked into the base class. It's Option F's
  per-category dispatch, but inheritance-based rather than
  composition-based.
- Harder to type-check: `_after_read` returns `Any` because different
  read methods return different types.
- Error handling paths (observe needs to fire `on_error` on exceptions)
  require `_on_error` hooks, growing the protocol.
- Two hook-based subclasses can't easily compose (you can't stack
  two ProxyStores that both implement `_after_read` — only one wins
  via MRO). Composition still requires nesting.

**Verdict:** G is the pragmatic evolution — it reduces boilerplate while
preserving the proven pattern. G2 is elegant but effectively reinvents
a dispatch framework inside the base class, converging with Option F.
If you're going to build a dispatch framework, F's explicit composition
is cleaner than G2's inheritance-based hooks.

---

### Option H: E + F Internals (Stream Wrappers + Internal Middleware Reuse)

Combine E's public design (stream wrappers for progress/checksums,
extension functions for integrity) with F's internal architecture
(category-scoped middleware under the hood) — but **without exposing
the middleware model to users**.

The key insight: users don't need to know about middleware. They use
the same `observe()` and `cached_store()` factories they use today.
But internally, both are implemented as middleware plugged into a
shared `_MiddlewareProxy`:

```python
# Public API — unchanged
observed = observe(store, on_read=log_it)
cached = cached_store(store, ttl=300)
both = observe(cached_store(store, ttl=300), on_read=log_it)

# Internal: observe() creates a _MiddlewareProxy with ObserveMiddleware
# cached_store() creates a _MiddlewareProxy with CacheMiddleware
# Nesting two _MiddlewareProxies: the outer detects the inner is also
# a _MiddlewareProxy and MERGES the middleware chains instead of wrapping.
```

**Middleware merging — the key trick:**

```python
def observe(store, **hooks):
    mw = _ObserveMiddleware(hooks)
    if isinstance(store, _MiddlewareProxy):
        # Merge: add observe middleware to existing proxy's chain.
        return store._with_middleware(mw)
    return _MiddlewareProxy(store, [mw])

def cached_store(store, ttl=300, ...):
    mw = _CacheMiddleware(ttl, ...)
    if isinstance(store, _MiddlewareProxy):
        return store._with_middleware(mw)
    return _MiddlewareProxy(store, [mw])
```

So `observe(cached_store(store))` produces **one** `_MiddlewareProxy`
with two middleware in its chain, not two nested proxies.

```
# What users write:
observe(cached_store(store, ttl=300), on_read=log_it)

# What they get internally:
_MiddlewareProxy(
    inner=store,
    chain=[_CacheMiddleware(ttl=300), _ObserveMiddleware(hooks)],
)
```

**Combined with stream wrappers for progress/checksums:**

```python
stream = ProgressReader(
    ChecksumReader(both.read("file.bin")),
    callback=update_bar,
)
```

**Category-scoped dispatch inside `_MiddlewareProxy`:**

```python
class _MiddlewareProxy(ProxyStore):
    def read_bytes(self, path: str) -> bytes:
        def inner_call():
            return self._inner.read_bytes(path)

        call = inner_call
        # Build chain in reverse (last middleware wraps innermost)
        for mw in reversed(self._chain):
            if hasattr(mw, 'on_read_bytes'):
                prev = call
                call = lambda prev=prev, mw=mw: mw.on_read_bytes(path, prev)
        return call()
```

**Pros:**
- **Zero nesting** even when composing observe + cache + future middleware.
  `observe(cached_store(store))` = one proxy, one `_backend` copy.
- **Public API unchanged.** `observe()` and `cached_store()` look and
  behave identically. `isinstance(result, Store)` still holds.
- **Stream wrappers** (from E) handle progress/checksums correctly.
- **Ordering is deterministic:** middleware merging preserves insertion
  order. Cache middleware runs before observe middleware.
- **New concerns are additive:** a future `RetryMiddleware` just
  registers into the chain. No new proxy subclass needed.
- **`child()` propagation** is trivial: `_MiddlewareProxy` creates a
  child with the same middleware chain.
- **Drift protection simplified:** one proxy class, one set of method
  dispatchers. Middleware don't override Store methods.

**Cons:**
- Internal complexity: the middleware chain, merging logic, and
  per-category dispatch are non-trivial internal machinery.
- Debugging: when something goes wrong, the user sees a single proxy
  with a chain — stack traces go through dispatch functions rather
  than named method overrides.
- Migration: existing ObservedStore / CachedStore tests assume specific
  class types. `isinstance(x, ObservedStore)` would need to still work
  (the proxy would need to masquerade or the classes become thin shells).
- Type narrowing: `observed.stats` (CachedStore-specific) or
  `observed.inner` need to remain discoverable. If the merged proxy is a
  generic `_MiddlewareProxy`, these accessors need a different home
  (e.g., `cached_store()` returns a `_MiddlewareProxy` subclass that
  exposes `.stats`).

**Verdict:** Most architecturally clean solution for the long term.
The middleware merging eliminates the nesting problem entirely, and
the unchanged public API means no breaking changes. The internal
complexity is real but contained — users never see it. The question
is whether the current two-wrapper case (observe + cache) justifies
this investment, or whether it's premature until a third or fourth
concern needs to compose.

---

## 3. Comparison Matrix

| Criterion | A (params) | B (proxies) | C (pipeline) | D (aspects) | E (streams) | F (cat. mw) | G (proxy base) | **H (E+F merged)** |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Max proxy depth | 0 | 4 | 1 | 1 | 2 | 1 | 2 | **1** |
| Core API change | yes | no | major | major | no | moderate | no | **no** |
| Ordering puzzle | n/a | user's | explicit | explicit | n/a | explicit | user's | **auto (merge)** |
| `child()` works | yes | no | fixable | fixable | no | fixable | fixable | **yes** |
| Stream progress | awkward | awkward | possible | possible | native | possible | native | **native** |
| Cache hit + progress | wrong | order-dep | config | config | correct | correct | correct | **correct** |
| Backend changes | yes | no | no | no | no | no | no | **no** |
| Breaking change | yes | no | yes | yes | no | moderate | no | **no** |
| Independently testable | n/a | yes | partial | no | yes | yes | yes | **yes** |
| `ext.transfer` reuse | possible | no | possible | possible | yes | possible | yes | **yes** |
| Boilerplate reduction | n/a | worse | good | good | none | good | moderate | **good** |
| Internal complexity | low | low | high | high | low | moderate | low | **moderate** |
| Migration effort | moderate | low | high | high | none | high | low | **moderate** |

---

## 4. Recommendation

Two viable paths depending on appetite for internal refactoring.

### Path 1 (Incremental): Option G + E — ProxyStore Base + Stream Wrappers

**Do this if:** we want to ship ID-006 and ID-008 soon with minimal
disruption, and improve the internal structure incrementally.

1. Extract `ProxyStore` base class from shared ObservedStore/CachedStore
   infrastructure. Centralizes `_backend`/`_root` coupling, adds
   `_materialize_iter()`, enables `child()` propagation.
2. Build `ext.streams` (ProgressReader, ChecksumReader, etc.) — stream-
   level wrappers for progress and checksums.
3. Build `ext.integrity` (verify, checksum) — pure functions.
4. Refactor `ext.transfer` to use public `ProgressReader`.

**Why G+E:**
- No breaking changes, no new dispatch model.
- ProxyStore reduces CachedStore by ~100 lines and eliminates the
  duplicated init coupling.
- Stream wrappers put progress/checksums at the right abstraction level.
- Cache hit correctly skips progress/checksum (no stream to wrap).
- Future proxy subclasses (retry, circuit breaker) inherit ProxyStore.

**Trade-off:** Two proxy layers remain when composing observe + cache.
Acceptable for now — the performance cost is two Python function calls
per operation, well under 1μs.

### Path 2 (Architectural): Option H — Merged Middleware + Stream Wrappers

**Do this if:** we're willing to invest in a deeper refactor that
eliminates nesting entirely and sets up the architecture for 3+
composable concerns.

1. Build the internal `_MiddlewareProxy` with category-scoped dispatch
   and middleware merging.
2. Reimplement `observe()` and `cached_store()` as thin factories that
   register middleware into the proxy (public API unchanged).
3. Build `ext.streams` and `ext.integrity` (same as Path 1).
4. Future concerns (retry, rate-limit, circuit breaker) are just new
   middleware — no new proxy subclasses.

**Why H:**
- `observe(cached_store(store))` → one proxy, zero nesting.
- `child()` propagation is trivial (copy the chain).
- Ordering is automatic (insertion order during merging).
- The public API doesn't change — `observe()` and `cached_store()`
  still return Store-compatible objects.

**Trade-off:** More internal complexity. The middleware chain + merging
logic is ~150 lines of framework code. Justified when there are 3+
concerns that need to compose; possibly premature for just observe +
cache.

### Recommended Decision Criteria

| If... | Then... |
|-------|---------|
| Only observe + cache compose (current state) | **Path 1 (G+E)** — simpler, less risk |
| Retry, rate-limit, or circuit breaker are on the near-term roadmap | **Path 2 (H)** — invest in the infrastructure now |
| Uncertain | **Path 1 now, Path 2 later** — ProxyStore is a stepping stone toward middleware; the refactor from G to H is easier than from the current code to H |

### What to Build (Both Paths)

| Module | Contents | Spec needed? |
|--------|----------|:------------:|
| `ext.streams` | `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter`, `read_with_progress()` | Yes (new spec) |
| `ext.integrity` | `verify()`, `checksum()` | Yes (new spec) |
| Backend changes | Populate `FileInfo.checksum` in S3, Azure, Local backends | Amend spec 001 |

### What to Build (Path 1 only)

| Module | Contents | Spec needed? |
|--------|----------|:------------:|
| `_proxy.py` (internal) | `ProxyStore` base class | No (internal refactor, amend ADR-0010) |

### What to Build (Path 2 only)

| Module | Contents | Spec needed? |
|--------|----------|:------------:|
| `_middleware.py` (internal) | `_MiddlewareProxy`, category protocols, merging logic | Yes (new ADR) |
| Rewrite observe/cache | As middleware implementations | Amend existing specs |

### What NOT to Build (Either Path)

- No `ProgressStore` proxy.
- No `ChecksumStore` proxy.
- No changes to `Store.read()` or `Store.write()` signatures.
- No public middleware API (internal only — users use `observe()` and
  `cached_store()` as before).

---

## 5. Open Questions

1. **`child()` propagation for ObservedStore / CachedStore.**
   This is an existing issue (not introduced by this design) but worth
   fixing. Both paths (G+E and H) enable `child()` propagation. Decision:
   should child stores inherit the full wrapper config, or should it be
   opt-in? (e.g., `observe(store, propagate_child=True)`)

2. **`FileInfo.checksum` population scope.**
   Should `get_file_info()` always compute checksums (expensive for local
   filesystem), or should it be opt-in? An `include_checksum=True`
   parameter on `get_file_info()` would keep the default fast but allow
   explicit requests. Alternatively, `ext.integrity.checksum()` covers
   this without any API change.

3. **Checksum algorithm consistency.**
   S3 uses MD5-based ETags, Azure uses MD5, local would use SHA-256.
   Should `FileInfo.checksum` include the algorithm prefix
   (e.g., `sha256:abcdef...`) or should it be opaque? A prefix is more
   useful for verification.

4. **Path 1 → Path 2 migration.**
   If we start with Path 1 (ProxyStore) and later want Path 2
   (middleware merging), how disruptive is the internal migration?
   ProxyStore's method-delegation pattern maps cleanly to middleware
   dispatch, so the migration should be internal-only (no public API
   change). But the test suite would need updating.

5. **Middleware ordering in Path 2.**
   When `observe(cached_store(store))` merges into one proxy, which
   middleware runs first? Cache should run before observe (so cache hits
   are observed). The merge logic needs a defined ordering strategy:
   insertion order (natural), explicit priority, or category-based rules.

---

## 6. Impact on Existing Backlog Items

| Item | Impact |
|------|--------|
| ID-006 (progress) | Redesigned as `ext.streams` (stream wrappers, not Store params) |
| ID-008 (checksums) | Split: `ext.integrity` (functions) + `ext.streams` (stream wrappers) + backend `FileInfo.checksum` |
| ID-023 (transfer) | Refactor to use public `ProgressReader` from `ext.streams` |
| ID-024 (observe) | No change; stays as proxy subclass |
| ID-025 (cache) | No change; stays as proxy subclass |

---

## 7. Next Steps

1. **Decision:** Choose Path 1 (G+E) or Path 2 (H). See decision
   criteria in Section 4.
2. **Either path — shared first steps:**
   a. Create spec for `ext.streams` (progress + checksum stream wrappers).
   b. Create spec for `ext.integrity` (verify/checksum functions).
   c. Amend ID-006 and ID-008 descriptions in BACKLOG.md to reference
      this research.
3. **Path 1 additional steps:**
   a. Extract `ProxyStore` base class (internal refactor).
   b. Amend ADR-0010 to document ProxyStore.
   c. Refactor ObservedStore and CachedStore to extend ProxyStore.
   d. Add `child()` propagation.
4. **Path 2 additional steps:**
   a. New ADR for internal middleware architecture.
   b. Build `_MiddlewareProxy` with category dispatch + merging.
   c. Reimplement observe and cache as middleware.
   d. Update specs 019 (observe) and 023 (cache) for internal changes.
5. **Both paths — implementation:**
   a. Implement `ext.streams` (enables ID-006, refactors transfer).
   b. Implement `ext.integrity` (enables ID-008).
   c. Backend `FileInfo.checksum` population per backend.
