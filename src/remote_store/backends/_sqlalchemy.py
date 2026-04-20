"""SQLAlchemy backends — blob store and query materializer."""

from __future__ import annotations

import abc
import contextlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, TypeVar, cast, runtime_checkable

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from remote_store._glob import pattern_to_regex
from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo, WriteResult
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

# Module-level import (unlike _sftp/_s3/_azure which defer to __init__/method
# bodies).  Acceptable because this module is already behind a try/except in
# backends/__init__.py, so sqlalchemy is never loaded unless explicitly opted-in.
try:
    import sqlalchemy as sa
    from sqlalchemy import Engine, event
except ImportError as _imp_err:  # pragma: no cover
    raise ImportError(
        "SQLAlchemy backends require the 'sqlalchemy' package. Install with: pip install remote-store[sql]"
    ) from _imp_err

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.LAZY_READ})
_QUERY_CAPABILITIES = CapabilitySet(
    {Capability.READ, Capability.LIST, Capability.METADATA, Capability.GLOB, Capability.SEEKABLE_READ}
)

log = logging.getLogger(__name__)


def _set_sqlite_pragmas(dbapi_conn: Any, _connection_record: Any) -> None:
    """Set SQLite PRAGMAs on every new raw DBAPI connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# ---------------------------------------------------------------------------
# Base class (shared with future SQLQueryBackend)
# ---------------------------------------------------------------------------


class _SQLAlchemyBaseBackend(Backend, abc.ABC):
    """Shared base for SQLAlchemy-backed storage backends.

    Manages engine lifecycle (owned vs borrowed), health checks,
    error mapping, and SQLite detection.
    """

    def __init__(self, url: str | None = None, *, engine: Engine | None = None) -> None:
        if (url is None) == (engine is None):
            msg = "Exactly one of 'url' or 'engine' must be provided"
            raise ValueError(msg)

        if url is not None:
            self._engine = sa.create_engine(url)
            self._owns_engine = True
        else:
            assert engine is not None
            self._engine = engine
            self._owns_engine = False

        self._is_sqlite = self._engine.dialect.name == "sqlite"

        if self._is_sqlite:
            self._configure_sqlite()

    def _configure_sqlite(self) -> None:
        """Set SQLite PRAGMAs on every new connection (idempotent)."""
        if not event.contains(self._engine, "connect", _set_sqlite_pragmas):
            event.listen(self._engine, "connect", _set_sqlite_pragmas)

    def check_health(self) -> None:
        """Verify database connectivity via ``SELECT 1``."""
        try:
            with self._engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
        except sa.exc.SQLAlchemyError as exc:
            raise BackendUnavailable(f"Database health check failed: {exc}", backend=self.name) from exc

    def close(self) -> None:
        """Dispose the engine if owned. No-op for borrowed engines."""
        if self._owns_engine:
            self._engine.dispose()

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the SQLAlchemy ``Engine`` if requested."""
        if type_hint is Engine or (isinstance(type_hint, type) and issubclass(type_hint, Engine)):
            return cast(T, self._engine)  # noqa: TC006
        return super().unwrap(type_hint)

    @contextlib.contextmanager
    def _map_errors(self, path: str = "") -> Iterator[None]:
        """Context manager that catches SQLAlchemy errors and re-raises as remote-store errors."""
        try:
            yield
        except (RemoteStoreError, ValueError):
            raise
        except sa.exc.IntegrityError as exc:
            raise AlreadyExists(f"Key already exists: {path}", path=path, backend=self.name) from exc
        except sa.exc.OperationalError as exc:
            raise BackendUnavailable(f"Database operation failed: {exc}", path=path, backend=self.name) from exc
        except sa.exc.SQLAlchemyError as exc:
            raise RemoteStoreError(f"Database error: {exc}", path=path, backend=self.name) from exc

    def _validate_path(self, path: str, *, allow_empty: bool = False) -> list[str]:
        """Validate and split a path. Returns segments."""
        if "\0" in path:
            raise InvalidPath("Path contains null byte", path=path, backend=self.name)
        if path.startswith("/"):
            raise InvalidPath("Absolute paths are not allowed", path=path, backend=self.name)

        segments: list[str] = []
        for seg in path.split("/"):
            if seg == "" or seg == ".":
                continue
            if seg == "..":
                raise InvalidPath("Path contains '..' segment", path=path, backend=self.name)
            segments.append(seg)

        if not segments and not allow_empty:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend=self.name)

        return segments


