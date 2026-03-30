"""Dagster IO Manager adapter — wraps any Store as a Dagster [IOManager](https://docs.dagster.io/_apidocs/io-managers#dagster.IOManager).

Lets teams already using remote-store reuse their Store configuration
(credentials, retry policy, caching, observability) inside Dagster pipelines
without duplicating config into dagster-aws / dagster-azure.

Install with ``pip install "remote-store[dagster]"``.

Usage:

```python
from remote_store.ext.dagster import dagster_io_manager

io_mgr = dagster_io_manager(store, serializer="pickle")
```
"""

from __future__ import annotations

import json
import logging
import pickle
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

try:
    from dagster import (  # type: ignore[import-untyped]
        ConfigurableIOManagerFactory,
        ConfigurableResource,
        InitResourceContext,
        IOManager,
    )
    from pydantic import PrivateAttr  # dagster depends on pydantic
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "Dagster is required for the dagster extension. Install it with: pip install 'remote-store[dagster]'"
    ) from _exc

if TYPE_CHECKING:
    import contextlib

    import pyarrow as pa  # type: ignore[import-untyped]

    with contextlib.suppress(ImportError):
        from dagster import InputContext, OutputContext  # type: ignore[import-untyped]

    from remote_store._store import Store

from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

log = logging.getLogger(__name__)

__all__ = [
    "DagsterStoreResource",
    "JsonSerializer",
    "ParquetSerializer",
    "PickleSerializer",
    "RemoteStoreIOManager",
    "Serializer",
    "dagster_dataset_io_manager",
    "dagster_io_manager",
]

