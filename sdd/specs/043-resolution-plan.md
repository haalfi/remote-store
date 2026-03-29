# Resolution Plan Specification

## Overview

This spec defines `resolve()` -- a universal introspection method that makes
key-to-location resolution explicit and inspectable across all backends.
`Store.resolve(key)` returns a frozen `ResolutionPlan` dataclass describing
how a key maps to its storage location, which backend handles it, and
backend-specific context for debugging, caching, and composition.

**Relationship to existing specs:**

- Extends `003-backend-adapter-contract.md` (new default method on Backend ABC)
- Extends `001-store-api.md` (new method on Store)
- Builds on `010-native-path-resolution.md` (`native_path()` as foundation)
- Relates to `023-ext-cache.md` (future cache key derivation, Phase 2+)
- See also: [Research](../research/research-resolve-spec-proposal.md)

---

## The Problem

### RES-001: Resolution Opacity

Backends resolve keys to bytes through different strategies (filesystem paths,
S3 objects, URLs, SQL queries, tiered fallthrough). Today this resolution is
implicit -- callers get bytes but cannot inspect *how* or *where* those bytes
came from. `native_path()` exposes the resolved location as a string but
carries no metadata about the resolution strategy, backend identity, or
backend-specific context.

This creates three practical problems:

1. **Debugging opacity** -- when a read fails or returns unexpected data, there
   is no way to ask "which backend handled this key and how?"
2. **Cache key fragility** -- cache key construction requires ad-hoc assembly
   of identity fields rather than deriving from a canonical resolution result.
3. **Composition blindness** -- a future `CompositeStore` (ID-121) that
   delegates across tiers has no standard way to report which tier resolved a
   key, which tiers were tried, or why resolution succeeded/failed.

---

## Specification

### RES-010: `ResolutionPlan` Dataclass

`ResolutionPlan` is a frozen dataclass in `remote_store._resolution`.

```python
@dataclass(frozen=True)
class ResolutionPlan:
    kind: str
    backend: str
    key: str
    native_path: str
    details: dict[str, Any]  # wrapped in MappingProxyType via __post_init__
```

**Fields:**

- **`kind`** -- Resolution strategy identifier. Standard values: `"local"`,
  `"s3"`, `"s3-pyarrow"`, `"azure"`, `"sftp"`, `"http"`, `"memory"`,
  `"sql-blob"`, `"sql-query"`, `"composite"`. Custom backends use their own
  strings. For simple backends, `kind` equals `Backend.name`.
- **`backend`** -- Human-readable backend identifier (typically `Backend.name`).
- **`key`** -- The resolved key (store-relative after `Store.resolve()`,
  backend-relative after `Backend.resolve()`).
- **`native_path`** -- The backend-native location string (same as
  `Backend.native_path()` output). Included for convenience.
- **`details`** -- Backend-specific resolution context. Immutable at runtime:
  wrapped in `types.MappingProxyType` via `__post_init__` to prevent accidental
  mutation. Values should be JSON-serializable primitives for
  logging/OTel compatibility.

**Invariants:**

- `ResolutionPlan` is frozen (`FrozenInstanceError` on attribute assignment).
- `ResolutionPlan` is **NOT hashable** (`TypeError` on `hash()`) because
  `MappingProxyType(dict)` is not hashable. Cache keys must be derived from
  specific fields (see RES-100, Phase 2).
- `details` is immutable at runtime (`TypeError` on item assignment).
- `resolve()` is an introspection API. It is **never called implicitly** by
  other Store or Backend methods (`read()`, `write()`, etc.).

### RES-020: `Backend.resolve()` Default Implementation

`Backend` gains a non-abstract `resolve()` method with a sensible default.
Placed alongside `native_path()`, `to_key()`, and `unwrap()` in the interop
section.

```python
def resolve(self, path: str) -> ResolutionPlan:
    return ResolutionPlan(
        kind=self.name,
        backend=self.name,
        key=path,
        native_path=self.native_path(path),
        details={},
    )
```

- Non-abstract: existing and third-party backends get a working default.
- No I/O: pure name-to-plan mapping.
- Backends override to add meaningful `details`.

### RES-025: Universal Contract

For any backend `b` and valid path `p`:

```python
plan = b.resolve(p)
assert plan.native_path == b.native_path(p)
assert isinstance(plan.details, MappingProxyType)
assert plan.kind == b.name  # true for default impl; overrides may differ
```

The `native_path` invariant ensures `resolve()` and `native_path()` agree.