# ---------------------------------------------------------------------------
# ResultSerializer protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ResultSerializer(Protocol):
    """Converts SQL result rows to bytes in a specific format."""

    def serialize(self, rows: Sequence[Any], columns: Sequence[str], format: str) -> bytes:
        """Serialize rows with given column names to the specified format.

        Args:
            rows: Sequence of row tuples from SQL execution.
            columns: Column name list.
            format: Target format (``"parquet"``, ``"csv"``, ``"arrow"``).

        Returns:
            Serialized bytes.
        """


class ArrowSerializer:
    """Serializes SQL result sets via PyArrow.

    Converts rows + columns to a ``pyarrow.Table``, then writes to the
    requested format. Imports ``pyarrow`` lazily so that ``SQLBlobBackend``
    remains importable without it.
    """

    def serialize(self, rows: Sequence[Any], columns: Sequence[str], format: str) -> bytes:
        """Serialize rows to Parquet, CSV, or Arrow IPC."""
        import pyarrow as pa  # type: ignore[import-untyped]  # noqa: PLC0415
        import pyarrow.csv as pcsv  # type: ignore[import-untyped]  # noqa: PLC0415
        import pyarrow.ipc as pipc  # type: ignore[import-untyped]  # noqa: PLC0415
        import pyarrow.parquet as pq  # type: ignore[import-untyped]  # noqa: PLC0415

        # Build Arrow table from rows
        if rows:
            col_arrays = list(zip(*rows, strict=True))
            arrays = [pa.array(col) for col in col_arrays]
        else:
            arrays = [pa.array([], type=pa.string()) for _ in columns]
        table = pa.table(dict(zip(columns, arrays, strict=True)))

        buf = io.BytesIO()
        if format == "parquet":
            pq.write_table(table, buf)
        elif format == "csv":
            pcsv.write_csv(table, buf)
        elif format in ("arrow", "ipc"):
            writer = pipc.new_file(buf, table.schema)
            writer.write_table(table)
            writer.close()
        else:
            msg = f"Unsupported serialization format: {format!r}"
            raise ValueError(msg)

        return buf.getvalue()


# ---------------------------------------------------------------------------
# SQLBlobBackend
# ---------------------------------------------------------------------------