# ---------------------------------------------------------------------------
# Serializer protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Serializer(Protocol):
    """Protocol for pluggable serializers (DAG-001).

    Implement this to provide a custom serializer to
    ``dagster_io_manager(store, serializer=my_serializer)``.
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
    """Parquet serializer via PyArrow (DAG-004). DataFrames and Arrow Tables."""

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
        elif isinstance(obj, pa.Table):
            table = obj
        elif hasattr(obj, "dtypes"):
            # pandas DataFrame
            table = pa.Table.from_pandas(obj)  # type: ignore[no-untyped-call]
        else:
            msg = f"ParquetSerializer expects a DataFrame, got {type(obj).__name__}"
            raise TypeError(msg)

        buf = io.BytesIO()
        pq.write_table(table, buf)  # type: ignore[no-untyped-call]
        return buf.getvalue()

    def deserialize(self, data: bytes) -> pa.Table:
        """Deserialize Parquet bytes to a PyArrow Table."""
        import io

        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        buf = io.BytesIO(data)
        return pq.read_table(buf)  # type: ignore[no-untyped-call]


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


def _dataset_key(context: OutputContext | InputContext) -> str:
    """Derive dataset key from asset key and partition (no file extension).

    Datasets are directories, so no extension is appended. Path is
    ``"/".join(asset_key.path)`` plus ``"/" + partition_key`` when partitioned.
    """
    parts = list(context.asset_key.path)
    if context.has_partition_key:
        parts.append(context.partition_key)
    return "/".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# IO Manager implementations (internal)
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


class _DatasetIOManagerImpl(IOManager):  # type: ignore[misc]
    """Internal IOManager using ParquetDatasetStore for dataset I/O."""

    def __init__(self, store: Store) -> None:
        try:
            from remote_store.ext.parquet import ParquetDatasetStore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "PyArrow is required for dataset mode. Install it with: pip install 'remote-store[dagster,arrow]'"
            ) from exc
        self._pds = ParquetDatasetStore(store)

    def handle_output(self, context: OutputContext, obj: Any) -> None:
        """Write a DataFrame as a Parquet dataset to the Store."""
        import pyarrow as pa  # type: ignore[import-untyped]

        if hasattr(obj, "to_arrow"):
            table = obj.to_arrow()  # Polars
        elif isinstance(obj, pa.Table):
            table = obj
        elif hasattr(obj, "dtypes"):
            table = pa.Table.from_pandas(obj)  # type: ignore[no-untyped-call]  # pandas
        else:
            msg = f"Dataset mode expects a DataFrame, got {type(obj).__name__}"
            raise TypeError(msg)

        key = _dataset_key(context)
        self._pds.write_dataset(table, key, overwrite=True)
        context.add_output_metadata({"dataset_key": key})
        log.debug("Wrote dataset to %s", key)

    def load_input(self, context: InputContext) -> Any:
        """Read a Parquet dataset from the Store."""
        key = _dataset_key(context)
        table = self._pds.read_dataset(key)
        log.debug("Read dataset from %s", key)
        return table


# ---------------------------------------------------------------------------
# Factory functions (public API — v1)
# ---------------------------------------------------------------------------


def dagster_io_manager(
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


def dagster_dataset_io_manager(store: Store) -> IOManager:  # type: ignore[type-arg]
    """Wrap a Store as a Dagster IOManager using ParquetDatasetStore (DAG-017).

    Unlike ``dagster_io_manager`` which serializes objects to single files,
    this manager writes Parquet datasets (multi-file with manifest) via
    ``ParquetDatasetStore``.

    Args:
        store: An existing Store instance. The caller owns its lifecycle.

    Returns:
        A Dagster ``IOManager`` backed by ParquetDatasetStore.
    """
    return _DatasetIOManagerImpl(store)


# ---------------------------------------------------------------------------
# Shared Store lifecycle helpers (v2)
# ---------------------------------------------------------------------------


def _build_store(backend_type: str, backend_options: dict[str, Any], root_path: str) -> Store:
    """Build a Store from registry config fields.

    Raises:
        ValueError: If *backend_type* is not registered, or if the backend
            constructor rejects the supplied options.
    """
    from remote_store._store import Store

    _register_builtin_backends()

    factory = _BACKEND_FACTORIES.get(backend_type)
    if factory is None:
        registered = sorted(_BACKEND_FACTORIES.keys())
        msg = f"Unknown backend type {backend_type!r}. Registered types: {registered}"
        raise ValueError(msg)

    try:
        backend = factory(**backend_options)
    except TypeError as exc:
        opts = list(backend_options.keys())
        msg = f"Backend {backend_type!r} rejected the provided options {opts}: {exc}"
        raise ValueError(msg) from exc

    return Store(backend, root_path=root_path)


def _close_store(store: Store | None) -> None:
    """Close a Store if it exists."""
    if store is not None:
        store.close()


# ---------------------------------------------------------------------------
# Resource and IO manager factory (public API — v2)
# ---------------------------------------------------------------------------


class DagsterStoreResource(ConfigurableResource):  # type: ignore[misc,type-arg]
    """Dagster resource that constructs a Store from config fields (DAG-012).

    Unlike stateless utility extensions (ADR-0008), this class owns Store
    lifecycle because it is a Dagster Resource with ``setup_for_execution``
    / ``teardown_after_execution`` hooks.

    Attributes:
        backend_type: Backend type string (e.g. ``"local"``, ``"s3"``, ``"memory"``).
            Must be registered in the backend factory registry.
        backend_options: Keyword arguments passed to the backend constructor.
        root_path: Optional root path for the Store.
    """

    backend_type: str
    backend_options: dict[str, Any] = {}
    root_path: str = ""

    _store: Store | None = PrivateAttr(default=None)

    def setup_for_execution(self, context: InitResourceContext) -> None:
        """Instantiate and cache the Store (called by Dagster before execution).

        Raises:
            ValueError: If *backend_type* is not registered, or if the backend
                constructor rejects the supplied *backend_options*.
        """
        self._store = _build_store(self.backend_type, self.backend_options, self.root_path)

    def teardown_after_execution(self, context: InitResourceContext) -> None:
        """Close the Store and release resources (called by Dagster after execution)."""
        _close_store(self._store)
        self._store = None

    def get_store(self) -> Store:
        """Return the underlying Store instance.

        Returns:
            The Store constructed during ``setup_for_execution``.

        Raises:
            RuntimeError: If called before ``setup_for_execution`` has run.
        """
        if self._store is None:
            msg = "Store is not available. Ensure setup_for_execution has been called."
            raise RuntimeError(msg)
        return self._store


class RemoteStoreIOManager(ConfigurableIOManagerFactory):  # type: ignore[misc,type-arg]
    """IO manager factory that constructs a Store from config fields (DAG-015).

    Embeds backend configuration directly so the IO manager owns the full
    Store lifecycle (setup and teardown). For direct Store access in assets,
    use ``DagsterStoreResource`` as a separate resource.

    Attributes:
        backend_type: Backend type string (e.g. ``"local"``, ``"s3"``, ``"memory"``).
        backend_options: Keyword arguments passed to the backend constructor.
        root_path: Optional root path for the Store.
        serializer: Serializer name. Use ``"parquet-dataset"`` for multi-file
            Parquet dataset output via ``ParquetDatasetStore``.
    """

    backend_type: str
    backend_options: dict[str, Any] = {}
    root_path: str = ""
    serializer: str = "pickle"

    _store: Store | None = PrivateAttr(default=None)

    def setup_for_execution(self, context: InitResourceContext) -> None:
        """Build and cache the Store before execution."""
        self._store = _build_store(self.backend_type, self.backend_options, self.root_path)

    def teardown_after_execution(self, context: InitResourceContext) -> None:
        """Close the Store and release resources."""
        _close_store(self._store)
        self._store = None

    def create_io_manager(self, context: Any) -> IOManager:  # type: ignore[type-arg]
        """Construct the IOManager for the given execution context.

        Returns:
            A ``_DatasetIOManagerImpl`` when ``serializer="parquet-dataset"``,
            otherwise a ``_RemoteStoreIOManagerImpl`` with the resolved serializer.

        Raises:
            RuntimeError: If called before ``setup_for_execution``.
            ValueError: If *serializer* is an unrecognized string.
        """
        if self._store is None:
            msg = "Store is not available. Ensure setup_for_execution has been called."
            raise RuntimeError(msg)
        if self.serializer == "parquet-dataset":
            return _DatasetIOManagerImpl(self._store)
        resolved = _resolve_serializer(self.serializer)
        return _RemoteStoreIOManagerImpl(self._store, resolved)
