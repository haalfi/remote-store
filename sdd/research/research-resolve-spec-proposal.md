# Research: `resolve()` Specification Proposal

**Item ID:** ID-120 (resolve -> ResolutionPlan), ID-121 (CompositeStore)
**Date:** 2026-03-29
**Status:** Research complete — ready for spec drafting
**Depends on:** ID-119 (SQLAlchemy backends, done)
**Sources:** Internal research files, source code analysis, external prior art

---

## 1. Problem Statement

remote-store backends each resolve keys to bytes through different strategies
(filesystem paths, S3 objects, URLs, SQL queries, tiered fallthrough). Today
this resolution is implicit — callers get bytes but cannot inspect *how* or
*where* those bytes came from. `native_path()` exposes the resolved location
as a string, but carries no metadata about the resolution strategy, backend
identity, or backend-specific context.

This gap creates three practical problems:

1. **Debugging opacity** — when a read fails or returns unexpected data in a
   multi-backend setup, there is no way to ask "which backend handled this key
   and how?"
2. **Cache key fragility** — `ext.cache` must construct cache keys from
   `(backend_name, full_path)` tuples assembled ad-hoc, rather than from a
   canonical, hashable resolution result.
3. **Composition blindness** — a `CompositeStore` (ID-121) that delegates
   across tiers has no standard way to report which tier resolved a key, which
   tiers were tried, or why resolution succeeded/failed.

---

## 2. Prior Art

### Internal (remote-store)

- **`native_path(key) -> str`** — exists on Backend, Store, ProxyStore. Returns
  the backend-native location string. This is the "resolve to location"
  primitive. ResolutionPlan generalizes it by adding metadata.
- **`to_key(native_path) -> str`** — inverse of `native_path()`. Strips
  backend-specific prefix to recover the key.
- **Research: SQLAlchemy backends** — introduced the "key -> byte resolver"
  framing and the original `ResolutionPlan` dataclass design.

### External

| System | Resolution Model | Key Insight |
|--------|-----------------|-------------|
| **Apache Iceberg** | Catalog -> metadata file -> manifest list -> manifests -> data files | Multi-layer metadata tree; each layer adds detail |
| **Delta Lake / Unity Catalog** | Name -> catalog lookup -> storage location + access rules | Name-based, not path-based; catalog as coordinator |
| **Apache Hudi** | Timeline + metadata table -> committed data files per version | Query-type-dependent resolution (snapshot, time-travel, incremental) |
| **fsspec** | Protocol string -> registry lookup -> filesystem class -> instance | Protocol-based dispatch; registry makes resolution inspectable |

**Industry convergence (2025-2026):** All major data lakehouse formats are
moving toward catalog-managed resolution where the catalog is the source of
truth, not the filesystem. The pattern is universal: name/key -> indirection
layer -> location + metadata + access rules.

---

## 3. Design Principles

Derived from internal research + external prior art:

1. **Indirection over direct paths** — `resolve()` returns a metadata object,
   not just a location string. The plan *is* the resolved identity.
2. **Extensible details** — each backend adds its own context via `details`.
   No schema imposed on backend-specific information.
3. **Immutable and cacheable** — `ResolutionPlan` is a frozen dataclass.
   Cache keys derived from `(kind, backend, key, native_path)` tuple, not
   `hash(plan)` directly (the `details` dict prevents `__hash__`).
4. **Composable** — composite resolution (try tier A, then B) is expressible
   as a `ResolutionPlan` whose details include the sub-plans.
5. **Inspectable** — callers branch on `kind` (a string discriminator) rather
   than `isinstance` checks on backend types.
6. **Backward-compatible** — the default implementation returns a sensible
   plan for any backend. No ABC signature change required.
7. **Immutable** — frozen dataclass, safe for concurrent use.

---

## 4. Specification

