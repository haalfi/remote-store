# Spec 042: Parquet Dataset Storage Extension (`ext.parquet`)

## Overview

`ParquetDatasetStore` provides high-level Parquet dataset read/write with
manifest metadata, `_SUCCESS` completion markers, and atomic-commit semantics.
Composes `Store`, not a backend — works with any backend that supports the
required capabilities.

RFC: [RFC-0008](../rfcs/rfc-0008-parquet-dataset-storage.md)

## PDS-001: Constructor & Defaults

**Invariant:** `ParquetDatasetStore` accepts a `Store` instance and optional
configuration.

**Parameters:**
- `store: Store` — the underlying store (required).
- `compression: str = "zstd"` — Parquet compression codec.
- `row_group_size: int | None = None` — passed to `pq.write_table`.
- `max_rows_per_file: int | None = None` — splits table into multiple parts.

**Postconditions:** Instance stores configuration; no I/O on construction.

## PDS-002: `write_dataset`

**Signature:**
```python
def write_dataset(
    self,
    table: pa.Table,
    key: str,
    *,
    overwrite: bool = False,
    run_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> DatasetManifest:
```

**Preconditions:**
- Backend supports `ATOMIC_WRITE` capability (hard gate).
- If `overwrite=True`, backend must also support `DELETE` capability.

**Invariants:**
- Raises `AlreadyExists` when `overwrite=False` and dataset exists.
- When `overwrite=True` and dataset exists, deletes existing dataset first.
- Each Parquet part is serialized to `io.BytesIO` then written via
  `store.write_atomic()`.
- `manifest.json` is written via `store.write_atomic()` after all parts.
- `_SUCCESS` is written via `store.write_atomic()` as the final commit signal.
  Using `write_atomic` avoids requiring a separate `WRITE` capability.
- Returns the `DatasetManifest` describing what was written.

**File layout:**
```
{dataset_key}/
├── data.parquet           # single-file (no max_rows_per_file)
├── manifest.json
└── _SUCCESS
```
or:
```
{dataset_key}/
├── part-00000.parquet     # multi-part (max_rows_per_file set)
├── part-00001.parquet
├── ...
├── manifest.json
└── _SUCCESS
```

## PDS-003: `read_dataset`

**Signature:**
```python
def read_dataset(
    self,
    key: str,
    *,
    columns: list[str] | None = None,
) -> pa.Table:
```

**Invariants:**
- Raises `DatasetIncomplete` if `{dataset_key}/_SUCCESS` does not exist.
- Reads and parses `{dataset_key}/manifest.json`.
- Verifies all parts listed in manifest exist before reading any (fail-fast).
- Raises `DatasetIncomplete` if any part is missing.
- Reads each part via `pq.read_table(io.BytesIO(...), columns=columns)`.
- Returns concatenated `pa.Table`.

## PDS-004: `DatasetManifest`

**Invariant:** Frozen dataclass with canonical JSON serialization.

**Fields:**
- `dataset_key: str`
- `parts: list[str]` — relative filenames only
- `row_count: int`
- `schema_hash: str` — first 16 hex chars of SHA-256 of `schema.to_string()`
- `compression: str`
- `created_at_utc: str` — ISO 8601
- `run_id: str | None = None`
- `metadata: dict[str, str] | None = None`

**Methods:**
- `to_json() -> str` — sorted keys, 2-space indent.
- `from_json(text: str) -> DatasetManifest` — raises `ManifestCorrupted`
  on parse failure or missing required fields.

**Postconditions:** `from_json(manifest.to_json())` round-trips without loss.
`schema_hash` is deterministic for the same Arrow schema.

## PDS-005: Single-File vs Multi-Part Layout

**Invariant:**
- `max_rows_per_file=None` → single `data.parquet`.
- `max_rows_per_file=N` → `part-00000.parquet`, `part-00001.parquet`, ...
  Each part contains at most N rows (last part may contain fewer).

## PDS-006: Column Projection

**Invariant:** `columns` kwarg on `read_dataset` is passed through to
`pq.read_table()`. Only specified columns are deserialized.

## PDS-007: `dataset_exists`

**Signature:** `def dataset_exists(self, key: str) -> bool`

**Invariant:** Returns `True` iff `{dataset_key}/_SUCCESS` exists in the store.

## PDS-008: Error Conditions

**New error types** (both inherit directly from `RemoteStoreError` per ERR-008):

- `DatasetIncomplete` — dataset is structurally incomplete (missing `_SUCCESS`
  or parts listed in manifest). Not `NotFound` — some files may exist.
- `ManifestCorrupted` — manifest file exists but cannot be parsed or is
  structurally invalid. Carries optional `reason: str` attribute for the
  specific parse/structural failure.

See also: ERR-011, ERR-012 in `005-error-model.md`.

## PDS-009: Dagster Integration

**Deferred to ID-083 (Dagster v2).** The v1 `Serializer` protocol is
bytes-oriented; dataset writes require directory-level access. ID-083's
`RemoteStoreIOManager` resolves this by owning Store dispatch. Consumers
construct `ParquetDatasetStore` directly in the meantime.

## PDS-010: `delete_dataset`

**Signature:** `def delete_dataset(self, key: str) -> None`

**Invariant:** Delegates to `store.delete_folder(dataset_key, recursive=True)`.
Raises `NotFound` if the dataset folder does not exist.

## PDS-011: Overwrite Semantics

**Invariant:** `overwrite=True` on `write_dataset`:
1. Checks `dataset_exists(dataset_key)`.
2. If exists, calls `delete_dataset(dataset_key)` to remove old files.
3. Writes new dataset (parts, manifest, `_SUCCESS`).

Requires both `ATOMIC_WRITE` and `DELETE` capabilities.

## PDS-012: `read_manifest`

**Signature:** `def read_manifest(self, key: str) -> DatasetManifest`

**Invariant:** Reads and parses `{dataset_key}/manifest.json`. Raises
`NotFound` if manifest does not exist, `ManifestCorrupted` if unparseable.
