# Research: Dagster Extension (`ext.dagster`, ID-073)

**Date:** 2026-03-13
**Backlog item:** ID-073 — Dagster integration (`ext.dagster`)
**Status:** Research complete — ready for design decisions

---

## 1. Problem Statement

Dagster users who want portable storage (S3 + SFTP + Local without rewriting pipelines)
today must choose a backend-specific IO manager (`dagster-aws`, `dagster-gcp`, …).
Switching backends requires changing pipeline code. remote-store already provides a
backend-uniform `Store` API. A thin Dagster adapter would let Dagster pipelines declare
*which backend to use* purely via config, with zero pipeline code changes.

---

## 2. Dagster IO Manager API (1.7–1.12+)

### 2.1 Core interface

| Class | Use when |
|---|---|
| `IOManager` | Raw base class; implement `handle_output(context, obj)` and `load_input(context)` |
| `ConfigurableIOManager` | Preferred when config fields and I/O live in the same class |
| `ConfigurableIOManagerFactory` | Preferred when factory class is separate from the actual `IOManager` impl (e.g., wraps a stateful connection) |
| `UPathIOManager` | Subclass of `ConfigurableIOManager`; filesystem-agnostic via `universal_pathlib`/`fsspec`; define `dump_to_path(ctx, obj, path)` and `load_from_path(ctx, path)` |

### 2.2 `OutputContext` — key attributes

| Attribute | Type | Notes |
|---|---|---|
| `asset_key` | `AssetKey` | `.path` is `Sequence[str]` |
| `has_partition_key` | `bool` | True for partitioned assets |
| `asset_partition_key` | `str` | Current partition key (single) |
| `asset_partition_keys` | `Sequence[str]` | All partition keys for this run |
| `definition_metadata` | `dict` | Metadata from `AssetOut` / `Out` (was `metadata`, deprecated) |
| `add_output_metadata(dict)` | method | Adds materialization metadata visible in the UI |

### 2.3 `InputContext` — key attributes

| Attribute | Type | Notes |
|---|---|---|
| `asset_key` | `AssetKey` | |
| `has_partition_key` | `bool` | |
| `asset_partition_key` | `str` | |
| `asset_partition_keys` | `Sequence[str]` | |
| `upstream_output` | `OutputContext` | Access upstream output definition metadata |

`get_asset_identifier()` returns `[*asset_key.path, partition_key]` when partitioned —
useful for deriving storage paths.

### 2.4 Testing helpers

```python
from dagster import build_output_context, build_input_context, build_asset_context

ctx = build_output_context(asset_key=AssetKey(["my", "asset"]))
io_manager.handle_output(ctx, obj)

ctx = build_input_context(asset_key=AssetKey(["my", "asset"]))
result = io_manager.load_input(ctx)
```

No running orchestrator needed; these cover unit tests completely.

### 2.5 Version landscape

| Dagster | Python | Notes |
|---|---|---|
| 1.7.x | 3.8–3.12 | Introduced `ConfigurableResource` / `ConfigurableIOManager` |
| 1.9.x | 3.9–3.12 | Dropped Python 3.8 |
| 1.12.x+ | 3.10–3.14 | Dropped Python 3.9; aligns with remote-store's `requires-python = ">=3.10"` |

**Recommendation:** Floor at `dagster>=1.9`. remote-store requires Python 3.10+ so our
users will effectively be on Dagster 1.12+, but 1.9 is the lowest stable version that
aligns with our Python floor without imposing an artificially tight pin.

---

## 3. Why NOT `UPathIOManager`

`UPathIOManager` is the right base for *fsspec/universal_pathlib backends* (S3, GCS,
Azure via fsspec). However:

1. **Dependency leak.** `UPathIOManager` requires `universal_pathlib` (which requires
   `fsspec`). remote-store explicitly avoids fsspec as a user-visible dependency
   (ADR-0003). Pulling it in through Dagster would leak a dep we committed to hiding.

2. **Conceptual mismatch.** `UPathIOManager` operates on `UPath` objects (fsspec paths).
   remote-store's `Store` API is its own abstraction, not an fsspec filesystem. Bridging
   through `ext.arrow`'s `pyarrow_fs` adapter would add `pyarrow` as a required dep just
   to make path objects work.

3. **Path-kwargs stripping bug.** `UPathIOManager._with_extension()` instantiates a new
   `UPath` without preserving auth kwargs — a known issue that would affect cloud backends.