### RES-030: `Store.resolve()` Key Rebasing

```python
def resolve(self, key: str) -> ResolutionPlan:
    full_path = self._full_path(key)
    plan = self._backend.resolve(full_path)
    return dataclasses.replace(plan, key=key)
```

- Rebases the key: `plan.key` is the store-relative key, not the
  backend-relative path.
- All other fields (`kind`, `backend`, `native_path`, `details`) are
  forwarded unchanged from the backend's plan.
- `resolve("")` is valid and resolves the store root.

### RES-035: `Store.resolve()` Invariant

For any store `s` and valid key `k`:

```python
plan = s.resolve(k)
assert s.native_path(k) == plan.native_path
```

This is the store-level coherence contract: the plan's `native_path` always
agrees with what the store would return for that key.

### RES-040: `ProxyStore.resolve()` Delegation

```python
def resolve(self, key: str) -> ResolutionPlan:
    return self._inner.resolve(key)
```

`ProxyStore` delegates to the inner store. The returned plan is unchanged.
Subclasses (`ObservedStore`, `CachedStore`) may override to add behavior
(e.g., observation events).

### RES-050: `LocalBackend.resolve()`

```python
kind = "local"
details = {"root": str, "absolute_path": str}
```

### RES-051: `S3Backend.resolve()`

```python
kind = "s3"
details = {"bucket": str, "object_key": str, "endpoint_url": str | None}
```

`endpoint_url` is stripped of userinfo (RFC 3986) before inclusion.

### RES-052: `S3PyArrowBackend.resolve()`

```python
kind = "s3-pyarrow"
details = {"bucket": str, "object_key": str, "endpoint_url": str | None}
```

### RES-053: `AzureBackend.resolve()`

```python
kind = "azure"
details = {"container": str, "account_url": str}
```

### RES-054: `SFTPBackend.resolve()`

```python
kind = "sftp"
details = {"host": str, "port": int, "base_path": str}
```

### RES-055: `ReadOnlyHttpBackend.resolve()`

```python
kind = "http"
details = {"url": str, "method": str}
```

`url` is the fully-resolved URL for the key. `method` is `"GET"`.

### RES-056: `MemoryBackend.resolve()`

Uses the default `Backend.resolve()` implementation. No override needed.

```python
kind = "memory"
details = {}
```

### RES-057: `SQLBlobBackend.resolve()`

```python
kind = "sql-blob"
details = {"table_name": str}
```

### RES-058: `SQLQueryBackend.resolve()`

```python
kind = "sql-query"
details = {"source": str, "format": str}
```

`source` is `"explicit"` for mapped queries. `format` is the output format
(e.g., `"parquet"`, `"csv"`). The raw SQL query is **not** included in
`details` (see Security section).

---

## Security

`ResolutionPlan` may be logged, serialized, or sent to observability systems.
Its contents must be treated as potentially public.

1. `details` **must never** include credentials, passwords, tokens, or secret
   keys.
2. `endpoint_url` values must be stripped of userinfo (`user:pass@host`) before
   inclusion in `details`.
3. SQL queries are **not** included in `details` to avoid leaking business
   logic or parameterized values.
4. Connection strings and database URLs are **not** included in `details`.

---

## Phase 1 Scope (ID-120)

Phase 1 covers RES-010 through RES-058:

1. `ResolutionPlan` dataclass in `remote_store._resolution`
2. Default `Backend.resolve()` on the ABC
3. `Store.resolve()` with key rebasing
4. `ProxyStore.resolve()` delegation
5. Per-backend overrides for all 9 backends
6. Export `ResolutionPlan` from `remote_store.__init__`

### Out of scope (future phases)

- **Phase 2 (RES-100):** Cache key derivation from `ResolutionPlan` fields
  in `ext.cache`.
- **Phase 3 (RES-110, ID-121):** `CompositeStore.resolve()` with tier
  reporting, `on_resolve` observation hook.

---

## Test Requirements

Per `sdd/TESTING.md` rules:

- Every spec ID gets `@pytest.mark.spec("RES-xxx")` tracing.
- `MemoryBackend` preferred over mocks for Store/ProxyStore tests.
- Per-backend tests assert expected detail key names exist (not values),
  except where semantically important (e.g., `details["bucket"]` matches
  configured bucket).
- Edge cases: `resolve("")`, `child().resolve()`, special characters in keys.
- Failure-path: `hash(plan)` raises `TypeError`.