class SQLBlobBackend(_SQLAlchemyBaseBackend):
    """SQL key-value blob store implementing the full Backend contract.

    Uses a SQL table as key-value storage. Each row holds one "file"
    with its key, data, and metadata. SQLite receives WAL mode and
    PRAGMA tuning automatically.

    Supports all capabilities except ``LAZY_READ``.

    Note:
        **Non-lazy reads and writes.** Both ``read()`` and ``write()``
        materialize the full content in memory. ``read()`` loads the
        entire BLOB before returning a stream (no ``LAZY_READ``).
        ``write()`` reads the full stream before issuing the SQL
        INSERT/UPDATE because BLOB columns require complete data in a
        single statement. For files larger than process memory, use a
        blob-storage backend (S3, Local, Azure) instead.
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        engine: Engine | None = None,
        table_name: str = "remote_store_objects",
        create_table: bool = True,
        max_blob_size: int | None = None,
    ) -> None:
        if not table_name:
            msg = "table_name must be a non-empty string"
            raise ValueError(msg)
        if max_blob_size is not None and max_blob_size <= 0:
            msg = "max_blob_size must be a positive integer"
            raise ValueError(msg)

        super().__init__(url=url, engine=engine)
        self._table_name = table_name
        self._max_blob_size = max_blob_size

        self._metadata = sa.MetaData()

        if create_table:
            self._table = sa.Table(
                table_name,
                self._metadata,
                sa.Column("key", sa.Text, primary_key=True),
                sa.Column("data", sa.LargeBinary, nullable=False),
                sa.Column("size", sa.Integer, nullable=False),
                sa.Column("modified_at", sa.Float, nullable=False),
                sa.Column("content_type", sa.Text, nullable=True),
                sa.Column("digest", sa.Text, nullable=True),
                sa.Column("extra", sa.Text, nullable=True),
                sa.Column("user_metadata", sa.Text, nullable=True),
            )
            self._metadata.create_all(self._engine)
            self._optional_columns = {"size", "modified_at", "content_type", "digest", "extra", "user_metadata"}
        else:
            self._table = sa.Table(table_name, self._metadata, autoload_with=self._engine)
            col_names = {c.name for c in self._table.columns}
            if "key" not in col_names or "data" not in col_names:
                msg = f"Table '{table_name}' must have at least 'key' and 'data' columns"
                raise ValueError(msg)
            self._optional_columns = col_names & {
                "size",
                "modified_at",
                "content_type",
                "digest",
                "extra",
                "user_metadata",
            }

        # Both USER_METADATA and WRITE_RESULT_NATIVE are declared only when the
        # backing table has the user_metadata column.  Advertising USER_METADATA
        # without the column causes silent WR-013 violations (Store gate passes,
        # data never stored).  WRITE_RESULT_NATIVE is stripped alongside it so
        # the spec 045 WR-004/WR-010 tables ("dynamic") agree with the code.
        if "user_metadata" in self._optional_columns:
            self._capabilities: CapabilitySet = _ALL_CAPABILITIES
        else:
            _legacy_excluded = {Capability.USER_METADATA, Capability.WRITE_RESULT_NATIVE}
            self._capabilities = CapabilitySet({c for c in _ALL_CAPABILITIES if c not in _legacy_excluded})

    # region: properties

    @property
    def name(self) -> str:
        return "sql-blob"

    @property
    def capabilities(self) -> CapabilitySet:
        return self._capabilities

    # endregion

    # region: interop

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with SQL blob details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind="sql-blob"`` and ``details`` containing
            ``table_name``.
        """
        from remote_store._resolution import ResolutionPlan as _RP

        return _RP(
            kind="sql-blob",
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={"table_name": self._table_name},
        )

    # endregion

    # region: public methods — existence

    def exists(self, path: str) -> bool:
        segs = self._validate_path(path, allow_empty=True)
        if not segs:
            return True  # root always exists
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            # Check file
            row = conn.execute(sa.select(sa.literal(1)).where(t.c.key == path)).first()
            if row is not None:
                return True
            # Check folder (any key with prefix)
            prefix = path + "/"
            row = conn.execute(sa.select(sa.literal(1)).where(t.c.key.like(prefix + "%")).limit(1)).first()
            return row is not None

    def is_file(self, path: str) -> bool:
        segs = self._validate_path(path, allow_empty=True)
        if not segs:
            return False
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            row = conn.execute(sa.select(sa.literal(1)).where(t.c.key == path)).first()
            return row is not None

    def is_folder(self, path: str) -> bool:
        segs = self._validate_path(path, allow_empty=True)
        if not segs:
            return True  # root is a folder
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            prefix = path + "/"
            row = conn.execute(sa.select(sa.literal(1)).where(t.c.key.like(prefix + "%")).limit(1)).first()
            return row is not None

    # endregion

    # region: public methods — reading

    def read(self, path: str) -> BinaryIO:
        self._validate_path(path)
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            row = conn.execute(sa.select(t.c.data).where(t.c.key == path)).first()
            if row is None:
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            data = row[0]
        return io.BytesIO(data)

    def read_bytes(self, path: str) -> bytes:
        self._validate_path(path)
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            row = conn.execute(sa.select(t.c.data).where(t.c.key == path)).first()
            if row is None:
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            return bytes(row[0])

    # endregion

    # region: public methods — writing

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        self._validate_path(path)
        # SQL BLOB columns require full materialization; streaming writes
        # are not possible.  This is by-design (ID-136).
        raw = content if isinstance(content, bytes) else content.read()

        if self._max_blob_size is not None and len(raw) > self._max_blob_size:
            msg = f"Content size ({len(raw)} bytes) exceeds max_blob_size ({self._max_blob_size} bytes)"
            raise ValueError(msg)

        now = datetime.now(timezone.utc).timestamp()
        meta_json = json.dumps(dict(metadata)) if metadata else None

        with self._map_errors(path), self._engine.begin() as conn:
            t = self._table
            existing = conn.execute(sa.select(sa.literal(1)).where(t.c.key == path)).first()

            values: dict[str, Any] = {"data": raw}
            if "size" in self._optional_columns:
                values["size"] = len(raw)
            if "modified_at" in self._optional_columns:
                values["modified_at"] = now
            if "user_metadata" in self._optional_columns:
                values["user_metadata"] = meta_json

            if existing is not None:
                if not overwrite:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                conn.execute(t.update().where(t.c.key == path).values(**values))
            else:
                values["key"] = path
                conn.execute(t.insert().values(**values))

        has_meta_col = "user_metadata" in self._optional_columns
        last_modified = (
            datetime.fromtimestamp(now, tz=timezone.utc)
            if has_meta_col and "modified_at" in self._optional_columns
            else None
        )
        return WriteResult(
            path=RemotePath(path),
            size=len(raw),
            source="native" if has_meta_col else "basic",
            last_modified=last_modified,
            metadata=metadata if has_meta_col else None,
        )

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        return self.write(path, content, overwrite=overwrite, metadata=metadata)

    @contextlib.contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        self._validate_path(path)
        if not overwrite:
            with self._map_errors(path), self._engine.connect() as conn:
                t = self._table
                if conn.execute(sa.select(sa.literal(1)).where(t.c.key == path)).first() is not None:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        buf: BinaryIO = io.BytesIO()
        yield buf
        buf.seek(0)
        self.write(path, buf.read(), overwrite=overwrite)

    # endregion

    # region: public methods — deletion

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        self._validate_path(path)
        with self._map_errors(path), self._engine.begin() as conn:
            t = self._table
            result = conn.execute(t.delete().where(t.c.key == path))
            if result.rowcount == 0 and not missing_ok:
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        self._validate_path(path)
        prefix = path + "/"
        with self._map_errors(path), self._engine.begin() as conn:
            t = self._table
            # Check if any keys exist under this prefix
            has_children = conn.execute(sa.select(sa.literal(1)).where(t.c.key.like(prefix + "%")).limit(1)).first()

            if has_children is None:
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
                return

            if not recursive:
                raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)

            conn.execute(t.delete().where(t.c.key.like(prefix + "%")))

    # endregion

    # region: public methods — listing

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        cols = self._select_info_columns()
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            query = sa.select(*cols).where(t.c.key.like(prefix + "%")) if prefix else sa.select(*cols)
            rows = conn.execute(query).fetchall()

        results: list[FileInfo] = []
        for row in rows:
            key = row[0]
            suffix = key[len(prefix) :]

            if not recursive and max_depth is None:
                # Non-recursive: only direct children
                if "/" in suffix:
                    continue
            elif max_depth is not None:
                depth = suffix.count("/")
                if depth > max_depth:
                    continue

            results.append(self._row_to_file_info(row))
        yield from results

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            query = sa.select(t.c.key).where(t.c.key.like(prefix + "%")) if prefix else sa.select(t.c.key)
            rows = conn.execute(query).fetchall()

        seen: set[str] = set()
        results: list[FolderEntry] = []
        for (key,) in rows:
            suffix = key[len(prefix) :]
            if "/" in suffix:
                folder_name = suffix.split("/", 1)[0]
                if folder_name not in seen:
                    seen.add(folder_name)
                    folder_path = f"{prefix}{folder_name}"
                    results.append(FolderEntry(path=RemotePath(folder_path), name=folder_name))
        yield from results

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        cols = self._select_info_columns()
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            query = sa.select(*cols).where(t.c.key.like(prefix + "%")) if prefix else sa.select(*cols)
            rows = conn.execute(query).fetchall()

        seen_folders: set[str] = set()
        results: list[FileInfo | FolderEntry] = []
        for row in rows:
            key = row[0]
            suffix = key[len(prefix) :]
            if "/" in suffix:
                folder_name = suffix.split("/", 1)[0]
                if folder_name not in seen_folders:
                    seen_folders.add(folder_name)
                    folder_path = f"{prefix}{folder_name}"
                    results.append(FolderEntry(path=RemotePath(folder_path), name=folder_name))
            else:
                results.append(self._row_to_file_info(row))
        yield from results

    # endregion

    # region: public methods — metadata

    def get_file_info(self, path: str) -> FileInfo:
        self._validate_path(path)
        cols = self._select_info_columns()
        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table
            row = conn.execute(sa.select(*cols).where(t.c.key == path)).first()
            if row is None:
                raise NotFound(f"File not found: {path}", path=path, backend=self.name)
            return self._row_to_file_info(row)

    def get_folder_info(self, path: str) -> FolderInfo:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        with self._map_errors(path), self._engine.connect() as conn:
            t = self._table

            agg_cols: list[sa.ColumnElement[Any]] = [sa.func.count()]
            if "size" in self._optional_columns:
                agg_cols.append(sa.func.coalesce(sa.func.sum(t.c.size), 0))
            else:
                agg_cols.append(sa.func.coalesce(sa.func.sum(sa.func.length(t.c.data)), 0))

            if "modified_at" in self._optional_columns:
                agg_cols.append(sa.func.max(t.c.modified_at))
            else:
                agg_cols.append(sa.literal(None))

            query = sa.select(*agg_cols).where(t.c.key.like(prefix + "%")) if prefix else sa.select(*agg_cols)

            row = conn.execute(query).first()
            # Aggregate queries (COUNT, SUM, MAX) always return exactly one row,
            # even on an empty table — row is guaranteed non-None.
            if row is None:  # pragma: no cover
                raise RemoteStoreError("Unexpected empty aggregate result", path=path, backend=self.name)

            file_count = row[0]
            total_size = row[1] or 0
            max_modified = row[2]

            if file_count == 0 and path:
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

            modified_at: datetime | None = None
            if max_modified is not None:
                modified_at = datetime.fromtimestamp(max_modified, tz=timezone.utc)

            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=modified_at,
            )

    # endregion

    # region: public methods — move/copy

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._validate_path(src)
        self._validate_path(dst)

        if src == dst:
            # Verify source exists, then no-op
            with self._map_errors(src), self._engine.connect() as conn:
                t = self._table
                if conn.execute(sa.select(sa.literal(1)).where(t.c.key == src)).first() is None:
                    raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            return

        with self._map_errors(src), self._engine.begin() as conn:
            t = self._table
            # Verify source exists
            if conn.execute(sa.select(sa.literal(1)).where(t.c.key == src)).first() is None:
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)

            # Check destination
            dst_exists = conn.execute(sa.select(sa.literal(1)).where(t.c.key == dst)).first() is not None
            if dst_exists and not overwrite:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)

            if dst_exists:
                conn.execute(t.delete().where(t.c.key == dst))

            conn.execute(t.update().where(t.c.key == src).values(key=dst))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        self._validate_path(src)
        self._validate_path(dst)

        now = datetime.now(timezone.utc).timestamp()

        with self._map_errors(src), self._engine.begin() as conn:
            t = self._table

            # Check source exists
            if conn.execute(sa.select(sa.literal(1)).where(t.c.key == src)).first() is None:
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)

            # Check destination
            dst_exists = conn.execute(sa.select(sa.literal(1)).where(t.c.key == dst)).first() is not None
            if dst_exists and not overwrite:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)

            if dst_exists:
                conn.execute(t.delete().where(t.c.key == dst))

            # Single INSERT ... SELECT — no blob data transferred through Python
            col_names: list[str] = ["key", "data"]
            select_cols: list[sa.ColumnElement[Any]] = [sa.literal(dst).label("key"), t.c.data]
            if "size" in self._optional_columns:
                col_names.append("size")
                select_cols.append(t.c.size)
            if "modified_at" in self._optional_columns:
                col_names.append("modified_at")
                select_cols.append(sa.literal(now).label("modified_at"))
            if "content_type" in self._optional_columns:
                col_names.append("content_type")
                select_cols.append(t.c.content_type)
            if "digest" in self._optional_columns:
                col_names.append("digest")
                select_cols.append(t.c.digest)
            if "extra" in self._optional_columns:
                col_names.append("extra")
                select_cols.append(t.c.extra)
            if "user_metadata" in self._optional_columns:
                col_names.append("user_metadata")
                select_cols.append(t.c.user_metadata)

            conn.execute(
                t.insert().from_select(
                    col_names,
                    sa.select(*select_cols).where(t.c.key == src),
                )
            )

    # endregion

    # region: public methods — glob

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        cols = self._select_info_columns()
        rx = pattern_to_regex(pattern)
        with self._map_errors(), self._engine.connect() as conn:
            t = self._table
            query = sa.select(*cols)

            if self._is_sqlite:
                # SQLite GLOB for SQL-side narrowing, then regex to enforce
                # GLOB-014 semantics (* = [^/]*, ? = [^/]).
                query = query.where(t.c.key.op("GLOB")(pattern))
            else:
                # Other dialects: LIKE for SQL-side narrowing.
                like_pattern = self._glob_to_like(pattern)
                if like_pattern is not None:
                    query = query.where(t.c.key.like(like_pattern))

            rows = conn.execute(query).fetchall()
            yield from (self._row_to_file_info(row) for row in rows if rx.match(row[0]))

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        dialect = self._engine.dialect.name
        return f"SQLBlobBackend(dialect={dialect!r}, table={self._table_name!r})"

    # endregion

    # region: private helpers

    def _select_info_columns(self) -> list[sa.ColumnElement[Any]]:
        """Return the columns to select for building FileInfo."""
        t = self._table
        cols: list[sa.ColumnElement[Any]] = [t.c.key]

        if "size" in self._optional_columns:
            cols.append(t.c.size)
        else:
            cols.append(sa.func.length(t.c.data).label("size"))

        if "modified_at" in self._optional_columns:
            cols.append(t.c.modified_at)
        else:
            cols.append(sa.literal(None).label("modified_at"))

        if "content_type" in self._optional_columns:
            cols.append(t.c.content_type)
        if "digest" in self._optional_columns:
            cols.append(t.c.digest)
        if "extra" in self._optional_columns:
            cols.append(t.c.extra)
        if "user_metadata" in self._optional_columns:
            cols.append(t.c.user_metadata)

        return cols

    def _row_to_file_info(self, row: Any) -> FileInfo:
        """Convert a database row to FileInfo."""
        key = row[0]
        size = row[1] or 0
        modified_ts = row[2]
        modified_at = (
            datetime.fromtimestamp(modified_ts, tz=timezone.utc)
            if modified_ts is not None
            else datetime.min.replace(tzinfo=timezone.utc)
        )

        content_type: str | None = None
        digest_obj: ContentDigest | None = None
        extra: dict[str, object] = {}
        user_meta: dict[str, str] | None = None

        idx = 3
        if "content_type" in self._optional_columns:
            content_type = row[idx] if idx < len(row) else None
            idx += 1
        if "digest" in self._optional_columns:
            digest_raw = row[idx] if idx < len(row) else None
            idx += 1
            if digest_raw and ":" in digest_raw:
                algo, val = digest_raw.split(":", 1)
                try:
                    digest_obj = ContentDigest(algorithm=algo, value=val)
                except ValueError:
                    log.warning("Invalid digest %r for key %r", digest_raw, key)
        if "extra" in self._optional_columns:
            extra_raw = row[idx] if idx < len(row) else None
            if extra_raw:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    extra = json.loads(extra_raw)
            idx += 1
        if "user_metadata" in self._optional_columns:
            meta_raw = row[idx] if idx < len(row) else None
            if meta_raw:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    parsed = json.loads(meta_raw)
                    if isinstance(parsed, dict):
                        user_meta = {k: v for k, v in parsed.items() if isinstance(k, str) and isinstance(v, str)}
            idx += 1

        rpath = RemotePath(key)
        return FileInfo(
            path=rpath,
            name=rpath.name,
            size=size,
            modified_at=modified_at,
            content_type=content_type,
            digest=digest_obj,
            extra=extra,
            metadata=user_meta,
        )

    @staticmethod
    def _glob_to_like(pattern: str) -> str | None:
        """Convert a glob pattern to a SQL LIKE pattern.

        Returns ``None`` when the pattern cannot be meaningfully narrowed
        (e.g. a bare ``*``), signalling the caller to skip the WHERE clause.
        """
        like: list[str] = []
        i = 0
        while i < len(pattern):
            ch = pattern[i]
            if ch == "*":
                # Collapse consecutive * (including **)
                while i < len(pattern) and pattern[i] == "*":
                    i += 1
                like.append("%")
            elif ch == "?":
                like.append("_")
                i += 1
            elif ch in ("%", "_"):
                # Escape SQL LIKE metacharacters that appear literally
                like.append("\\" + ch)
                i += 1
            elif ch == "[":
                # Character classes — not convertible to LIKE; use wildcard
                end = pattern.find("]", i + 1)
                if end == -1:
                    like.append(ch)
                else:
                    like.append("_")
                    i = end + 1
                    continue
                i += 1
            else:
                like.append(ch)
                i += 1
        result = "".join(like)
        return None if result == "%" else result

    # endregion


