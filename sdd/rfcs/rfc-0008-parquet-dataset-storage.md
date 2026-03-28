# RFC-0008: Parquet Dataset Storage Extension

## Status

Draft

## Summary

Add an `ext.parquet` module that provides `ParquetDatasetStore` — a high-level
abstraction for writing and reading multi-file Parquet datasets with manifest
metadata, `_SUCCESS` markers, and atomic-commit semantics. Built on top of
`Store`, `ext.arrow`, and `ext.partition`, it composes existing primitives into a
reusable dataset protocol for teams running Dagster, Airflow, or custom
pipelines that produce partitioned Parquet outputs.

## Motivation

Teams using remote-store as their storage layer in analytics pipelines converge
on the same write pattern: serialize a PyArrow Table to one or more Parquet
files, write a `manifest.json` describing what was written, drop a `_SUCCESS`
marker, and optionally promote from a staging prefix to a canonical one. The
read side mirrors this: locate the manifest, resolve parts, read and concatenate.

Today this pattern is implemented ad-hoc by each team. Common problems:

1. **Duplicated write sequences.** Every pipeline author hand-rolls the
   multi-step write (Parquet files → manifest → `_SUCCESS`). Bugs in one copy
   are not fixed in others.

2. **Inconsistent manifests.** Without a shared schema, each pipeline writes
   different keys (`rows` vs `row_count`, `parts` vs `file_count`), making
   cross-pipeline tooling (validation, lineage, retention) fragile.

3. **No read-back.** Manifests are write-only today. No standard reader resolves
   a manifest back to a concatenated `pa.Table`, so consumers duplicate file
   discovery logic.

4. **Mixed single-file / multi-part layouts.** Some pipelines write a single
   `data.parquet`, others write `part-00000.parquet` through `part-NNNNN.parquet`.
   Readers must handle both, but nothing enforces a convention.

5. **No completion contract.** `_SUCCESS` files are written but nothing checks
   for them before reading, so partial writes are silently consumed.

The existing `ext.dagster` IO manager handles simple serialize/deserialize via
`ParquetSerializer`, but it operates on in-memory bytes — no streaming, no
multi-part, no manifest. The `ext.arrow` adapter provides the PyArrow filesystem
bridge but does not prescribe any dataset layout or metadata protocol.

This RFC proposes a composable extension that fills the gap between "raw I/O"
(Store) and "full table format" (Delta Lake, Iceberg), targeting teams that need
reliable Parquet dataset management without adopting a transactional table
format.

## Proposal

### Module location

`remote_store/ext/parquet.py` — optional dependency on `pyarrow`.
Install: `pip install "remote-store[arrow]"` (reuses the existing `[arrow]` extra
which already includes `pyarrow>=12.0.0`; no new install extra needed).

### Core class: `ParquetDatasetStore`

```python
class ParquetDatasetStore:
    """High-level Parquet dataset read/write on top of any Store."""

    def __init__(
        self,
        store: Store,
        *,
        compression: str = "zstd",
        row_group_size: int | None = None,
        max_rows_per_file: int | None = None,
    ) -> None: ...

    def write_dataset(
        self,
        table: pa.Table,
        dataset_key: str,
        *,
        overwrite: bool = False,
        run_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> DatasetManifest: ...

    def delete_dataset(self, dataset_key: str) -> None: ...

    def read_dataset(
        self,
        dataset_key: str,
        *,
        columns: list[str] | None = None,
    ) -> pa.Table: ...

    def read_manifest(self, dataset_key: str) -> DatasetManifest: ...

    def dataset_exists(self, dataset_key: str) -> bool: ...
```

**Key behaviors:**

- `write_dataset` writes Parquet file(s) under `{dataset_key}/`, writes
  `manifest.json`, writes `_SUCCESS`, and returns the manifest. When
  `max_rows_per_file` is set, the table is split into multiple
  `part-NNNNN.parquet` files; otherwise a single `data.parquet` is written.
  **Calling `write_dataset` for a `dataset_key` that already exists raises
  `AlreadyExists` by default.** Pass `overwrite=True` to replace the dataset
  (deletes old files before writing new ones).
- `read_dataset` checks for `_SUCCESS`, reads `manifest.json`, resolves the
  listed parts, reads and concatenates them into a single `pa.Table`.
  **On read, verifies that every part listed in the manifest exists before
  reading.** Raises `DatasetIncomplete` if any part is missing.
- **Write path:** Each Parquet file is serialized to an in-memory buffer
  (`pq.write_table` → `io.BytesIO`), then written via `store.write_atomic()`.
  This ensures per-file atomicity but requires full materialization of each
  part. For true streaming writes to backends that support it, callers can use
  the `ext.arrow` PyArrow filesystem adapter directly and then call
  `write_manifest()` separately (a future convenience method).
