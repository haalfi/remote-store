"""Dagster IO Manager adapter — wraps any Store as a Dagster [IOManager](https://docs.dagster.io/_apidocs/io-managers#dagster.IOManager).

Lets teams already using remote-store reuse their Store configuration
(credentials, retry policy, caching, observability) inside Dagster pipelines
without duplicating config into dagster-aws / dagster-azure.

Install with ``pip install "remote-store[dagster]"``.

!!! example

    ```python
    from remote_store.ext.dagster import dagster_io_manager

    io_mgr = dagster_io_manager(store, serializer="pickle")
    ```
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import shutil
import tempfile
from typing import IO, TYPE_CHECKING, Any, Protocol, runtime_checkable

try:
    from dagster import (  # type: ignore[import-untyped]
        ConfigurableIOManagerFactory,
        ConfigurableResource,
        Field,
        InitResourceContext,
        IOManager,
        Noneable,
        Permissive,
        StringSource,
    )
    from dagster import _check as dagster_check  # type: ignore[import-untyped]
    from dagster._core.storage.cloud_storage_compute_log_manager import (  # type: ignore[import-untyped]
        PollingComputeLogSubscriptionManager,
        TruncatingCloudStorageComputeLogManager,
    )
    from dagster._core.storage.compute_log_manager import ComputeIOType  # type: ignore[import-untyped]
    from dagster._core.storage.local_compute_log_manager import (  # type: ignore[import-untyped]
        IO_TYPE_EXTENSION,
        LocalComputeLogManager,
    )
    from dagster._serdes import ConfigurableClass, ConfigurableClassData  # type: ignore[import-untyped]
    from dagster._utils import ensure_dir  # type: ignore[import-untyped]
    from pydantic import PrivateAttr  # dagster depends on pydantic
except ModuleNotFoundError as _exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "Dagster is required for the dagster extension. Install it with: pip install 'remote-store[dagster]'"
    ) from _exc

if TYPE_CHECKING:
    import contextlib
    from collections.abc import Mapping, Sequence

    import pyarrow as pa  # type: ignore[import-untyped]

    with contextlib.suppress(ImportError):
        from dagster import InputContext, OutputContext  # type: ignore[import-untyped]
        from dagster._core.storage.compute_log_manager import (  # type: ignore[import-untyped]
            CapturedLogSubscription,
        )

    from remote_store._store import Store

# The compute-log-manager classes above have no public dagster import path —
# dagster's own `dagster-aws` / `dagster-azure` compute log managers import
# them from these `dagster._core` modules too. Paths verified against the
# installed `dagster` (RFC-0014 Open Question 2).

# private: framework integration requires direct registry access; no public path exists
from remote_store._registry import (
    _BACKEND_FACTORIES,
    _register_builtin_backends,
)

log = logging.getLogger(__name__)

__all__ = [
    "DagsterStoreResource",
    "JsonSerializer",
    "ParquetSerializer",
    "PickleSerializer",
    "RemoteStoreComputeLogManager",
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
    """Protocol for pluggable serializers.

    Implement this to provide a custom serializer to
    ``dagster_io_manager(store, serializer=my_serializer)``.
    """

    extension: str

    def serialize(self, obj: Any) -> bytes:
        """Convert a Python object to bytes."""

    def deserialize(self, data: bytes) -> Any:
        """Convert bytes back to a Python object."""


# ---------------------------------------------------------------------------
# Built-in serializers
# ---------------------------------------------------------------------------


class PickleSerializer:
    """Pickle-based serializer. Universal; opaque format."""

    extension: str = ".pkl"

    def serialize(self, obj: Any) -> bytes:
        """Serialize using pickle."""
        return pickle.dumps(obj)

    def deserialize(self, data: bytes) -> Any:
        """Deserialize using pickle."""
        return pickle.loads(data)  # noqa: S301  # CodeQL: intentional — caller explicitly selects PickleSerializer; data originates from the user's own store


class JsonSerializer:
    """JSON serializer. JSON-serializable objects only."""

    extension: str = ".json"

    def serialize(self, obj: Any) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps(obj).encode("utf-8")

    def deserialize(self, data: bytes) -> Any:
        """Deserialize from JSON bytes."""
        return json.loads(data)


class ParquetSerializer:
    """Parquet serializer via PyArrow. DataFrames and Arrow Tables."""

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


def _asset_path(
    context: OutputContext | InputContext,
    ext: str,
    *,
    partition_key: str | None = None,
) -> str:
    """Derive storage path from asset key and partition.

    Path is ``"/".join(asset_key.path)`` plus ``"/" + partition_key`` when
    partitioned, plus the file extension.

    When *partition_key* is given explicitly (multi-partition loading), it is
    used instead of ``context.partition_key``.
    """
    parts = list(context.asset_key.path)
    if partition_key is not None:
        parts.append(partition_key)
    elif context.has_partition_key:
        parts.append(context.partition_key)
    return "/".join(str(p) for p in parts) + ext


def _dataset_key(
    context: OutputContext | InputContext,
    *,
    partition_key: str | None = None,
) -> str:
    """Derive dataset key from asset key and partition (no file extension).

    Datasets are directories, so no extension is appended. Path is
    ``"/".join(asset_key.path)`` plus ``"/" + partition_key`` when partitioned.

    When *partition_key* is given explicitly (multi-partition loading), it is
    used instead of ``context.partition_key``.
    """
    parts = list(context.asset_key.path)
    if partition_key is not None:
        parts.append(partition_key)
    elif context.has_partition_key:
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
        """Serialize and write obj to the Store."""
        path = _asset_path(context, self._serializer.extension)
        data = self._serializer.serialize(obj)
        self._store.write(path, data, overwrite=True)
        context.add_output_metadata({"path": path, "size": len(data)})
        log.debug("Wrote %d bytes to %s", len(data), path)

    def load_input(self, context: InputContext) -> Any:
        """Read and deserialize from the Store.

        When the input context carries multiple partition keys (e.g. a
        time-window aggregation), returns ``dict[str, Any]`` mapping each
        partition key to its deserialized object.
        """
        if context.has_asset_partitions and len(context.asset_partition_keys) > 1:
            result: dict[str, Any] = {}
            for key in context.asset_partition_keys:
                path = _asset_path(context, self._serializer.extension, partition_key=key)
                data = self._store.read_bytes(path)
                log.debug("Read %d bytes from %s", len(data), path)
                result[key] = self._serializer.deserialize(data)
            return result
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
        """Read a Parquet dataset from the Store.

        When the input context carries multiple partition keys, returns
        ``dict[str, Any]`` mapping each partition key to its Arrow Table.
        """
        if context.has_asset_partitions and len(context.asset_partition_keys) > 1:
            result: dict[str, Any] = {}
            for pk in context.asset_partition_keys:
                key = _dataset_key(context, partition_key=pk)
                table = self._pds.read_dataset(key)
                log.debug("Read dataset from %s", key)
                result[pk] = table
            return result
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
    """Wrap a Store as a Dagster IOManager.

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
    """Wrap a Store as a Dagster IOManager using ParquetDatasetStore.

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

    Credential-named options (the ``_SENSITIVE_KEYS`` set shared with
    ``RegistryConfig._from_dict``) are wrapped in ``Secret`` before reaching
    the backend constructor, so they are masked in ``repr()`` and tracebacks.
    The caller's *backend_options* mapping is copied, never mutated.

    Raises:
        ValueError: If *backend_type* is not registered, or if the backend
            constructor rejects the supplied options.
    """
    from remote_store import Secret, Store
    from remote_store._config import _SENSITIVE_KEYS

    _register_builtin_backends()

    factory = _BACKEND_FACTORIES.get(backend_type)
    if factory is None:
        registered = sorted(_BACKEND_FACTORIES.keys())
        msg = f"Unknown backend type {backend_type!r}. Registered types: {registered}"
        raise ValueError(msg)

    options = dict(backend_options)
    for sensitive_key in _SENSITIVE_KEYS:
        value = options.get(sensitive_key)
        if isinstance(value, str):
            options[sensitive_key] = Secret(value)

    try:
        backend = factory(**options)
    except TypeError as exc:
        opts = list(options.keys())
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
    """Dagster resource that constructs a Store from config fields.

    Unlike stateless utility extensions, this class owns Store lifecycle
    because it is a Dagster Resource with ``setup_for_execution`` /
    ``teardown_after_execution`` hooks.

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
    """IO manager factory that constructs a Store from config fields.

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


