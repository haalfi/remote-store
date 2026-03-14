"""Dagster IO Manager adapter — wraps any Store as a Dagster `IOManager <https://docs.dagster.io/_apidocs/io-managers#dagster.IOManager>`_.

Lets teams already using remote-store reuse their Store configuration
(credentials, retry policy, caching, observability) inside Dagster pipelines
without duplicating config into dagster-aws / dagster-azure.

Install with ``pip install "remote-store[dagster]"``.

Usage:

```python
from remote_store.ext.dagster import remote_store_io_manager

io_mgr = remote_store_io_manager(store, serializer="pickle")
```
"""

from __future__ import annotations

import json
import logging
import pickle
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

try:
    from dagster import IOManager  # type: ignore[import-untyped]
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "Dagster is required for the dagster extension. Install it with: pip install 'remote-store[dagster]'"
    ) from _exc

if TYPE_CHECKING:
    from dagster import InputContext, OutputContext  # type: ignore[import-untyped]

    from remote_store._store import Store

log = logging.getLogger(__name__)

__all__ = [
    "JsonSerializer",
    "ParquetSerializer",
    "PickleSerializer",
    "Serializer",
    "remote_store_io_manager",
]

# ---------------------------------------------------------------------------
# Serializer protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Serializer(Protocol):
    """Protocol for pluggable serializers (DAG-001).

    Implement this to provide a custom serializer to
    ``remote_store_io_manager(store, serializer=my_serializer)``.
    """

    extension: str

    def serialize(self, obj: Any) -> bytes:
        """Convert a Python object to bytes."""
        ...

    def deserialize(self, data: bytes) -> Any:
        """Convert bytes back to a Python object."""
        ...


# ---------------------------------------------------------------------------
# Built-in serializers
# ---------------------------------------------------------------------------


class PickleSerializer:
    """Pickle-based serializer (DAG-002). Universal; opaque format."""

    extension: str = ".pkl"

    def serialize(self, obj: Any) -> bytes:
        """Serialize using pickle."""
        return pickle.dumps(obj)

    def deserialize(self, data: bytes) -> Any:
        """Deserialize using pickle."""
        return pickle.loads(data)  # noqa: S301


class JsonSerializer:
    """JSON serializer (DAG-003). JSON-serializable objects only."""

    extension: str = ".json"

    def serialize(self, obj: Any) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps(obj).encode("utf-8")

    def deserialize(self, data: bytes) -> Any:
        """Deserialize from JSON bytes."""
        return json.loads(data)


class ParquetSerializer:
    """Parquet serializer via PyArrow (DAG-004). DataFrames only."""

    extension: str = ".parquet"

    def __init__(self) -> None:
        try:
            import pyarrow  # type: ignore[import-untyped]  # noqa: F401
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "PyArrow is required for the parquet serializer. "
                "Install it with: pip install 'remote-store[dagster,arrow]'"
            ) from exc

    def serialize(self, obj: Any) -> bytes:
        """Serialize a DataFrame to Parquet bytes."""
        import io

        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        if hasattr(obj, "to_arrow"):
            # Polars DataFrame → Arrow Table
            table = obj.to_arrow()
        elif hasattr(obj, "to_pandas"):
            # Already an Arrow Table or similar
            table = obj
        else:
            # pandas DataFrame
            table = pa.Table.from_pandas(obj)  # type: ignore[no-untyped-call]

        buf = io.BytesIO()
        pq.write_table(table, buf)  # type: ignore[no-untyped-call]
        return buf.getvalue()

    def deserialize(self, data: bytes) -> Any:
        """Deserialize Parquet bytes to a pandas DataFrame."""
        import io

        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        buf = io.BytesIO(data)
        table = pq.read_table(buf)  # type: ignore[no-untyped-call]
        return table.to_pandas()


# ---------------------------------------------------------------------------
# Serializer resolution
# ---------------------------------------------------------------------------

_SERIALIZER_MAP: dict[str, type[PickleSerializer] | type[JsonSerializer] | type[ParquetSerializer]] = {
    "pickle": PickleSerializer,
    "json": JsonSerializer,
    "parquet": ParquetSerializer,
}


def _resolve_serializer(serializer: str | Serializer) -> Serializer:
    """Resolve a serializer string or instance to a Serializer object."""
    if isinstance(serializer, str):
        cls = _SERIALIZER_MAP.get(serializer)
        if cls is None:
            msg = f"Unknown serializer {serializer!r}. Choose from: {', '.join(sorted(_SERIALIZER_MAP))}"
            raise ValueError(msg)
        return cls()
    return serializer


# ---------------------------------------------------------------------------
# Path derivation
# ---------------------------------------------------------------------------


def _asset_path(context: OutputContext | InputContext, ext: str) -> str:
    """Derive storage path from asset key and partition (DAG-005, DAG-006).

    Path is ``"/".join(asset_key.path)`` plus ``"/" + partition_key`` when
    partitioned, plus the file extension.
    """
    parts = list(context.asset_key.path)
    if context.has_partition_key:
        parts.append(context.partition_key)
    return "/".join(str(p) for p in parts) + ext


# ---------------------------------------------------------------------------
# IO Manager implementation (internal)
# ---------------------------------------------------------------------------


class _RemoteStoreIOManagerImpl(IOManager):  # type: ignore[misc]
    """Internal IOManager wrapping a Store with a Serializer."""

    def __init__(self, store: Store, serializer: Serializer) -> None:
        self._store = store
        self._serializer = serializer

    def handle_output(self, context: OutputContext, obj: Any) -> None:
        """Serialize and write obj to the Store (DAG-007)."""
        path = _asset_path(context, self._serializer.extension)
        data = self._serializer.serialize(obj)
        self._store.write(path, data, overwrite=True)
        context.add_output_metadata({"path": path, "size": len(data)})
        log.debug("Wrote %d bytes to %s", len(data), path)

    def load_input(self, context: InputContext) -> Any:
        """Read and deserialize from the Store (DAG-008)."""
        path = _asset_path(context, self._serializer.extension)
        data = self._store.read_bytes(path)
        log.debug("Read %d bytes from %s", len(data), path)
        return self._serializer.deserialize(data)


# ---------------------------------------------------------------------------
# Factory function (public API)
# ---------------------------------------------------------------------------


def remote_store_io_manager(
    store: Store,
    *,
    serializer: str | Serializer = "pickle",
) -> IOManager:  # type: ignore[type-arg]
    """Wrap a Store as a Dagster IOManager (DAG-011).

    Args:
        store: An existing Store instance. The caller owns its lifecycle —
            the IO manager does not close the Store.
        serializer: ``"pickle"`` (default), ``"json"``, ``"parquet"``, or a
            custom object satisfying the ``Serializer`` protocol.

    Returns:
        A Dagster ``IOManager`` backed by the given Store.

    Raises:
        ValueError: If *serializer* is an unrecognized string.
    """
    resolved = _resolve_serializer(serializer)
    return _RemoteStoreIOManagerImpl(store, resolved)