### 4.1 `ResolutionPlan` Dataclass

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ResolutionPlan:
    """Result of resolving a key through a backend.

    Describes how a key maps to its storage location and provides
    backend-specific context for debugging, caching, and composition.
    """

    kind: str
    """Resolution strategy identifier.

    Standard values:
    - ``"local"`` — local filesystem path
    - ``"s3"`` — S3 object
    - ``"s3_pyarrow"`` — S3 via PyArrow filesystem
    - ``"azure"`` — Azure Blob Storage object
    - ``"sftp"`` — SFTP remote path
    - ``"http"`` — HTTP/HTTPS URL (read-only)
    - ``"memory"`` — in-memory store (``native_path`` equals ``key``; no
      additional location information for in-memory backends)
    - ``"sql_blob"`` — SQL row-based blob storage
    - ``"sql_query"`` — SQL query -> serialized result
    - ``"composite"`` — resolved through tier composition

    Custom backends use their own ``kind`` strings.
    """

    backend: str
    """Human-readable backend identifier (e.g. ``"s3"``, ``"postgresql"``,
    ``"composite"``). Typically ``Backend.name`` or a user-assigned name."""

    key: str
    """The resolved key (after Store root-path rebasing)."""

    native_path: str
    """The backend-native location (same as ``Backend.native_path()`` output).
    Included for convenience — avoids a second call after resolution."""

    details: dict[str, Any]
    """Backend-specific resolution context. Examples:

    - Local: ``{"root": "/data", "absolute_path": "/data/sales/q1.parquet"}``
    - S3: ``{"bucket": "prod", "object_key": "sales/q1.parquet", "region": "us-east-1"}``
    - HTTP: ``{"url": "https://api.example.com/sales/q1.parquet", "method": "GET"}``
    - SQL query: ``{"query": "SELECT ...", "format": "parquet", "source": "explicit"}``
    - SQL blob: ``{"table": "remote_store_objects", "key_column": "path"}``
    - Composite: ``{"resolved_tier": "warm", "tried": ["hot", "warm"],
                    "tier_plan": <ResolutionPlan from warm tier>}``

    **Serialization note:** ``details`` values should be JSON-serializable
    primitives for logging/OTel compatibility. Nested ``ResolutionPlan`` in
    ``details`` (e.g. ``tier_plan`` in composite resolution) is allowed but
    requires a custom serializer. Consider a ``CompositeResolutionPlan``
    subclass with a typed ``tier_plan`` field in a future version.
    """
```

### 4.2 `Backend.resolve()` Method

```python
class Backend(abc.ABC):
    # ... existing methods ...

    def resolve(self, path: str) -> ResolutionPlan:
        """Resolve a backend-relative path to a ResolutionPlan.

        The default implementation returns a plan with ``kind=self.name``
        and minimal details. Backends override to add meaningful context.

        Args:
            path: Backend-relative path (not store-relative key).

        Returns:
            Frozen ResolutionPlan describing how this path resolves.
        """
        return ResolutionPlan(
            kind=self.name,
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={},
        )
```

**Override examples:**

```python
# S3Backend
def resolve(self, path: str) -> ResolutionPlan:
    return ResolutionPlan(
        kind="s3",
        backend=self.name,
        key=path,
        native_path=self.native_path(path),
        details={
            "bucket": self._bucket,
            "object_key": path,
            "endpoint_url": self._endpoint_url,
        },
    )

# SQLQueryBackend
def resolve(self, path: str) -> ResolutionPlan:
    query_config = self._resolve_query(path)
    return ResolutionPlan(
        kind="sql_query",
        backend=self.name,
        key=path,
        native_path=f"{self.name}://{path}",
        details={
            "source": query_config.source,
            "query": query_config.query,
            "format": query_config.format,
        },
    )