4. **Extension is the right fit.** The remote-store public API (`read_bytes`, `write`,
   `exists`) is exactly the interface needed. There is no value in the fsspec abstraction
   layer.

**Decision:** Implement against the public `Store` API directly, using
`ConfigurableIOManagerFactory` (two-class pattern) as the Dagster entry point.

---

## 4. Proposed Design

### 4.1 Architecture overview

```
DagsterStoreResource          → ConfigurableResource that builds a Store
    backend_type: str
    backend_options: dict
    root_path: str = ""

RemoteStoreIOManager          → ConfigurableIOManagerFactory
    store_resource: ResourceDependency[DagsterStoreResource]
    serializer: str = "pickle"    # "pickle" | "json" | "parquet"
    extension: str = ""           # override file extension (default: serializer default)

_RemoteStoreIOManagerImpl     → IOManager (internal, not exported)
    __init__(store: Store, serializer: Serializer)
    handle_output(context, obj) → None
    load_input(context)         → Any
```

`DagsterStoreResource` and `RemoteStoreIOManager` are both exported in `__all__`.
`_RemoteStoreIOManagerImpl` is internal.

### 4.2 Minimal usage

```python
from dagster import Definitions, asset
from remote_store.ext.dagster import DagsterStoreResource, RemoteStoreIOManager

@asset
def raw_data() -> dict:
    return {"rows": [1, 2, 3]}

defs = Definitions(
    assets=[raw_data],
    resources={
        "io_manager": RemoteStoreIOManager(
            store_resource=DagsterStoreResource(
                backend_type="s3",
                backend_options={"bucket": "my-bucket"},
                root_path="dagster",
            ),
            serializer="pickle",
        )
    },
)
```

Local-dev override — purely via resource config, zero pipeline changes:

```python
resources={
    "io_manager": RemoteStoreIOManager(
        store_resource=DagsterStoreResource(backend_type="local",
                                            backend_options={"root": "/tmp/dagster"}),
    )
}
```

### 4.3 Direct-Store path (escape hatch)

For users who already have a `Store` object (e.g., from `Registry`), a factory function
provides a non-`ConfigurableIOManager` path:

```python
from remote_store.ext.dagster import remote_store_io_manager

@io_manager
def my_io_manager() -> IOManager:
    registry = Registry(config)
    store = registry.get_store("production")
    return remote_store_io_manager(store, serializer="pickle")
```

This covers the "pass an existing Store" case without fighting Dagster's resource system.

### 4.4 Path generation strategy

Storage path derived from `context.get_asset_identifier()` (includes partition key when
partitioned):

| Asset / Partition | Derived path |
|---|---|
| `AssetKey(["foo", "bar"])`, no partition | `foo/bar.<ext>` |
| `AssetKey(["foo", "bar"])`, partition `"2026-01"` | `foo/bar/2026-01.<ext>` |
| `AssetKey(["ns", "report"])`, no partition | `ns/report.<ext>` |

Implementation:

```python
def _asset_path(context: OutputContext | InputContext, ext: str) -> str:
    identifier = context.get_asset_identifier()   # ["foo", "bar"] or ["foo", "bar", "2026-01"]
    *parts, last = identifier
    path = "/".join(parts + [last]) if parts else last
    return f"{path}{ext}"
```

The `root_path` of the `Store` (set on `DagsterStoreResource`) acts as the namespace
prefix — no need to embed it in the path generation logic.

### 4.5 Serializer protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Serializer(Protocol):
    extension: str                        # e.g., ".pkl", ".json", ".parquet"
    def serialize(self, obj: Any) -> bytes: ...
    def deserialize(self, data: bytes) -> Any: ...
