# ext.parquet

## parquet

Parquet dataset read/write with manifest metadata and completion markers.

Install with `pip install "remote-store[arrow]"`.

Example

```
from remote_store.ext.parquet import ParquetDatasetStore

pds = ParquetDatasetStore(store)
manifest = pds.write_dataset(table, "silver/orders")
table = pds.read_dataset("silver/orders")
```

### DatasetIncomplete

```
DatasetIncomplete(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
)
```

Bases: `RemoteStoreError`

Raised when a dataset is structurally incomplete.

Raised by `ParquetDatasetStore.read_dataset()` when the `_SUCCESS` marker is missing or when parts listed in the manifest cannot be found. Not `NotFound` — some files may exist; the dataset as a whole is not in a readable state.

### ManifestCorrupted

```
ManifestCorrupted(
    message: str = "",
    *,
    path: str | None = None,
    backend: str | None = None,
    reason: str = "",
)
```

Bases: `RemoteStoreError`

Raised when a manifest file cannot be parsed or is structurally invalid.

Raised by `ParquetDatasetStore.read_dataset()` and `read_manifest()` when `manifest.json` exists but contains invalid JSON or is missing required fields.

Parameters:

- **`reason`** (`str`, default: `''` ) – The specific parse or structural failure.

### DatasetManifest

```
DatasetManifest(
    dataset_key: str,
    parts: list[str],
    row_count: int,
    schema_hash: str,
    compression: str,
    created_at_utc: str,
    run_id: str | None = None,
    metadata: dict[str, str] | None = None,
)
```

Immutable metadata record for a written Parquet dataset.

Parameters:

- **`dataset_key`** (`str`) – The store-relative prefix under which the dataset lives.
- **`parts`** (`list[str]`) – Relative filenames of the Parquet part files.
- **`row_count`** (`int`) – Total number of rows across all parts.
- **`schema_hash`** (`str`) – First 16 hex characters of the SHA-256 of schema.to_string().
- **`compression`** (`str`) – Compression codec used (e.g. "zstd", "snappy").
- **`created_at_utc`** (`str`) – ISO 8601 timestamp of dataset creation.
- **`run_id`** (`str | None`, default: `None` ) – Optional caller-supplied run identifier for lineage tracking.
- **`metadata`** (`dict[str, str] | None`, default: `None` ) – Optional caller-supplied key-value metadata.

#### to_json

```
to_json() -> str
```

Serialize the manifest to a JSON string.

Returns:

- `str` – A JSON string with sorted keys and 2-space indentation.

#### from_json

```
from_json(text: str) -> DatasetManifest
```

Deserialize a manifest from a JSON string.

Parameters:

- **`text`** (`str`) – The JSON string to parse.

Returns:

- `DatasetManifest` – A DatasetManifest instance.

Raises:

- `ManifestCorrupted` – If the JSON is invalid, required fields are missing, or field types are wrong.

### ParquetDatasetStore

```
ParquetDatasetStore(
    store: Store,
    *,
    compression: str = "zstd",
    row_group_size: int | None = None,
    max_rows_per_file: int | None = None,
)
```

High-level Parquet dataset operations backed by a `Store`.

Writes multi-part Parquet datasets with manifest metadata and atomic completion markers, enabling reliable dataset exchange over any remote-store backend.

Parameters:

- **`store`** (`Store`) – The Store instance to use for I/O.
- **`compression`** (`str`, default: `'zstd'` ) – Parquet compression codec. Default "zstd".
- **`row_group_size`** (`int | None`, default: `None` ) – Maximum rows per row group within each Parquet file. None (default) uses PyArrow's default.
- **`max_rows_per_file`** (`int | None`, default: `None` ) – If set, split the table into multiple part files of at most this many rows each. None writes a single file.

#### store

```
store: Store
```

The underlying store.

#### compression

```
compression: str
```

The Parquet compression codec.

#### row_group_size

```
row_group_size: int | None
```

Maximum rows per row group, or `None` for PyArrow default.

#### max_rows_per_file

```
max_rows_per_file: int | None
```

Maximum rows per part file, or `None` for single file.

#### write_dataset

```
write_dataset(
    table: Table,
    key: str,
    *,
    overwrite: bool = False,
    run_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> DatasetManifest
```

Write a PyArrow table as a Parquet dataset under *key*.

Parameters:

- **`table`** (`Table`) – The PyArrow table to write.
- **`key`** (`str`) – Store-relative prefix for the dataset (e.g. "silver/orders").
- **`overwrite`** (`bool`, default: `False` ) – If True, delete any existing dataset at key first. Requires the DELETE capability.
- **`run_id`** (`str | None`, default: `None` ) – Optional run identifier for lineage tracking.
- **`metadata`** (`dict[str, str] | None`, default: `None` ) – Optional key-value metadata to embed in the manifest.

Returns:

- `DatasetManifest` – A DatasetManifest describing the written dataset.

Raises:

- `CapabilityNotSupported` – If the store lacks ATOMIC_WRITE, or DELETE when overwrite is True.
- `AlreadyExists` – If overwrite is False and the dataset exists.

#### read_dataset

```
read_dataset(
    key: str, *, columns: list[str] | None = None
) -> Table
```

Read a Parquet dataset from *key*.

Parameters:

- **`key`** (`str`) – Store-relative prefix for the dataset.
- **`columns`** (`list[str] | None`, default: `None` ) – Optional subset of columns to read. None reads all.

Returns:

- `Table` – A PyArrow table with the concatenated contents of all parts.

Raises:

- `DatasetIncomplete` – If the \_SUCCESS marker is missing or any part listed in the manifest cannot be found.
- `ManifestCorrupted` – If the manifest cannot be parsed.
- `NotFound` – If the manifest file does not exist.

#### read_manifest

```
read_manifest(key: str) -> DatasetManifest
```

Read and parse the manifest for the dataset at *key*.

Parameters:

- **`key`** (`str`) – Store-relative prefix for the dataset.

Returns:

- `DatasetManifest` – The parsed DatasetManifest.

Raises:

- `NotFound` – If manifest.json does not exist.
- `ManifestCorrupted` – If the manifest cannot be parsed.

#### dataset_exists

```
dataset_exists(key: str) -> bool
```

Check whether a completed dataset exists at *key*.

Parameters:

- **`key`** (`str`) – Store-relative prefix for the dataset.

Returns:

- `bool` – True if the \_SUCCESS marker exists, False otherwise.

#### delete_dataset

```
delete_dataset(key: str) -> None
```

Delete an entire dataset at *key*.

Parameters:

- **`key`** (`str`) – Store-relative prefix for the dataset.

Raises:

- `NotFound` – If the dataset folder does not exist.

## See also

- [Parquet Datasets](https://docs.remotestore.dev/stable/guides/parquet-datasets/index.md) — guide to reading and writing managed Parquet datasets
- [Parquet Dataset example](https://docs.remotestore.dev/stable/tutorial/examples/parquet-dataset/index.md) — ParquetDatasetStore in action
- [PyArrow Adapter](https://docs.remotestore.dev/stable/guides/pyarrow-adapter/index.md) — lower-level Store-as-PyArrow-filesystem adapter