```

### 4.3 `Store.resolve()` Method

```python
class Store:
    def resolve(self, key: str) -> ResolutionPlan:
        """Resolve a store-relative key to a ResolutionPlan.

        Rebases the key to the backend's path space, then delegates
        to the backend's resolve() method.

        Args:
            key: Store-relative key.

        Returns:
            Frozen ResolutionPlan with the resolved key (store-relative).
        """
        full_path = self._full_path(key)
        plan = self._backend.resolve(full_path)
        # Return plan with store-relative key (not backend-relative path)
        return ResolutionPlan(
            kind=plan.kind,
            backend=plan.backend,
            key=key,
            native_path=plan.native_path,
            details=plan.details,
        )
```

**Invariant:** `store.native_path(plan.key) == plan.native_path` — this is the
implicit contract that makes the design coherent. The plan's `native_path` always
agrees with what the store would return for that key.

### 4.4 `ProxyStore.resolve()` Delegation

```python
class ProxyStore(Store):
    def resolve(self, key: str) -> ResolutionPlan:
        return self._inner.resolve(key)
```

`ext.observe` wraps with observation callback. `ext.cache` can derive a
cache key from the plan's fields (see §4.6).

**Note:** `resolve()` is expected to be cheap (no I/O for most backends). For
CompositeStore (where tier matching may involve I/O), the cache should store
the plan itself rather than calling `resolve()` on every lookup.

### 4.5 CompositeStore Resolution (ID-121, Future)

CompositeStore overrides `resolve()` to report tier-based resolution.
`tier.matches(key)` is pattern-based (no I/O) — it checks whether the key
matches a tier's configured pattern, not whether the key exists in that tier's
storage. `NotFoundError` from `resolve()` means "no pattern matched any tier",
not "key doesn't exist in storage".

```python
class CompositeStore(Store):
    def resolve(self, key: str) -> ResolutionPlan:
        tried: list[str] = []
        for tier in self._tiers:
            tried.append(tier.name)
            if tier.matches(key):
                tier_plan = tier.store.resolve(key)
                return ResolutionPlan(
                    kind="composite",
                    backend="composite",
                    key=key,
                    native_path=tier_plan.native_path,
                    details={
                        "resolved_tier": tier.name,
                        "tried": tried,
                        "tier_plan": tier_plan,
                    },
                )
        raise NotFoundError(key)
```

**Note:** The nested `tier_plan` in `details` is a `ResolutionPlan` object, not a
JSON-serializable primitive. See the serialization note in §4.1 `details` docstring
for implications and future direction.

### 4.6 Cache Key Usage

```python
# ext/cache.py — principled cache keys
def _cache_key(self, key: str) -> str:
    plan = self._inner.resolve(key)
    return f"{plan.kind}:{plan.backend}:{plan.native_path}"