```

Built-in serializers:

| Name | `serializer=` string | `extension` | Dependency | Notes |
|---|---|---|---|---|
| `PickleSerializer` | `"pickle"` (default) | `.pkl` | stdlib | Universal; opaque |
| `JsonSerializer` | `"json"` | `.json` | stdlib | JSON-serializable objects only |
| `ParquetSerializer` | `"parquet"` | `.parquet` | `pyarrow>=14.0` | DataFrames (pandas, polars) |

`ParquetSerializer` is guarded behind the same `try/except` pattern as `ext.arrow`.
Users who pass `serializer="parquet"` without PyArrow installed get a clear error:
`"PyArrow is required for the parquet serializer. Install it with: pip install 'remote-store[dagster,arrow]'"`.

Custom serializers can be passed as objects:

```python
RemoteStoreIOManager(
    store_resource=...,
    serializer=MyCustomSerializer(),   # any object matching Serializer protocol
)
```

The `serializer` field type would be `str | Serializer`. In practice Dagster config
fields must be Pydantic-compatible types — so the `serializer` field of
`RemoteStoreIOManager` stores a string (`"pickle"` | `"json"` | `"parquet"`), and a
`custom_serializer` field can accept an arbitrary `Serializer` object at construction
time (but this field won't be config-drivable). This is a known trade-off of Pydantic-
based config.

---

## 5. Design Decision: Single file vs. separate distribution

| Option | Pros | Cons |
|---|---|---|
| `ext/dagster.py` in remote-store | Consistent with existing extensions; no extra PyPI package to maintain; single install | Adds `dagster` as an optional dep to the main package |
| Separate `remote-store-dagster` PyPI package | Completely separate release cycle; dagster dependency not in remote-store | Two packages, doubled maintenance; harder discovery |

**Recommendation: `ext/dagster.py` in the main package** — consistent with
`ext/arrow.py`, `ext/otel.py`, `ext/pydantic.py`. Dagster is declared as an optional
dep under the `dagster` extra. Users install `pip install "remote-store[dagster]"`.

The backlog's third-party naming convention (`remote-store-<name>`) is for *external*
packages, not for first-party extensions — this is first-party.

---

## 6. Design Decision: `DagsterStoreResource` vs. RegistryConfig YAML

The backlog mentions "wraps `RegistryConfig`". Two approaches:

**Option A: Direct backend fields** (recommended)
`DagsterStoreResource` has `backend_type`, `backend_options`, `root_path` fields.
Simple, transparent, no RegistryConfig indirection.

**Option B: Profile-based via RegistryConfig**
`DagsterStoreResource` has `profile_name` and points to a YAML/env-var config.
More powerful but complex; requires `ext.yaml` or `ext.toml`.

**Recommendation: Option A for v1, Option B as a follow-up.** Ship simple first.
A `profile` field can be added later without breaking Option A.

---

## 7. Design Decision: `DagsterStoreResource` backend_options schema

`backend_options` is `dict[str, Any]` — same as `BackendConfig.options` in RegistryConfig.
Secret wrapping (e.g., `account_key`, `password`) should use the same logic as
`RegistryConfig.from_dict` — wrap sensitive keys in `Secret`.

Dagster's `EnvVar("MY_SECRET")` can be used for the string values, which Dagster
resolves at runtime. The `DagsterStoreResource.get_store()` method calls
`RegistryConfig.from_dict({"backends": {...}, "stores": {...}})` to build the Store.

---

## 8. Testing Strategy

### Unit tests (no Dagster orchestrator)

```python
from dagster import build_output_context, build_input_context, AssetKey
from remote_store.backends._memory import MemoryBackend
from remote_store._store import Store
from remote_store.ext.dagster import remote_store_io_manager

def test_roundtrip_pickle():
    store = Store(MemoryBackend())
    mgr = remote_store_io_manager(store, serializer="pickle")

    obj = {"key": "value"}
    out_ctx = build_output_context(asset_key=AssetKey(["my", "asset"]))
    mgr.handle_output(out_ctx, obj)

    in_ctx = build_input_context(asset_key=AssetKey(["my", "asset"]),
                                  upstream_output=out_ctx)
    assert mgr.load_input(in_ctx) == obj
