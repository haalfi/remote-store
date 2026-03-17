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

## 3. Comparison Matrix

| Criterion | A (params) | B (more proxies) | C (pipeline) | D (aspects) | **E (streams + ext)** |
|-----------|:----------:|:-----------------:|:------------:|:-----------:|:---------------------:|
| Max proxy depth | 0 | 4 | 1 | 1 | **2** |
| Core API change | yes | no | yes (major) | yes (major) | **no** |
| Ordering puzzle | n/a | yes (user's problem) | explicit | explicit | **n/a** |
| `child()` works | yes | no | fixable | fixable | **no (existing issue)** |
| Stream-level progress | awkward | awkward | possible | possible | **native** |
| Cache hit + progress | fires (wrong) | depends on order | configurable | configurable | **silent (correct)** |
| Backend changes needed | yes | no | no | no | **no** |
| Breaking change | yes | no | yes | yes | **no** |
| Independently testable | n/a | yes | partially | no | **yes** |
| `ext.transfer` reuse | possible | no | possible | possible | **yes (direct)** |

---

## 4. Recommendation: Option E (Stream Wrappers + Extension Functions)

### Why

1. **Right abstraction level.** Progress and checksums are properties of
   data flow, not of store operations. A stream wrapper is the natural
   place for them — it's where the bytes actually flow.

2. **No core API change.** Store stays a thin shim (ADR-0001). No new
   parameters to forward through every proxy.

3. **No ordering puzzle.** Stream wrappers compose naturally (just like
   `BufferedReader(GzipReader(stream))`). The user wraps what they need
   at the point of use.

4. **Correct cache semantics for free.** A cache hit returns `bytes`
   directly — no stream to wrap, no spurious progress events, no
   redundant checksum verification.

5. **`ext.transfer` integration.** The existing `_ProgressReader` in
   transfer becomes the public `ProgressReader` in `ext.streams`.
   Transfer gets checksum verification by composing
   `ChecksumReader(ProgressReader(stream))`.

6. **No breaking changes.** ObservedStore and CachedStore stay as-is.
   New modules are additive.

### What to Build

| Module | Contents | Spec needed? |
|--------|----------|:------------:|
| `ext.streams` | `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter`, `read_with_progress()` | Yes (new spec) |
| `ext.integrity` | `verify()`, `checksum()` | Yes (new spec) |
| Backend changes | Populate `FileInfo.checksum` in S3, Azure, Local backends | Amend spec 001 |

### What NOT to Build

- No `ProgressStore` proxy.
- No `ChecksumStore` proxy.
- No middleware pipeline.
- No changes to `Store.read()` or `Store.write()` signatures.

---

## 5. Open Questions

1. **`child()` propagation for ObservedStore / CachedStore.**
   This is an existing issue (not introduced by this design) but worth
   fixing. Options: override `child()` to return a wrapped child, or
   accept the current behavior and document it.

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

4. **Private-attribute coupling (`_proxy()` classmethod).**
   Is `Store._proxy()` worth adding now, or should we wait until a
   third proxy subclass appears?  Two consumers (observe, cache) may
   not justify the abstraction yet.

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

1. Review this research with the team.
2. If agreed: create spec for `ext.streams` and `ext.integrity`.
3. Amend ID-006 and ID-008 descriptions in BACKLOG.md to reference
   this research.
4. Implement `ext.streams` first (enables ID-006 and refactors transfer).
5. Implement `ext.integrity` second (enables ID-008).
6. Backend `FileInfo.checksum` population as a follow-up per backend.