- The `dataset_key` is a `/`-separated path (e.g., `silver/orders`,
  `bronze/events/2026-03-28`). The `Store`'s `root_path` acts as the
  namespace — `ParquetDatasetStore` does not embed it.

### Manifest schema: `DatasetManifest`

```python
@dataclass(frozen=True)
class DatasetManifest:
    """Canonical manifest for a Parquet dataset snapshot."""
    dataset_key: str
    parts: list[str]          # relative filenames: ["data.parquet"] or ["part-00000.parquet", ...]
    row_count: int
    schema_hash: str           # SHA-256 of schema.to_string() (text, version-stable)
    compression: str
    created_at_utc: str        # ISO 8601
    run_id: str | None = None  # pipeline run identifier (Dagster run_id, Airflow run_id, etc.)
    metadata: dict[str, str] | None = None  # caller-supplied key-value pairs
```

- Serialized as JSON. One canonical schema — no per-caller variation.
- `schema_hash` computed as SHA-256 of `table.schema.to_string()` (text
  representation, stable across PyArrow versions — unlike `serialize()` whose
  IPC binary format may change).
- `metadata` is an escape hatch for pipeline-specific fields (report IDs,
  source system identifiers, etc.) without polluting the core schema.
- `_SUCCESS` is an empty file written *after* manifest, signaling completion.

### Write sequence

```
{dataset_key}/
├── data.parquet           # or part-00000.parquet, part-00001.parquet, ...
├── manifest.json
└── _SUCCESS
```

1. If `overwrite=True` and `_SUCCESS` exists, delete existing dataset files.
2. Serialize each Parquet part to bytes (`pq.write_table` → `io.BytesIO`),
   then write via `store.write_atomic()`.
3. Write `manifest.json` via `store.write_atomic()`.
4. Write `_SUCCESS` (empty) via `store.write()`.

Steps 2–4 are not transactional across files (S3 has no multi-object
transactions). The `_SUCCESS` marker is the commit signal — readers that check
for it are protected from partial writes. This is the same contract used by
Hadoop, Spark, and Hive.

**Concurrency note:** Concurrent writers to the same `dataset_key` are not
safe. The non-transactional write sequence means writer A's `_SUCCESS` could
become visible while writer B's parts are half-written. Callers must
coordinate externally (e.g., pipeline-level locking, unique `dataset_key` per
run). This is consistent with Spark/Hive behavior for non-transactional
writes.

### Read sequence

1. Check `{dataset_key}/_SUCCESS` exists → raise `DatasetIncomplete` if missing.
2. Read and parse `{dataset_key}/manifest.json` → `DatasetManifest`.
3. Verify all parts listed in `manifest.parts` exist → raise
   `DatasetIncomplete` if any part is missing (fail-fast, no partial reads).
4. Read each part via PyArrow.
5. Concatenate into a single `pa.Table`.
6. Optionally apply column projection (`columns` parameter).

### Dataset deletion

`delete_dataset(dataset_key)` removes all files under `{dataset_key}/`
(parts, manifest, `_SUCCESS`) via `store.delete_folder(dataset_key)`. This is
a thin convenience — callers can also call `store.delete_folder()` directly.

### Integration with `ext.dagster`

The existing `ParquetSerializer` can be extended (or a new
`DatasetParquetSerializer` added) to delegate to `ParquetDatasetStore`
internally, preserving the current `dagster_io_manager` API while gaining
manifest and multi-part support.

```python
# Dagster IO manager usage — no API change for the user
io_mgr = dagster_io_manager(store, serializer="parquet-dataset")

# Or direct usage outside Dagster
ds = ParquetDatasetStore(store.child("silver"), compression="zstd")
ds.write_dataset(table, "orders", run_id="dagster-abc123")
```

### New spec sections (proposed)

Spec `041-ext-parquet.md` with IDs:

- `PDS-001`: `ParquetDatasetStore` constructor and defaults
- `PDS-002`: `write_dataset` — file layout, serialize-then-write-atomic, manifest, `_SUCCESS`
- `PDS-003`: `read_dataset` — `_SUCCESS` check, manifest-parts verification, concatenation
- `PDS-004`: `DatasetManifest` — schema, serialization, `schema_hash` via `to_string()`
- `PDS-005`: Single-file vs multi-part layout rules
- `PDS-006`: Column projection on read
- `PDS-007`: `dataset_exists` — checks for `_SUCCESS`
- `PDS-008`: Error conditions (`DatasetIncomplete`, `ManifestCorrupted`)
- `PDS-009`: Integration with `ext.dagster` serializer
- `PDS-010`: `delete_dataset` — removes dataset files via `delete_folder`
- `PDS-011`: Overwrite semantics (delete-then-write)

## Alternatives Considered

### A: Full table format (Delta Lake / Iceberg)

Both provide ACID transactions, time travel, schema evolution, and compaction.
However:

