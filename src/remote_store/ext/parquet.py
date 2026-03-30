"""Parquet dataset read/write with manifest metadata and completion markers.

Install with ``pip install "remote-store[arrow]"``.

Usage:

```python
from remote_store.ext.parquet import ParquetDatasetStore

pds = ParquetDatasetStore(store)
manifest = pds.write_dataset(table, "silver/orders")
table = pds.read_dataset("silver/orders")
```
"""

from __future__ import annotations

__all__ = [
    "DatasetIncomplete",
    "DatasetManifest",
    "ManifestCorrupted",
    "ParquetDatasetStore",
]

import dataclasses
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, CapabilityNotSupported, RemoteStoreError

if TYPE_CHECKING:
    from remote_store._store import Store

try:
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "PyArrow is required for the parquet extension. Install it with: pip install 'remote-store[arrow]'"
    ) from _exc


# ---------------------------------------------------------------------------
# Extension-specific errors
# ---------------------------------------------------------------------------


class DatasetIncomplete(RemoteStoreError):
    """Raised when a dataset is structurally incomplete.

    Raised by ``ParquetDatasetStore.read_dataset()`` when the ``_SUCCESS``
    marker is missing or when parts listed in the manifest cannot be found.
    Not ``NotFound`` — some files may exist; the dataset as a whole is not
    in a readable state.
    """


class ManifestCorrupted(RemoteStoreError):
    """Raised when a manifest file cannot be parsed or is structurally invalid.

    Raised by ``ParquetDatasetStore.read_dataset()`` and ``read_manifest()``
    when ``manifest.json`` exists but contains invalid JSON or is missing
    required fields.

    Args:
        reason: The specific parse or structural failure.
    """

    def __init__(
        self,
        message: str = "",
        *,
        path: str | None = None,
        backend: str | None = None,
        reason: str = "",
    ) -> None:
        self.reason = reason
        super().__init__(message, path=path, backend=backend)

    def __str__(self) -> str:
        base = super().__str__()
        if self.reason:
            return f"{base} | reason={self.reason!r}" if base else f"reason={self.reason!r}"
        return base

    def __repr__(self) -> str:
        cls = type(self).__name__
        args = [repr(self.args[0] if self.args else "")]
        if self.path is not None:
            args.append(f"path={self.path!r}")
        if self.backend is not None:
            args.append(f"backend={self.backend!r}")
        if self.reason:
            args.append(f"reason={self.reason!r}")
        return f"{cls}({', '.join(args)})"