```

`build_output_context` / `build_input_context` are sufficient — no `dagster-daemon` or
`dagster-webserver` needed.

### What must be tested

| Test | Spec ID to assign |
|---|---|
| Pickle roundtrip (MemoryBackend) | DAG-001 |
| JSON roundtrip | DAG-002 |
| Parquet roundtrip (pandas DataFrame) | DAG-003 |
| Partitioned asset — path includes partition key | DAG-004 |
| Multi-segment asset key maps to nested path | DAG-005 |
| `DagsterStoreResource.get_store()` builds correct Store | DAG-006 |
| Missing file raises `NotFound` on load | DAG-007 |
| `handle_output` adds metadata to context | DAG-008 |
| Custom serializer protocol respected | DAG-009 |
| Missing PyArrow for parquet gives helpful error | DAG-010 |

---

## 9. Interaction with Existing Extensions

- **`ext.arrow`**: `ParquetSerializer` can reuse `pyarrow` directly — no need to go
  through `StoreFileSystemHandler`. The serializer just writes `bytes` and `store.write()`
  handles the rest.

- **`ext.observe`**: Users who want observability on their Dagster Store operations can
  wrap the Store with `observe()` before passing to `DagsterStoreResource`. The IO manager
  only sees the public `Store` API so any wrapping is transparent.

- **`ext.cache`**: Same pattern — wrap with `cached_store()` before passing. No special
  integration needed.

- **`ext.partition`**: `ext.partition` provides `partition_path()` for date-based paths.
  This is complementary; users can override path logic via a custom `_get_path` hook if
  needed, but the default asset-key-based path is sufficient for most cases.

---

## 10. Open Questions — Resolved

| Question | Resolution |
|---|---|
| Single package vs. separate distribution? | `ext/dagster.py` in remote-store — consistent with existing extensions |
| Serialization default? | `"pickle"` (universal); Parquet behind optional PyArrow guard |
| Dagster version floor? | `dagster>=1.9`; aligns with Python 3.9+ drop and `ConfigurableResource` stability |
| Testing without orchestrator? | `build_output_context` / `build_input_context` are sufficient |
| Use `UPathIOManager`? | No — introduces fsspec/universal_pathlib dep; violates ADR-0003 |
| Path for multi-segment asset keys? | `"/".join(asset_key.path) + "/" + partition_key + ext` |
| Secret handling in `backend_options`? | Delegate to `RegistryConfig.from_dict` — same `Secret` wrapping as everywhere else |

---

## 11. Remaining Open Questions (for owner to decide)

1. **`DagsterStoreResource.backend_options` typing**: Should sensitive keys in
   `backend_options` accept Dagster's `EnvVar("...")` type directly, or require users to
   use Dagster's `EnvVar` string resolution before passing? The simplest approach is plain
   strings (users set env vars themselves). Dagster `EnvVar` integration would be a
   follow-up.

2. **Multi-partition loading**: When a downstream asset has multiple upstream partitions
   (e.g., time-window aggregation), `load_input` is called once with `asset_partition_keys`
   containing N keys. The IO manager should return a `dict[str, Any]` mapping partition
   key → deserialized object. This is the Dagster convention. Confirm this behavior is in
   scope for v1 or explicitly deferred.

3. **`extension` override**: Should users be able to override the file extension
   independently of the serializer (e.g., serializer="pickle" but extension=".dat")?
   Probably not — keep it simple; extension is determined by the serializer.

4. **`handle_output` for `None`**: When an asset returns `None` (e.g., a sink asset that
   writes to a DB), should `handle_output` skip writing (no-op) or write the pickled
   `None`? The convention in Dagster's own IO managers is to write it, so downstream can
   distinguish "never materialized" from "materialized as None". Confirm.

---

## 12. Proposed Spec IDs

`sdd/specs/030-ext-dagster.md` — DAGSTER-NNN series, DAG-001 through DAG-010+ (see §8).

---

## 13. Implementation Checklist (SDD pipeline)

- [ ] RFC: `sdd/rfcs/rfc-0005-dagster-extension.md`
- [ ] Spec: `sdd/specs/030-ext-dagster.md` (DAG-001 … DAG-010+)
- [ ] Implementation: `src/remote_store/ext/dagster.py`
- [ ] Tests: `tests/test_dagster.py` with `@pytest.mark.spec("DAG-NNN")`
- [ ] Guide: `guides/dagster.md` (setup, usage patterns, serializer guide)
- [ ] Docs wiring: `docs-src/api/ext-dagster.md`, `docs-src/_nav.yml`
- [ ] `pyproject.toml`: add `dagster` extra (`dagster>=1.9`)
- [ ] `remote_store/__init__.py`: conditional re-export
- [ ] CHANGELOG, BACKLOG updates (same commit)

---

## References

- [Dagster IO Managers API](https://docs.dagster.io/api/dagster/io-managers)
- [Defining a Custom IO Manager](https://docs.dagster.io/guides/build/io-managers/defining-a-custom-io-manager)
- [dagster-aws S3 IO Manager source](https://github.com/dagster-io/dagster/blob/master/python_modules/libraries/dagster-aws/dagster_aws/s3/io_manager.py)
- [UPathIOManager PR](https://github.com/dagster-io/dagster/pull/10193)
- [Dagster releases and compatibility](https://docs.dagster.io/about/releases)
- ADR-0003: fsspec is an implementation detail (`sdd/adrs/0003-fsspec-is-implementation-detail.md`)
- ADR-0008: Extension architecture (`sdd/adrs/0008-extension-architecture.md`)