```

This replaces ad-hoc `(backend_name, full_path)` tuple construction and is
correct across all backend types including SQL and composite. Note: we derive
the cache key from specific fields rather than `hash(plan)` because the
`details` dict makes `ResolutionPlan` unhashable.

---

## 5. Capability Impact

`resolve()` is **not** a capability — it is a universal introspection method
available on every Backend and Store. No capability check required. This
follows the pattern of `native_path()` and `to_key()`, which are also
universal and not gated by capabilities.

---

## 6. Migration Path

### Phase 1: Core `resolve()` (ID-120)
1. Add `ResolutionPlan` to `remote_store._resolution` (new module)
2. Add default `Backend.resolve()` returning minimal plan
3. Add `Store.resolve()` with key rebasing
4. Add `ProxyStore.resolve()` delegation
5. Override in existing backends: Local, S3, S3PyArrow, Azure, SFTP, HTTP, Memory
6. Override in SQLAlchemy backends (already designed)
7. Export from `remote_store.__init__`

### Phase 2: Cache integration
1. `ext.cache` derives cache keys from plan fields (see §4.6)
2. Backward-compatible: existing cache keys still work during transition

### Phase 3: CompositeStore (ID-121)
1. `CompositeStore` with tier-based `resolve()` override
2. Fallthrough and pattern-match modes
3. `ext.observe` integration for resolution event callbacks

### Phase 4: Resolution algebra (future, uncommitted)
- Parallel, shadow, quorum read strategies
- All expressible as `ResolutionPlan` compositions
- No new abstraction needed — just new strategy options on CompositeStore

---

## 7. Spec IDs (Proposed)

| ID | Description |
|----|-------------|
| RES-010 | `ResolutionPlan` dataclass definition, fields, frozen invariant |
| RES-020 | `Backend.resolve()` default implementation |
| RES-030 | `Store.resolve()` key rebasing |
| RES-040 | `ProxyStore.resolve()` delegation |
| RES-050..RES-090 | Per-backend `resolve()` overrides (one per backend) |
| RES-100 | Cache key derivation from `ResolutionPlan` fields (not `__hash__`) |
| RES-110 | `CompositeStore.resolve()` tier reporting |

---

## 8. Open Questions

1. **Should `details` be typed per-kind?** Current design: `dict[str, Any]`.
   Alternative: `TypedDict` subclasses per kind. Recommendation: keep `dict`
   for v1 (simpler, extensible), consider typed details in v2 if patterns
   stabilize. **Hashability note:** the `dict` field makes `ResolutionPlan`
   unhashable despite `frozen=True`. Cache keys must be derived from specific
   fields (see §4.6), not from `hash(plan)`.

2. **Should `resolve()` check existence?** Current design: no — `resolve()`
   is a pure name-to-plan mapping. Existence checking is `exists()`. This
   matches Iceberg (catalog lookup doesn't check file existence) and Delta
   (name resolution doesn't verify storage). Recommendation: keep `resolve()`
   as pure resolution, no I/O. **CompositeStore nuance:**
   `CompositeStore.resolve()` uses `tier.matches(key)` which is pattern-based
   (no I/O). `NotFoundError` means "no tier pattern matched", not "key doesn't
   exist in storage". This is consistent with the no-I/O principle.

3. **Should `native_path` be in the plan?** It duplicates `Backend.native_path()`
   output. But including it avoids a second call and makes the plan
   self-contained. Recommendation: include it (convenience > minimal surface).

4. **CompositeStore: resolve vs read resolution** — `resolve()` reports which
   tier *would* handle a key. `read()` actually tries tiers. These may
   diverge if a tier's `exists()` is stale. Recommendation: document that
   `resolve()` is a best-effort prediction, not a guarantee of `read()`
   success.

---

## 9. Recommendation

**Proceed to spec drafting for Phase 1 (ID-120: core `resolve()`).**

The design is validated by:
- Internal research (SQLAlchemy backend research, middleware architecture)
- External prior art (Iceberg, Delta/Unity, Hudi, fsspec)
- Existing codebase (`native_path()` as foundation, ProxyStore delegation)
- Industry convergence toward catalog-managed, metadata-rich resolution

The specification is minimal (one frozen dataclass + one method with a default),
backward-compatible (no ABC change, default for all existing backends), and
extensible (open `details` dict, composable plans for CompositeStore).

Phase 1 can ship independently. CompositeStore (ID-121) builds on it but is a
separate spec with separate timeline.

---

## 10. References

### Internal
- [SQLAlchemy backend research § 5](research-sqlalchemy-backend.md#5-resolution-model--composite-store) — original ResolutionPlan design
- [Store config research](research-store-config.md) — Registry multi-backend composition
- `sdd/BACKLOG.md` — ID-120, ID-121 descriptions

### External
- [Apache Iceberg Spec](https://iceberg.apache.org/spec/) — catalog-based table resolution
- [Delta Lake Documentation](https://docs.delta.io/) — name-based resolution, catalog as coordinator
- [Apache Hudi Tech Spec](https://hudi.apache.org/tech-specs/) — timeline + metadata table resolution
- [fsspec](https://filesystem-spec.readthedocs.io/) — protocol-based filesystem dispatch
- [Unity Catalog](https://www.unitycatalog.io/) — three-level namespace, OpenAPI spec
- [Iceberg REST Catalog](https://iceberg.apache.org/spec/) — language-agnostic catalog API
