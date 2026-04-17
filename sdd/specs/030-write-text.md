# write_text Specification

## Overview

`write_text()` is a Store-level convenience method that encodes a string and
writes it to a file. Mirrors `pathlib.Path.write_text()` semantics. No backend
ABC changes -- text encoding is an application-layer concern, not a storage
concern.

**Related:** [001-store-api.md](001-store-api.md) (STORE-008),
[019-ext-observe.md](019-ext-observe.md) (OBS-003a),
[023-ext-cache.md](023-ext-cache.md) (CACHE-006, CACHE-007).

---

## Store API

### WTXT-001: `Store.write_text()` Signature and Behavior

**Invariant:** `Store.write_text(path, text, *, encoding="utf-8", overwrite=False)`
encodes a string and writes it to a file, returning a `WriteResult`.

**Signature:**
```python
def write_text(self, path: str, text: str, *, encoding: str = "utf-8", overwrite: bool = False) -> WriteResult:
    ...
```

**Implementation:** Encodes `text` via `.encode(encoding)` and delegates to
`self.write(path, encoded, overwrite=overwrite)`, forwarding the returned
`WriteResult` unchanged.

**Postconditions:**
- Writes `text.encode(encoding)` to the file at `path`.
- `encoding` parameter matches `pathlib.Path.write_text()` semantics.
- `overwrite` parameter controls whether existing files may be replaced.
- Raises `InvalidPath` if `path` is empty or `"."`.
- Raises `AlreadyExists` if the file exists and `overwrite=False`.
- Capability-gated on `Capability.WRITE` (inherited from `write`).

**See also:** [045-write-result.md](045-write-result.md) (WR-001) for the
return-type widening from `None` to `WriteResult`.

### WTXT-002: No Backend ABC Change

**Invariant:** `write_text()` is a Store-level convenience only. No abstract
method is added to `Backend`.

**Rationale:** Backends deal in bytes; text encoding is an application-layer
concern. Adding `write_text()` to every backend would duplicate trivial
encode logic across 6 implementations.

### WTXT-003: STORE-008 Update

**Invariant:** `write_text` is added to the Store API surface in STORE-008.

---

## Extension Integration

### WTXT-004: ext.observe

**Invariant:** `ObservedStore.write_text()` emits a `"write_text"` operation
event via `_observe_op`. The event metadata includes `encoding` and `overwrite`.

### WTXT-005: ext.cache

**Invariant:** `CachedStore.write_text()` delegates to the inner store's
`write_text()` and invalidates the cache for the written path. No separate
cache method needed -- cache invalidation is inherited from `write()`.

### WTXT-006: Symmetric with read_text

**Invariant:** `write_text()` and `read_text()` form a symmetric pair.
Writing with encoding E and reading with the same encoding E returns the
original string (round-trip property).