# ---------------------------------------------------------------------------
# DatasetManifest
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DatasetManifest:
    """Immutable metadata record for a written Parquet dataset.

    Args:
        dataset_key: The store-relative prefix under which the dataset lives.
        parts: Relative filenames of the Parquet part files.
        row_count: Total number of rows across all parts.
        schema_hash: First 16 hex characters of the SHA-256 of ``schema.to_string()``.
        compression: Compression codec used (e.g. ``"zstd"``, ``"snappy"``).
        created_at_utc: ISO 8601 timestamp of dataset creation.
        run_id: Optional caller-supplied run identifier for lineage tracking.
        metadata: Optional caller-supplied key-value metadata.
    """

    dataset_key: str
    parts: list[str]
    row_count: int
    schema_hash: str
    compression: str
    created_at_utc: str
    run_id: str | None = None
    metadata: dict[str, str] | None = None

    def to_json(self) -> str:
        """Serialize the manifest to a JSON string.

        Returns:
            A JSON string with sorted keys and 2-space indentation.
        """
        data = dataclasses.asdict(self)
        # Strip None optional fields for cleaner output
        return json.dumps({k: v for k, v in data.items() if v is not None}, sort_keys=True, indent=2)

    @classmethod
    def from_json(cls, text: str) -> DatasetManifest:
        """Deserialize a manifest from a JSON string.

        Args:
            text: The JSON string to parse.

        Returns:
            A ``DatasetManifest`` instance.

        Raises:
            ManifestCorrupted: If the JSON is invalid, required fields are
                missing, or field types are wrong.
        """
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ManifestCorrupted(
                "Failed to parse manifest JSON",
                reason=f"Invalid JSON: {exc}",
            ) from exc

        if not isinstance(data, dict):
            raise ManifestCorrupted(
                "Manifest must be a JSON object",
                reason=f"Expected object, got {type(data).__name__}",
            )

        required_fields = ("dataset_key", "parts", "row_count", "schema_hash", "compression", "created_at_utc")
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ManifestCorrupted(
                f"Manifest missing required fields: {', '.join(missing)}",
                reason=f"Missing fields: {', '.join(missing)}",
            )

        # Type validation
        if not isinstance(data["dataset_key"], str):
            raise ManifestCorrupted(
                "Field 'dataset_key' must be a string",
                reason=f"dataset_key has type {type(data['dataset_key']).__name__}, expected str",
            )
        if not isinstance(data["parts"], list) or not all(isinstance(p, str) for p in data["parts"]):
            raise ManifestCorrupted(
                "Field 'parts' must be a list of strings",
                reason="parts must be list[str]",
            )
        if not isinstance(data["row_count"], int) or isinstance(data["row_count"], bool):
            raise ManifestCorrupted(
                "Field 'row_count' must be an integer",
                reason=f"row_count has type {type(data['row_count']).__name__}, expected int",
            )
        if not isinstance(data["schema_hash"], str):
            raise ManifestCorrupted(
                "Field 'schema_hash' must be a string",
                reason=f"schema_hash has type {type(data['schema_hash']).__name__}, expected str",
            )
        if not isinstance(data["compression"], str):
            raise ManifestCorrupted(
                "Field 'compression' must be a string",
                reason=f"compression has type {type(data['compression']).__name__}, expected str",
            )
        if not isinstance(data["created_at_utc"], str):
            raise ManifestCorrupted(
                "Field 'created_at_utc' must be a string",
                reason=f"created_at_utc has type {type(data['created_at_utc']).__name__}, expected str",
            )

        # Optional field type validation
        run_id = data.get("run_id")
        if run_id is not None and not isinstance(run_id, str):
            raise ManifestCorrupted(
                "Field 'run_id' must be a string or null",
                reason=f"run_id has type {type(run_id).__name__}, expected str",
            )
        metadata = data.get("metadata")
        if metadata is not None and (
            not isinstance(metadata, dict)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items())
        ):
            raise ManifestCorrupted(
                "Field 'metadata' must be a dict[str, str] or null",
                reason="metadata must be dict[str, str]",
            )

        return cls(
            dataset_key=data["dataset_key"],
            parts=data["parts"],
            row_count=data["row_count"],
            schema_hash=data["schema_hash"],
            compression=data["compression"],
            created_at_utc=data["created_at_utc"],
            run_id=run_id,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# ParquetDatasetStore
# ---------------------------------------------------------------------------


def _schema_hash(schema: pa.Schema) -> str:
    """Compute the first 16 hex chars of SHA-256 of the schema string."""
    return hashlib.sha256(schema.to_string().encode("utf-8")).hexdigest()[:16]


class ParquetDatasetStore:
    """High-level Parquet dataset operations backed by a ``Store``.

    Writes multi-part Parquet datasets with manifest metadata and atomic
    completion markers, enabling reliable dataset exchange over any
    remote-store backend.

    Args:
        store: The Store instance to use for I/O.
        compression: Parquet compression codec. Default ``"zstd"``.
        row_group_size: Maximum rows per row group within each Parquet file.
            ``None`` (default) uses PyArrow's default.
        max_rows_per_file: If set, split the table into multiple part files
            of at most this many rows each. ``None`` writes a single file.
    """

    def __init__(
        self,
        store: Store,
        *,
        compression: str = "zstd",
        row_group_size: int | None = None,
        max_rows_per_file: int | None = None,
    ) -> None:
        self._store = store
        self._compression = compression
        self._row_group_size = row_group_size
        self._max_rows_per_file = max_rows_per_file

    @property
    def store(self) -> Store:
        """The underlying store."""
        return self._store

    @property
    def compression(self) -> str:
        """The Parquet compression codec."""
        return self._compression

    @property
    def row_group_size(self) -> int | None:
        """Maximum rows per row group, or ``None`` for PyArrow default."""
        return self._row_group_size

    @property
    def max_rows_per_file(self) -> int | None:
        """Maximum rows per part file, or ``None`` for single file."""
        return self._max_rows_per_file

    # -- public API --------------------------------------------------------

    def write_dataset(
        self,
        table: pa.Table,
        key: str,
        *,
        overwrite: bool = False,
        run_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> DatasetManifest:
        """Write a PyArrow table as a Parquet dataset under *key*.

        Args:
            table: The PyArrow table to write.
            key: Store-relative prefix for the dataset (e.g. ``"silver/orders"``).
            overwrite: If ``True``, delete any existing dataset at *key* first.
                Requires the ``DELETE`` capability.
            run_id: Optional run identifier for lineage tracking.
            metadata: Optional key-value metadata to embed in the manifest.

        Returns:
            A ``DatasetManifest`` describing the written dataset.

        Raises:
            CapabilityNotSupported: If the store lacks ``ATOMIC_WRITE``, or
                ``DELETE`` when *overwrite* is ``True``.
            AlreadyExists: If *overwrite* is ``False`` and the dataset exists.
        """
        if not self._store.supports(Capability.ATOMIC_WRITE):
            raise CapabilityNotSupported(
                f"write_dataset requires ATOMIC_WRITE capability for key {key!r}",
                path=key,
                capability=Capability.ATOMIC_WRITE.value,
            )

        if overwrite:
            if not self._store.supports(Capability.DELETE):
                raise CapabilityNotSupported(
                    f"write_dataset with overwrite=True requires DELETE capability for key {key!r}",
                    path=key,
                    capability=Capability.DELETE.value,
                )
            if self.dataset_exists(key):
                self.delete_dataset(key)
        elif self.dataset_exists(key):
            raise AlreadyExists(
                f"Dataset already exists at {key!r}",
                path=key,
            )

        # Split table into parts
        parts = self._split_table(table)
        part_names: list[str] = []

        for idx, part_table in enumerate(parts):
            name = "data.parquet" if len(parts) == 1 else f"part-{idx:05d}.parquet"
            part_names.append(name)

            buf = io.BytesIO()
            pq.write_table(
                part_table,
                buf,
                compression=self._compression,
                row_group_size=self._row_group_size,
            )
            self._store.write_atomic(f"{key}/{name}", buf.getvalue(), overwrite=True)

        # Build and write manifest
        manifest = DatasetManifest(
            dataset_key=key,
            parts=part_names,
            row_count=table.num_rows,
            schema_hash=_schema_hash(table.schema),
            compression=self._compression,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            run_id=run_id,
            metadata=metadata,
        )
        self._store.write_atomic(f"{key}/manifest.json", manifest.to_json().encode("utf-8"), overwrite=True)

        # Completion marker — write_atomic avoids requiring a separate WRITE capability
        self._store.write_atomic(f"{key}/_SUCCESS", b"", overwrite=True)

        return manifest

    def read_dataset(
        self,
        key: str,
        *,
        columns: list[str] | None = None,
    ) -> pa.Table:
        """Read a Parquet dataset from *key*.

        Args:
            key: Store-relative prefix for the dataset.
            columns: Optional subset of columns to read. ``None`` reads all.

        Returns:
            A PyArrow table with the concatenated contents of all parts.

        Raises:
            DatasetIncomplete: If the ``_SUCCESS`` marker is missing or any
                part listed in the manifest cannot be found.
            ManifestCorrupted: If the manifest cannot be parsed.
            NotFound: If the manifest file does not exist.
        """
        if not self._store.exists(f"{key}/_SUCCESS"):
            raise DatasetIncomplete(
                f"Dataset at {key!r} is incomplete: _SUCCESS marker missing",
                path=key,
            )

        manifest = self.read_manifest(key)

        # Verify all parts exist before reading (fail-fast)
        missing_parts = [part for part in manifest.parts if not self._store.exists(f"{key}/{part}")]
        if missing_parts:
            raise DatasetIncomplete(
                f"Dataset at {key!r} is incomplete: missing parts {missing_parts}",
                path=key,
            )

        tables: list[pa.Table] = []
        for part in manifest.parts:
            raw = self._store.read_bytes(f"{key}/{part}")
            tables.append(pq.read_table(io.BytesIO(raw), columns=columns))

        return pa.concat_tables(tables)

    def read_manifest(self, key: str) -> DatasetManifest:
        """Read and parse the manifest for the dataset at *key*.

        Args:
            key: Store-relative prefix for the dataset.

        Returns:
            The parsed ``DatasetManifest``.

        Raises:
            NotFound: If ``manifest.json`` does not exist.
            ManifestCorrupted: If the manifest cannot be parsed.
        """
        raw = self._store.read_bytes(f"{key}/manifest.json")
        return DatasetManifest.from_json(raw.decode("utf-8"))

    def dataset_exists(self, key: str) -> bool:
        """Check whether a completed dataset exists at *key*.

        Args:
            key: Store-relative prefix for the dataset.

        Returns:
            ``True`` if the ``_SUCCESS`` marker exists, ``False`` otherwise.
        """
        return self._store.exists(f"{key}/_SUCCESS")

    def delete_dataset(self, key: str) -> None:
        """Delete an entire dataset at *key*.

        Args:
            key: Store-relative prefix for the dataset.

        Raises:
            NotFound: If the dataset folder does not exist.
        """
        self._store.delete_folder(key, recursive=True)

    # -- private helpers ---------------------------------------------------

    def _split_table(self, table: pa.Table) -> list[pa.Table]:
        """Split a table into parts based on ``max_rows_per_file``.

        Args:
            table: The table to split.

        Returns:
            A list of table slices. Single-element if no splitting configured.
        """
        if self._max_rows_per_file is None or table.num_rows <= self._max_rows_per_file:
            return [table]

        parts: list[pa.Table] = []
        offset = 0
        while offset < table.num_rows:
            length = min(self._max_rows_per_file, table.num_rows - offset)
            parts.append(table.slice(offset, length))
            offset += length
        return parts
