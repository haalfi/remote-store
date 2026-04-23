# read_text Specification

## Overview

`read_text()` is a Store-level convenience method that reads a file and decodes
its bytes to a string. Mirrors `pathlib.Path.read_text()` semantics. No backend
ABC changes — text decoding is an application-layer concern, not a storage
concern.

**Related:** [001-store-api.md](001-store-api.md) (STORE-008),
[006-streaming-io.md](006-streaming-io.md) (SIO-002),
[019-ext-observe.md](019-ext-observe.md) (OBS-003a),
[023-ext-cache.md](023-ext-cache.md) (CACHE-006, CACHE-007).

---

## Store API

### RTXT-001: `Store.read_text()` Signature and Behavior

**Invariant:** `Store.read_text(path, *, encoding="utf-8", errors="strict")`
reads the full file content and decodes it to a string.

**Signature:**
```python
def read_text(self, path: str, *, encoding: str = "utf-8", errors: str = "strict") -> str:
    ...
```

**Implementation:** Delegates to `self.read_bytes(path)` and calls
`.decode(encoding, errors)` on the result.

**Postconditions:**
- Returns a `str` decoded from the file's byte content.
- `encoding` and `errors` parameters match `pathlib.Path.read_text()` semantics.
- Raises `NotFound` if the file does not exist.
- Raises `InvalidPath` if `path` is empty or `"."`.
- Raises `UnicodeDecodeError` (standard Python exception, not remapped) if
  decoding fails with `errors="strict"`.
- Capability-gated on `Capability.READ` (inherited from `read_bytes`).

### RTXT-002: No Backend ABC Change

**Invariant:** `read_text()` is a Store-level convenience only. No abstract
method is added to `Backend`.

**Rationale:** Backends deal in bytes; text decoding is an application-layer
concern. Adding `read_text()` to every backend would duplicate trivial
decode logic across 6 implementations.

### RTXT-003: STORE-008 Update

**Invariant:** `read_text` is added to the Store API surface in STORE-008.

---

## Extension Integration

### RTXT-004: ext.observe

**Invariant:** `read_text` maps to the `on_read` hook (same as `read` and
`read_bytes`). The operation name in the `StoreEvent` is `"read_text"`.

`ObservedStore.read_text()` delegates to `self._inner.read_text()` inside
`_observe_op("read_text", path, {"encoding": encoding})`.

### RTXT-005: ext.cache

**Invariant:** `CachedStore` overrides `read_text()` to call
`self.read_bytes(path).decode(encoding, errors)`, routing through the cached
`read_bytes()` path. This avoids double-caching the same data and ensures
cache hits when `read_bytes()` has already been called for the same path.

`read_text` does NOT get its own cache key or entry in `_PATH_PREFIXES`.

---

## Spec Cross-References

### RTXT-006: Spec Updates

The following specs are updated to reflect `read_text`:

- **001-store-api.md**: Add `read_text` to STORE-008 surface list. Add to
  STORE-002 file-targeted methods list.
- **006-streaming-io.md**: Add SIO-007 noting text convenience reads.
- **019-ext-observe.md**: Add `read_text` to `on_read` hook table (OBS-003a).
- **023-ext-cache.md**: Document that `read_text` delegates to cached
  `read_bytes` (CACHE-007 non-cached section).