# ---------------------------------------------------------------------------
# SQLQueryBackend
# ---------------------------------------------------------------------------

_SUPPORTED_FORMATS: dict[str, str] = {
    ".parquet": "parquet",
    ".csv": "csv",
    ".arrow": "arrow",
    ".ipc": "arrow",
}

_EPOCH_MIN = datetime.min.replace(tzinfo=timezone.utc)


class SQLQueryBackend(_SQLAlchemyBaseBackend):
    """Read-only SQL query materializer implementing a subset of the Backend contract.

    Maps path keys to SQL queries. On ``read()``, executes the query and
    serializes the result set to the format implied by the key's file
    extension (Parquet, CSV, or Arrow IPC).

    Capabilities: ``READ``, ``LIST``, ``METADATA``, ``GLOB``,
    ``SEEKABLE_READ``.
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        engine: Engine | None = None,
        queries: dict[str, str] | None = None,
        strict: bool = True,
        serializer: ResultSerializer | None = None,
    ) -> None:
        if not strict:
            msg = "View/convention discovery (strict=False) is not yet implemented"
            raise NotImplementedError(msg)

        try:
            import pyarrow  # noqa: F401, PLC0415
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "SQLQueryBackend requires 'pyarrow'. Install with: pip install remote-store[sql-query]"
            ) from exc

        super().__init__(url=url, engine=engine)

        self._queries: dict[str, str] = {}
        if queries:
            for key, sql in queries.items():
                if not key or not key.strip():
                    msg = "Query key must be a non-empty string"
                    raise ValueError(msg)
                if not sql or not sql.strip():
                    msg = f"SQL query for key {key!r} must be a non-empty string"
                    raise ValueError(msg)
                self._queries[key] = sql

        self._strict = strict
        self._serializer: ResultSerializer = serializer or ArrowSerializer()

    # region: properties

    @property
    def name(self) -> str:
        return "sql-query"

    @property
    def capabilities(self) -> CapabilitySet:
        return _QUERY_CAPABILITIES

    # endregion

    # region: interop

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with SQL query details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind="sql-query"`` and ``details`` containing
            ``source`` and ``format``.
        """
        from remote_store._resolution import ResolutionPlan as _RP

        dot_idx = path.rfind(".")
        ext = "" if dot_idx == -1 else path[dot_idx:].lower()
        fmt = _SUPPORTED_FORMATS.get(ext, "unknown")

        return _RP(
            kind="sql-query",
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={
                "source": "explicit",
                "format": fmt,
            },
        )

    # endregion

    # region: key resolution

    def _resolve_key(self, path: str) -> str:
        """Resolve a path to a SQL query string."""
        if path in self._queries:
            return self._queries[path]
        raise NotFound(f"No query registered for key: {path}", path=path, backend=self.name)

    def _detect_format(self, path: str) -> str:
        """Detect serialization format from file extension."""
        dot_idx = path.rfind(".")
        ext = "" if dot_idx == -1 else path[dot_idx:].lower()
        fmt = _SUPPORTED_FORMATS.get(ext)
        if fmt is None:
            supported = ", ".join(sorted(_SUPPORTED_FORMATS.keys()))
            raise InvalidPath(
                f"Unsupported format {ext!r} for key {path!r}. Supported: {supported}",
                path=path,
                backend=self.name,
            )
        return fmt

    # endregion

    # region: public methods — existence

    def exists(self, path: str) -> bool:
        self._validate_path(path, allow_empty=True)
        if not path:
            return True
        # Check file (exact key match)
        if path in self._queries:
            return True
        # Check virtual folder
        prefix = path + "/"
        return any(k.startswith(prefix) for k in self._queries)

    def is_file(self, path: str) -> bool:
        self._validate_path(path, allow_empty=True)
        if not path:
            return False
        return path in self._queries

    def is_folder(self, path: str) -> bool:
        self._validate_path(path, allow_empty=True)
        if not path:
            return True
        prefix = path + "/"
        return any(k.startswith(prefix) for k in self._queries)

    # endregion

    # region: public methods — reading

    def read(self, path: str) -> BinaryIO:
        self._validate_path(path)
        sql = self._resolve_key(path)
        fmt = self._detect_format(path)
        with self._map_errors(path), self._engine.connect() as conn:
            result = conn.execute(sa.text(sql))
            columns = list(result.keys())
            rows = result.fetchall()
        data = self._serializer.serialize(rows, columns, fmt)
        return io.BytesIO(data)

    def read_bytes(self, path: str) -> bytes:
        self._validate_path(path)
        sql = self._resolve_key(path)
        fmt = self._detect_format(path)
        with self._map_errors(path), self._engine.connect() as conn:
            result = conn.execute(sa.text(sql))
            columns = list(result.keys())
            rows = result.fetchall()
        return self._serializer.serialize(rows, columns, fmt)

    # endregion

    # region: public methods — unsupported (read-only backend)

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        raise CapabilityNotSupported("SQL query backend is read-only", capability="write", backend=self.name)

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        raise CapabilityNotSupported("SQL query backend is read-only", capability="atomic_write", backend=self.name)

    def open_atomic(self, path: str, *, overwrite: bool = False) -> contextlib.AbstractContextManager[BinaryIO]:
        raise CapabilityNotSupported("SQL query backend is read-only", capability="atomic_write", backend=self.name)

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        raise CapabilityNotSupported("SQL query backend is read-only", capability="delete", backend=self.name)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        raise CapabilityNotSupported("SQL query backend is read-only", capability="delete", backend=self.name)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        raise CapabilityNotSupported("SQL query backend is read-only", capability="move", backend=self.name)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        raise CapabilityNotSupported("SQL query backend is read-only", capability="copy", backend=self.name)

    # endregion

    # region: public methods — listing

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        for key in sorted(self._queries):
            if prefix and not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]

            if not recursive and max_depth is None:
                if "/" in suffix:
                    continue
            elif max_depth is not None:
                depth = suffix.count("/")
                if depth > max_depth:
                    continue

            yield self._key_to_file_info(key)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        seen: set[str] = set()
        for key in sorted(self._queries):
            if prefix and not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]
            if "/" in suffix:
                folder_name = suffix.split("/", 1)[0]
                if folder_name not in seen:
                    seen.add(folder_name)
                    folder_path = f"{prefix}{folder_name}"
                    yield FolderEntry(path=RemotePath(folder_path), name=folder_name)

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        seen_folders: set[str] = set()
        for key in sorted(self._queries):
            if prefix and not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]
            if "/" in suffix:
                folder_name = suffix.split("/", 1)[0]
                if folder_name not in seen_folders:
                    seen_folders.add(folder_name)
                    folder_path = f"{prefix}{folder_name}"
                    yield FolderEntry(path=RemotePath(folder_path), name=folder_name)
            else:
                yield self._key_to_file_info(key)

    # endregion

    # region: public methods — metadata

    def get_file_info(self, path: str) -> FileInfo:
        self._validate_path(path)
        if path not in self._queries:
            raise NotFound(f"No query registered for key: {path}", path=path, backend=self.name)
        return self._key_to_file_info(path)

    def get_folder_info(self, path: str) -> FolderInfo:
        self._validate_path(path, allow_empty=True)
        prefix = (path + "/") if path else ""

        file_count = 0
        for key in self._queries:
            if not prefix or key.startswith(prefix):
                file_count += 1

        if file_count == 0 and path:
            raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

        return FolderInfo(
            path=RemotePath.from_backend_path(path) if path and path != "." else RemotePath.ROOT,
            file_count=file_count,
            total_size=0,
            modified_at=None,
        )

    # endregion

    # region: public methods — glob

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        rx = pattern_to_regex(pattern)
        for key in sorted(self._queries):
            if rx.match(key):
                yield self._key_to_file_info(key)

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        dialect = self._engine.dialect.name
        return f"SQLQueryBackend(dialect={dialect!r}, keys={len(self._queries)}, strict={self._strict!r})"

    # endregion

    # region: private helpers

    @staticmethod
    def _key_to_file_info(key: str) -> FileInfo:
        """Build a FileInfo for a registered key (sentinel metadata)."""
        rpath = RemotePath(key)
        return FileInfo(
            path=rpath,
            name=rpath.name,
            size=0,
            modified_at=_EPOCH_MIN,
            extra={"materialized": False},
        )

    # endregion