# ---------------------------------------------------------------------------
# Compute log manager (public API — v3)
# ---------------------------------------------------------------------------


def _clean_prefix(prefix: str) -> str:
    """Drop empty segments from a Store path prefix (e.g. leading/trailing slashes)."""
    return "/".join(part for part in prefix.split("/") if part)


class RemoteStoreComputeLogManager(  # type: ignore[misc]
    TruncatingCloudStorageComputeLogManager,
    ConfigurableClass,
):
    """Captures op/step ``stdout`` / ``stderr`` to any remote-store backend.

    A Dagster ``ComputeLogManager`` wired into ``dagster.yaml`` as an instance
    component. Logs are captured to a local staging directory at the
    file-descriptor level, then uploaded to a ``Store`` the manager builds
    itself from ``backend_type`` + ``backend_options``. When ``upload_interval``
    is set, partial uploads also run periodically while a step executes so the
    Dagster UI can tail them. Subclasses Dagster's
    ``TruncatingCloudStorageComputeLogManager`` (capture-then-upload machinery,
    50 MB upload truncation) and ``ConfigurableClass`` (``dagster.yaml``
    plumbing).

    Configure it in ``dagster.yaml``:

    ```yaml
    compute_logs:
      module: remote_store.ext.dagster
      class: RemoteStoreComputeLogManager
      config:
        backend_type: s3
        backend_options:
          bucket: my-logs-bucket
        root_path: dagster/compute-logs
        upload_interval: 30
    ```

    Attributes:
        backend_type: Registered backend type (``"local"``, ``"s3"``, ``"sftp"``,
            ``"azure"``, ``"memory"``, ...).
        backend_options: Keyword arguments for the backend constructor.
        root_path: Store root prefix applied to every log object.
        local_dir: Local staging directory for capture. Defaults to the
            system temp directory.
        prefix: Path prefix within the Store. Defaults to ``"dagster"``.
        skip_empty_files: Skip uploading zero-byte log files.
        upload_interval: Seconds between partial uploads while a step runs;
            ``None`` (default) disables live tailing.
    """

    def __init__(
        self,
        backend_type: str,
        backend_options: dict[str, Any] | None = None,
        root_path: str = "",
        local_dir: str | None = None,
        prefix: str = "dagster",
        skip_empty_files: bool = False,
        upload_interval: int | None = None,
        inst_data: ConfigurableClassData | None = None,
    ) -> None:
        """Build the Store, validate its capabilities, and wire the local manager.

        Raises:
            ValueError: If *backend_type* is not registered, if the backend
                rejects *backend_options*, or if the backend is missing a
                capability the manager requires (``READ``, ``WRITE``,
                ``DELETE``, ``METADATA``, ``LIST``).
        """
        from remote_store import Capability

        self._store = _build_store(backend_type, backend_options or {}, root_path)
        required = (
            Capability.READ,
            Capability.WRITE,
            Capability.DELETE,
            Capability.METADATA,
            Capability.LIST,
        )
        missing = [cap.name for cap in required if not self._store.supports(cap)]
        if missing:
            self._store.close()
            msg = (
                f"Backend {backend_type!r} is missing capabilities required by "
                f"RemoteStoreComputeLogManager: {', '.join(missing)}"
            )
            raise ValueError(msg)

        self._prefix = _clean_prefix(prefix)
        self._skip_empty_files = skip_empty_files
        self._upload_interval = upload_interval
        self._inst_data = inst_data

        self._local_manager = LocalComputeLogManager(local_dir or tempfile.gettempdir())
        self._subscription_manager = PollingComputeLogSubscriptionManager(self)
        super().__init__()

    # -- ConfigurableClass plumbing (DAG-021) -------------------------------

    @property
    def inst_data(self) -> ConfigurableClassData | None:
        """The ``ConfigurableClassData`` this manager was rehydrated from, if any."""
        return self._inst_data

    @classmethod
    def config_type(cls) -> dict[str, Any]:
        """The ``dagster.yaml`` config schema for this manager."""
        return {
            "backend_type": StringSource,
            "backend_options": Field(Permissive(), is_required=False),
            "root_path": Field(StringSource, is_required=False, default_value=""),
            "local_dir": Field(StringSource, is_required=False),
            "prefix": Field(StringSource, is_required=False, default_value="dagster"),
            "skip_empty_files": Field(bool, is_required=False, default_value=False),
            "upload_interval": Field(Noneable(int), is_required=False, default_value=None),
        }

    @classmethod
    def from_config_value(
        cls, inst_data: ConfigurableClassData | None, config_value: Mapping[str, Any]
    ) -> RemoteStoreComputeLogManager:
        """Construct a manager from a validated ``dagster.yaml`` config value."""
        return cls(inst_data=inst_data, **config_value)

    # -- Inherited-behaviour properties (DAG-023) ---------------------------

    @property
    def local_manager(self) -> LocalComputeLogManager:
        """The ``LocalComputeLogManager`` that stages captures before upload."""
        return self._local_manager

    @property
    def upload_interval(self) -> int | None:
        """Seconds between partial uploads, or ``None`` when live tailing is off."""
        return self._upload_interval if self._upload_interval else None

    # -- Remote path scheme (DAG-024) ---------------------------------------

    def _store_path(self, log_key: Sequence[str], io_type: ComputeIOType, partial: bool = False) -> str:
        """Derive the Store-relative path for one captured log stream."""
        *namespace, filebase = log_key
        filename = f"{filebase}.{IO_TYPE_EXTENSION[io_type]}"
        if partial:
            filename = f"{filename}.partial"
        segments = [seg for seg in (self._prefix, "storage", *namespace) if seg]
        segments.append(filename)
        return "/".join(segments)

    def _store_folder(self, log_key_prefix: Sequence[str]) -> str:
        """Derive the Store-relative folder for a log-key prefix."""
        return "/".join(seg for seg in (self._prefix, "storage", *log_key_prefix) if seg)

    # -- Cloud-storage hooks (DAG-025 – DAG-028) ----------------------------

    def _upload_file_obj(
        self, data: IO[bytes], log_key: Sequence[str], io_type: ComputeIOType, partial: bool = False
    ) -> None:
        """Upload a captured local log file to the Store."""
        local_path = self._local_manager.get_captured_local_path(log_key, IO_TYPE_EXTENSION[io_type])
        if (self._skip_empty_files or partial) and os.stat(local_path).st_size == 0:
            return
        self._store.write(
            self._store_path(log_key, io_type, partial=partial),
            data,  # type: ignore[arg-type]  # an open binary file satisfies BinaryIO at runtime
            overwrite=True,
        )

    def download_from_cloud_storage(
        self, log_key: Sequence[str], io_type: ComputeIOType, partial: bool = False
    ) -> None:
        """Stream a log object from the Store into the local staging file."""
        local_path = self._local_manager.get_captured_local_path(log_key, IO_TYPE_EXTENSION[io_type], partial=partial)
        ensure_dir(os.path.dirname(local_path))
        store_path = self._store_path(log_key, io_type, partial=partial)
        with self._store.read(store_path) as src, open(local_path, "wb") as dst:
            shutil.copyfileobj(src, dst)

    def cloud_storage_has_logs(self, log_key: Sequence[str], io_type: ComputeIOType, partial: bool = False) -> bool:
        """Return whether the Store holds a log object for this key."""
        return self._store.is_file(self._store_path(log_key, io_type, partial=partial))

    def display_path_for_type(  # type: ignore[override]  # base hint is `str`; `None` until capture completes (matches S3ComputeLogManager)
        self, log_key: Sequence[str], io_type: ComputeIOType
    ) -> str | None:
        """A human-readable Store location for the Dagster UI, once capture is done."""
        if not self.is_capture_complete(log_key):
            return None
        return self._store.native_path(self._store_path(log_key, io_type))

    def download_url_for_type(self, log_key: Sequence[str], io_type: ComputeIOType) -> str | None:
        """No signed-URL primitive in v1 — the webserver streams logs itself."""
        return None

    # -- Deletion and enumeration (DAG-029, DAG-031) ------------------------

    def delete_logs(self, log_key: Sequence[str] | None = None, prefix: Sequence[str] | None = None) -> None:
        """Delete captured logs by ``log_key`` or by ``prefix``, local and remote.

        Raises:
            CheckError: If neither *log_key* nor *prefix* is given.
        """
        if log_key is None and prefix is None:
            dagster_check.failed("Must pass in either `log_key` or `prefix` argument to delete_logs")
        self._local_manager.delete_logs(log_key=log_key, prefix=prefix)
        if log_key:
            for io_type in (ComputeIOType.STDOUT, ComputeIOType.STDERR):
                for partial in (False, True):
                    self._store.delete(self._store_path(log_key, io_type, partial=partial), missing_ok=True)
        elif prefix:
            self._store.delete_folder(self._store_folder(prefix), recursive=True, missing_ok=True)

    def get_log_keys_for_log_key_prefix(
        self, log_key_prefix: Sequence[str], io_type: ComputeIOType
    ) -> Sequence[Sequence[str]]:
        """Enumerate the stored log keys under a log-key prefix."""
        extension = IO_TYPE_EXTENSION[io_type]
        results: list[list[str]] = []
        for info in self._store.list_files(self._store_folder(log_key_prefix)):
            # `rpartition` keeps this robust against a dotless stray file
            # (no extension) and excludes `.partial` uploads, whose final
            # segment is `partial`, not `out` / `err`.
            filebase, dot, obj_extension = info.name.rpartition(".")
            if dot and obj_extension == extension:
                results.append([*log_key_prefix, filebase])
        return results

    # -- Subscriptions and lifecycle (DAG-030, DAG-032) ---------------------

    def on_subscribe(self, subscription: CapturedLogSubscription) -> None:
        """Register a UI live-tail subscription with the polling manager."""
        self._subscription_manager.add_subscription(subscription)

    def on_unsubscribe(self, subscription: CapturedLogSubscription) -> None:
        """Deregister a UI live-tail subscription from the polling manager."""
        self._subscription_manager.remove_subscription(subscription)

    def dispose(self) -> None:
        """Dispose the subscription and local managers and close the Store."""
        self._subscription_manager.dispose()
        # super().dispose() disposes local_manager; calling it (rather than
        # self._local_manager.dispose() directly) inherits any cleanup a
        # future dagster CloudStorageComputeLogManager.dispose() adds.
        super().dispose()
        self._store.close()
