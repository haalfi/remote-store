"""SQLAlchemy blob backend — key-value store in any SQL database."""

from __future__ import annotations

import abc
import contextlib
import fnmatch
import io
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar, cast

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

try:
    import sqlalchemy as sa
    from sqlalchemy import Engine, event
except ImportError as _imp_err:  # pragma: no cover
    raise ImportError(
        "SQLBlobBackend requires the 'sqlalchemy' package. Install it with: pip install remote-store[sql]"
    ) from _imp_err

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability))

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
            return cast("T", self._engine)
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


# ---------------------------------------------------------------------------
# SQLBlobBackend
# ---------------------------------------------------------------------------


class SQLBlobBackend(_SQLAlchemyBaseBackend):
    """SQL key-value blob store implementing the full Backend contract.

    Uses a SQL table as key-value storage. Each row holds one "file"
    with its key, data, and metadata. SQLite receives WAL mode and
    PRAGMA tuning automatically.

    All 10 capabilities are supported.
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
            )
            self._metadata.create_all(self._engine)
            self._optional_columns = {"size", "modified_at", "content_type", "digest", "extra"}
        else:
            self._table = sa.Table(table_name, self._metadata, autoload_with=self._engine)
            col_names = {c.name for c in self._table.columns}
            if "key" not in col_names or "data" not in col_names:
                msg = f"Table '{table_name}' must have at least 'key' and 'data' columns"
                raise ValueError(msg)
            self._optional_columns = col_names & {"size", "modified_at", "content_type", "digest", "extra"}

    # region: properties

    @property
    def name(self) -> str:
        return "sql-blob"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

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
        return io.BufferedReader(cast("io.RawIOBase", io.BytesIO(data)))

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

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        self._validate_path(path)
        raw = content if isinstance(content, bytes) else content.read()

        if self._max_blob_size is not None and len(raw) > self._max_blob_size:
            msg = f"Content size ({len(raw)} bytes) exceeds max_blob_size ({self._max_blob_size} bytes)"
            raise ValueError(msg)

        now = datetime.now(timezone.utc).timestamp()

        with self._map_errors(path), self._engine.begin() as conn:
            t = self._table
            existing = conn.execute(sa.select(sa.literal(1)).where(t.c.key == path)).first()

            values: dict[str, Any] = {"data": raw}
            if "size" in self._optional_columns:
                values["size"] = len(raw)
            if "modified_at" in self._optional_columns:
                values["modified_at"] = now

            if existing is not None:
                if not overwrite:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                conn.execute(t.update().where(t.c.key == path).values(**values))
            else:
                values["key"] = path
                conn.execute(t.insert().values(**values))

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        self.write(path, content, overwrite=overwrite)

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
            assert row is not None

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
        with self._map_errors(), self._engine.connect() as conn:
            t = self._table
            query = sa.select(*cols)

            if self._is_sqlite:
                # SQLite supports native GLOB (case-sensitive, * = any, ? = single)
                query = query.where(t.c.key.op("GLOB")(pattern))
                rows = conn.execute(query).fetchall()
                yield from (self._row_to_file_info(row) for row in rows)
            else:
                # Other dialects: convert glob to LIKE for SQL-side filtering,
                # then refine with fnmatch in Python for edge cases.
                like_pattern = self._glob_to_like(pattern)
                if like_pattern is not None:
                    query = query.where(t.c.key.like(like_pattern))
                rows = conn.execute(query).fetchall()
                yield from (self._row_to_file_info(row) for row in rows if fnmatch.fnmatch(row[0], pattern))

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        dialect = self._engine.dialect.name
        return f"SQLBlobBackend(dialect={dialect!r}, table={self._table_name!r})"

    # endregion

    # region: private helpers

    @staticmethod
    def _validate_path(path: str, *, allow_empty: bool = False) -> list[str]:
        """Validate and split a path. Returns segments."""
        if "\0" in path:
            raise InvalidPath("Path contains null byte", path=path, backend="sql-blob")
        if path.startswith("/"):
            raise InvalidPath("Absolute paths are not allowed", path=path, backend="sql-blob")

        segments: list[str] = []
        for seg in path.split("/"):
            if seg == "" or seg == ".":
                continue
            if seg == "..":
                raise InvalidPath("Path contains '..' segment", path=path, backend="sql-blob")
            segments.append(seg)

        if not segments and not allow_empty:
            raise InvalidPath("Path must not be empty for file operations", path=path, backend="sql-blob")

        return segments

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

        idx = 3
        if "content_type" in self._optional_columns:
            content_type = row[idx] if idx < len(row) else None
            idx += 1
        if "digest" in self._optional_columns:
            digest_raw = row[idx] if idx < len(row) else None
            idx += 1
            if digest_raw and ":" in digest_raw:
                algo, val = digest_raw.split(":", 1)
                with contextlib.suppress(ValueError):
                    digest_obj = ContentDigest(algorithm=algo, value=val)
        if "extra" in self._optional_columns:
            extra_raw = row[idx] if idx < len(row) else None
            if extra_raw:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    extra = json.loads(extra_raw)

        rpath = RemotePath(key)
        return FileInfo(
            path=rpath,
            name=rpath.name,
            size=size,
            modified_at=modified_at,
            content_type=content_type,
            digest=digest_obj,
            extra=extra,
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

    def _row_field(self, row: Any, field_name: str) -> Any:
        """Extract a field value from an info row by column position."""
        # Columns are: key, size, modified_at, [content_type], [digest], [extra]
        idx = 3
        for col_name in ("content_type", "digest", "extra"):
            if col_name in self._optional_columns:
                if col_name == field_name:
                    return row[idx] if idx < len(row) else None
                idx += 1
        return None

    # endregion