1. **Heavyweight dependency.** Delta-rs or PyIceberg add significant
   transitive dependencies and require catalog configuration.
2. **Overkill for write-once datasets.** Many analytics pipelines write
   immutable snapshots (daily extracts, report outputs) that never need
   UPDATE, MERGE, or time travel.
3. **Not the library's role.** remote-store's documented boundary is "portable,
   testable, observable storage I/O" (see `docs-src/data-lake-patterns.md`).
   Full table format semantics belong above the storage layer.

A `ParquetDatasetStore` occupies the middle ground: more structure than raw
files, less complexity than a table format. Teams that outgrow it graduate to
Delta/Iceberg via the existing `ext.arrow` PyArrow filesystem adapter.

### B: Compose existing primitives without a new class

Users can already do:

```python
pq.write_table(table, "orders/data.parquet", filesystem=pyarrow_fs(store))
store.write(f"orders/manifest.json", json.dumps({...}).encode())
store.write(f"orders/_SUCCESS", b"")
```

This is exactly the status quo that produces inconsistent manifests and
duplicated logic across pipelines. A shared abstraction eliminates the
duplication without adding framework-level complexity.

### C: Manifest-only class (no Parquet awareness)

A generic `ManifestManager` that writes/reads JSON manifests but does not
understand Parquet. This was considered but rejected because:

1. The manifest schema is tightly coupled to Parquet metadata (row count,
   schema hash, compression, part filenames).
2. Separating manifest from write forces callers to coordinate two objects and
   keep them consistent — the same coordination problem we're trying to solve.
3. A manifest protocol for non-Parquet formats (JSON, CSV, Avro) could be
   added later as a separate extension if demand exists.

### D: Path convention / locator class

A `SnapshotLocator` that maps logical names to physical paths
(e.g., `(layer="silver", dataset="orders", partition="2026-03-28")` →
`silver/orders/snapshot_date=2026-03-28/`). Rejected for v1 because:

1. remote-store already provides `Store.child()` for layer scoping and
   `ext.partition.partition_path()` for Hive-style partition paths.
2. Path conventions are inherently application-specific (teams disagree on
   `as_of_date` vs `snapshot_date` vs `partition_key`).
3. `dataset_key` as a free-form string lets callers encode whatever convention
   they want. Composition beats prescription.

If a common pattern emerges across multiple adopters, a locator could be
revisited in a future RFC.

## Impact

- **Public API:** Adds `ParquetDatasetStore`, `DatasetManifest`, and
  `DatasetIncomplete` to `ext.parquet`. Not re-exported from `__init__`
  (per ADR-0013).
- **Backwards compatibility:** Non-breaking. New optional extension.
- **Performance:** The default write path serializes each part to bytes via
  `pq.write_table` and writes via `store.write_atomic()`, which requires
  per-part in-memory materialization. For large tables, `max_rows_per_file`
  limits per-part memory usage. True streaming writes (no materialization) are
  possible via the `ext.arrow` PyArrow filesystem adapter for backends that
  support it. Multi-part support enables parallel reads (future optimization).
- **Testing:** Conformance tests against `MemoryBackend` (unit) and
  `S3Backend` / `LocalBackend` (integration). Tests for single-file and
  multi-part layouts, manifest roundtrip, `_SUCCESS` contract, and error
  conditions.

## Open Questions

1. **Should `write_dataset` support incremental appends?** v1 proposes
   overwrite semantics (each write replaces the dataset). Append-mode would
   require manifest merging and complicates the `_SUCCESS` contract.
   Recommendation: defer to v2.

2. **Should `_SUCCESS` contain the manifest hash?** Writing the manifest's
   content hash into `_SUCCESS` would let readers detect corruption without
   parsing the manifest. Trade-off: adds complexity vs marginal safety gain.

3. **Compression parameter scope.** Should compression be set per-dataset
   (constructor) or per-write (method parameter)? Constructor default with
   per-write override is the most flexible but increases API surface.

4. **Relationship to `ext.dagster` v2.** The deferred `DagsterStoreResource` /
   `RemoteStoreIOManager` (noted in spec 031) could natively integrate
   `ParquetDatasetStore`. Should this RFC block on or coordinate with that
   work?

*Resolved:* `delete_dataset` is included in the proposal (see above).
Overwrite semantics are specified via the `overwrite` parameter.

## References

- Store API: `sdd/specs/001-store-api.md`
- Atomic writes: `sdd/specs/007-atomic-writes.md`
- PyArrow filesystem adapter: `sdd/specs/014-pyarrow-filesystem-adapter.md`,
  RFC-0002
- Dagster IO manager: `sdd/specs/031-ext-dagster.md`
- Partition helpers: `ext.partition` module
- Data lake patterns guide: `docs-src/data-lake-patterns.md`
- Scope boundary: "remote-store owns portable, testable, observable storage
  I/O. Everything above the storage layer belongs to purpose-built tools."
