"""Tests for SQLBlobBackend — SQL key-value blob storage."""

from __future__ import annotations

import io
import pathlib
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

import pytest
import sqlalchemy as sa

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from remote_store._models import WriteResult
from remote_store.backends._sqlalchemy import SQLBlobBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend() -> Iterator[SQLBlobBackend]:
    """Fresh SQLite backend for each test, engine disposed on teardown."""
    b = SQLBlobBackend(url="sqlite:///:memory:")
    yield b
    b.close()


@pytest.fixture
def populated(backend: SQLBlobBackend) -> SQLBlobBackend:
    """Backend with some test data."""
    backend.write("a/1.txt", b"one")
    backend.write("a/2.txt", b"two")
    backend.write("a/b/deep.txt", b"deep")
    backend.write("c/3.txt", b"three")
    return backend


@pytest.fixture
def minimal_engine() -> Iterator[sa.Engine]:
    """Engine with a minimal (key, data) table — no optional columns."""
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "minimal",
        metadata,
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("data", sa.LargeBinary, nullable=False),
    )
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def mtime_engine() -> Iterator[sa.Engine]:
    """Engine with a (key, data, modified_at) table — mtime present, no user_metadata."""
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "mtime_only",
        metadata,
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("modified_at", sa.Float, nullable=False),
    )
    metadata.create_all(engine)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_raw(backend: SQLBlobBackend, key: str, **cols: object) -> None:
    """Insert a row directly via SQL, bypassing backend.write()."""
    with backend._engine.begin() as conn:
        conn.execute(backend._table.insert().values(key=key, **cols))


# ---------------------------------------------------------------------------
# Construction & properties
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-001")
class TestConstruction:
    def test_url_creates_backend(self) -> None:
        b = SQLBlobBackend(url="sqlite:///:memory:")
        assert b.name == "sql-blob"
        b.close()

    def test_engine_creates_backend(self) -> None:
        engine = sa.create_engine("sqlite:///:memory:")
        b = SQLBlobBackend(engine=engine)
        assert b.name == "sql-blob"
        b.close()
        engine.dispose()

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"url": "sqlite:///:memory:", "table_name": ""}, "table_name"),
            ({"url": "sqlite:///:memory:", "max_blob_size": 0}, "max_blob_size"),
            ({"url": "sqlite:///:memory:", "max_blob_size": -1}, "max_blob_size"),
            ({}, "Exactly one"),
        ],
        ids=["empty_table_name", "zero_blob_size", "negative_blob_size", "no_url_no_engine"],
    )
    def test_construction_invalid(self, kwargs: dict[str, object], match: str) -> None:
        with pytest.raises(ValueError, match=match):
            SQLBlobBackend(**kwargs)  # type: ignore[arg-type]

    def test_both_url_and_engine_raises(self) -> None:
        engine = sa.create_engine("sqlite:///:memory:")
        with pytest.raises(ValueError, match="Exactly one"):
            SQLBlobBackend(url="sqlite:///:memory:", engine=engine)
        engine.dispose()

    def test_custom_table_name(self) -> None:
        b = SQLBlobBackend(url="sqlite:///:memory:", table_name="my_table")
        assert "my_table" in repr(b)
        b.close()


@pytest.mark.spec("SQL-BLOB-002")
def test_name(backend: SQLBlobBackend) -> None:
    assert backend.name == "sql-blob"


@pytest.mark.spec("SQL-BLOB-003")
def test_capabilities(backend: SQLBlobBackend) -> None:
    caps = backend.capabilities
    for cap in Capability:
        if cap is Capability.LAZY_READ:
            assert cap not in caps, "SQLBlob pre-loads blobs into memory — must NOT declare LAZY_READ"
        else:
            assert cap in caps, f"Missing capability: {cap}"
    # Explicit assertion: SQLBlob move() runs inside a transaction — atomic.
    assert Capability.ATOMIC_MOVE in caps, "SQLBlob must declare ATOMIC_MOVE (transactional move)"


@pytest.mark.spec("SQL-BLOB-004")
def test_repr(backend: SQLBlobBackend) -> None:
    r = repr(backend)
    assert "SQLBlobBackend" in r
    assert "sqlite" in r
    assert "remote_store_objects" in r


# ---------------------------------------------------------------------------
# Existing table (create_table=False)
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-012")
class TestExistingTable:
    def test_create_table_false_with_full_schema(self) -> None:
        engine = sa.create_engine("sqlite:///:memory:")
        metadata = sa.MetaData()
        sa.Table(
            "custom",
            metadata,
            sa.Column("key", sa.Text, primary_key=True),
            sa.Column("data", sa.LargeBinary, nullable=False),
            sa.Column("size", sa.Integer, nullable=False),
            sa.Column("modified_at", sa.Float, nullable=False),
            sa.Column("content_type", sa.Text),
        )
        metadata.create_all(engine)
        b = SQLBlobBackend(engine=engine, table_name="custom", create_table=False)
        b.write("test.txt", b"hello")
        assert b.read_bytes("test.txt") == b"hello"
        b.close()
        engine.dispose()

    def test_create_table_false_minimal_schema(self, minimal_engine: sa.Engine) -> None:
        b = SQLBlobBackend(engine=minimal_engine, table_name="minimal", create_table=False)
        b.write("test.txt", b"hello")
        assert b.read_bytes("test.txt") == b"hello"
        b.close()

    def test_create_table_false_minimal_modified_at_fallback(self, minimal_engine: sa.Engine) -> None:
        """SQL-BLOB-012: missing modified_at -> datetime.min."""
        from datetime import datetime, timezone

        b = SQLBlobBackend(engine=minimal_engine, table_name="minimal", create_table=False)
        b.write("test.txt", b"hello")
        info = b.get_file_info("test.txt")
        assert info.modified_at == datetime.min.replace(tzinfo=timezone.utc)
        b.close()

    def test_create_table_false_missing_columns_raises(self) -> None:
        engine = sa.create_engine("sqlite:///:memory:")
        metadata = sa.MetaData()
        sa.Table(
            "bad",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("content", sa.LargeBinary),
        )
        metadata.create_all(engine)
        with pytest.raises(ValueError, match="'key' and 'data'"):
            SQLBlobBackend(engine=engine, table_name="bad", create_table=False)
        engine.dispose()


# ---------------------------------------------------------------------------
# Read/Write operations
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-020")
def test_read_returns_seekable_stream(backend: SQLBlobBackend) -> None:
    """SQL-BLOB-020: SQLBlob returns a seekable BytesIO; generic readable-stream
    contract is covered by the conformance suite (BE-006, SIO-001).
    """
    backend.write("f.txt", b"data")
    stream = backend.read("f.txt")
    assert stream.seekable()
    assert stream.read() == b"data"
    stream.close()


@pytest.mark.spec("SQL-BLOB-022")
def test_write_max_blob_size() -> None:
    b = SQLBlobBackend(url="sqlite:///:memory:", max_blob_size=10)
    try:
        with pytest.raises(ValueError, match="max_blob_size"):
            b.write("f.txt", b"x" * 11)
        # Under limit should work
        b.write("f.txt", b"x" * 10)
    finally:
        b.close()


# ---------------------------------------------------------------------------
# Delete operations
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-025")
def test_delete_folder_not_recursive_raises(populated: SQLBlobBackend) -> None:
    """SQL-BLOB-025: flat-namespace delete_folder raises DirectoryNotEmpty when non-recursive.
    The extended conformance suite skips this check for flat-namespace backends.
    Generic delete/missing_ok/recursive are covered by the conformance suite (BE-012, BE-013).
    """
    with pytest.raises(DirectoryNotEmpty):
        populated.delete_folder("a")


# ---------------------------------------------------------------------------
# Existence checks
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-026")
class TestExistence:
    """Root-path existence checks for SQLBlob flat namespace.
    File, folder, and missing-path checks are covered by the conformance suite (BE-004, BE-005).
    """

    def test_exists_root(self, populated: SQLBlobBackend) -> None:
        assert populated.exists("")

    def test_is_file_root(self, backend: SQLBlobBackend) -> None:
        assert not backend.is_file("")

    def test_is_folder_root(self, backend: SQLBlobBackend) -> None:
        assert backend.is_folder("")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-027")
class TestListFiles:
    """Root-path listing for SQLBlob flat namespace.
    Non-recursive, recursive, and max_depth listing are covered by the conformance
    suite (BE-014) and extended conformance.
    """

    def test_list_files_root(self, populated: SQLBlobBackend) -> None:
        files = list(populated.list_files("", recursive=True))
        assert len(files) == 4

    def test_list_files_empty_folder(self, backend: SQLBlobBackend) -> None:
        files = list(backend.list_files(""))
        assert files == []


@pytest.mark.spec("SQL-BLOB-028")
class TestListFolders:
    """Root-path and leaf-folder listing for SQLBlob flat namespace.
    Nested subfolder listing is covered by the conformance suite (BE-015).
    """

    def test_list_folders(self, populated: SQLBlobBackend) -> None:
        folders = list(populated.list_folders(""))
        names = {f.name for f in folders}
        assert names == {"a", "c"}

    def test_list_folders_no_subfolders(self, populated: SQLBlobBackend) -> None:
        folders = list(populated.list_folders("c"))
        assert folders == []


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-029")
class TestGetFileInfo:
    """SQL-specific file info checks (path as string, timezone-aware modified_at).
    NotFound / InvalidPath error fidelity is covered by the conformance suite (BE-016).
    """

    def test_basic(self, populated: SQLBlobBackend) -> None:
        info = populated.get_file_info("a/1.txt")
        assert info.name == "1.txt"
        assert info.size == 3  # len(b"one")
        assert str(info.path) == "a/1.txt"
        assert info.modified_at.tzinfo is not None


@pytest.mark.spec("SQL-BLOB-030")
class TestGetFolderInfo:
    """SQL-specific folder info checks (modified_at present, root-path aggregates).
    NotFound / InvalidPath error fidelity is covered by the conformance suite (BE-017).
    """

    def test_basic(self, populated: SQLBlobBackend) -> None:
        info = populated.get_folder_info("a")
        assert info.file_count == 3  # 1.txt, 2.txt, b/deep.txt
        assert info.total_size == 3 + 3 + 4  # one + two + deep
        assert info.modified_at is not None

    def test_root(self, populated: SQLBlobBackend) -> None:
        info = populated.get_folder_info("")
        assert info.file_count == 4


# ---------------------------------------------------------------------------
# Glob
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-033")
class TestGlob:
    def test_star(self, populated: SQLBlobBackend) -> None:
        files = list(populated.glob("a/*.txt"))
        names = {f.name for f in files}
        # GLOB-014: * matches [^/]* — direct children only
        assert names == {"1.txt", "2.txt"}

    def test_double_star(self, populated: SQLBlobBackend) -> None:
        files = list(populated.glob("a/**"))
        names = {f.name for f in files}
        assert "1.txt" in names
        assert "deep.txt" in names

    def test_question_mark(self, populated: SQLBlobBackend) -> None:
        files = list(populated.glob("a/?.txt"))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt"}

    def test_no_match(self, populated: SQLBlobBackend) -> None:
        files = list(populated.glob("z/*.nope"))
        assert files == []

    def test_glob_sql_side_filtering(self, populated: SQLBlobBackend) -> None:
        """Verify SQL-side filtering returns correct results for various patterns."""
        # Exact prefix with wildcard
        files = list(populated.glob("c/*"))
        assert {f.name for f in files} == {"3.txt"}

        # Deep recursive pattern
        files = list(populated.glob("a/b/*"))
        assert {f.name for f in files} == {"deep.txt"}

        # Pattern that matches nothing
        files = list(populated.glob("nonexistent/*"))
        assert files == []


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-040")
def test_check_health(backend: SQLBlobBackend) -> None:
    result = backend.check_health()
    assert result is None


@pytest.mark.spec("SQL-BLOB-041")
def test_close_owned_engine() -> None:
    # SQL-BLOB-041: close() on an owned engine calls Engine.dispose(), which
    # swaps the connection pool with a fresh one. Probing post-close behaviour
    # via an I/O call would silently re-open a connection on the disposed
    # engine and leak it (ResourceWarning), so assert pool identity instead
    # via the publicly-unwrapped Engine handle.
    b = SQLBlobBackend(url="sqlite:///:memory:")
    b.write("f.txt", b"data")
    engine = b.unwrap(sa.Engine)
    pool_before = engine.pool
    b.close()
    assert engine.pool is not pool_before


@pytest.mark.spec("SQL-BLOB-041")
def test_close_borrowed_engine_noop() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    b = SQLBlobBackend(engine=engine)
    b.write("f.txt", b"data")
    result = b.close()
    assert result is None
    # Engine still usable since it's borrowed
    with engine.connect() as conn:
        conn.execute(sa.text("SELECT 1"))
    engine.dispose()


@pytest.mark.spec("SQL-BLOB-042")
def test_unwrap_engine(backend: SQLBlobBackend) -> None:
    engine = backend.unwrap(sa.Engine)
    assert isinstance(engine, sa.Engine)
    with engine.connect() as conn:
        conn.execute(sa.text("SELECT 1"))


@pytest.mark.spec("SQL-BLOB-042")
def test_unwrap_wrong_type(backend: SQLBlobBackend) -> None:
    from remote_store._errors import CapabilityNotSupported

    with pytest.raises(CapabilityNotSupported):
        backend.unwrap(str)


@pytest.mark.spec("SQL-BLOB-043")
def test_sqlite_wal_mode(tmp_path: object) -> None:
    db_path = pathlib.Path(str(tmp_path)) / "test.db"
    b = SQLBlobBackend(url=f"sqlite:///{db_path}")
    engine = b.unwrap(type(b._engine))
    with engine.connect() as conn:
        result = conn.execute(sa.text("PRAGMA journal_mode")).scalar()  # type: ignore[attr-defined]
        assert result == "wal"
    b.close()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-005")
def test_registration() -> None:
    """sql-blob is registered in the backend registry."""
    from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

    _register_builtin_backends()
    assert _BACKEND_FACTORIES.get("sql-blob") is SQLBlobBackend


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-010")
def test_default_schema(backend: SQLBlobBackend) -> None:
    """Default table has all expected columns."""
    col_names = {c.name for c in backend._table.columns}
    assert col_names == {"key", "data", "size", "modified_at", "content_type", "digest", "extra", "user_metadata"}


# ---------------------------------------------------------------------------
# Move — same-path edge case (no conformance equivalent)
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-031")
def test_move_same_path_missing_source(backend: SQLBlobBackend) -> None:
    """move(missing, missing) raises NotFound — not a no-op."""
    with pytest.raises(NotFound):
        backend.move("missing.txt", "missing.txt")


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-050")
class TestErrorMapping:
    def test_integrity_error_raises_already_exists(self, backend: SQLBlobBackend) -> None:
        backend.write("dup.txt", b"first")
        with pytest.raises(AlreadyExists):
            backend.write("dup.txt", b"second")

    def test_not_found_on_missing_read(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(NotFound):
            backend.read_bytes("missing.txt")

    def test_not_found_on_missing_delete(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(NotFound):
            backend.delete("missing.txt")


# ---------------------------------------------------------------------------
# Prefix matching
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-061")
def test_prefix_matching_no_false_positives(backend: SQLBlobBackend) -> None:
    """Prefix 'data/' must not match 'dataset/file.txt'."""
    backend.write("data/file.txt", b"yes")
    backend.write("dataset/file.txt", b"no")
    files = list(backend.list_files("data"))
    assert {f.name for f in files} == {"file.txt"}
    assert not backend.is_folder("dat")


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-060")
class TestPathValidation:
    def test_null_byte(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(InvalidPath, match="null byte"):
            backend.read("a\0b")

    def test_absolute_path(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(InvalidPath, match="Absolute"):
            backend.read("/root/file")

    def test_dotdot(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(InvalidPath, match="\\.\\."):
            backend.read("a/../secret")

    def test_empty_path_for_file_op(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(InvalidPath, match="must not be empty"):
            backend.read("")

    def test_empty_path_for_folder_op(self, backend: SQLBlobBackend) -> None:
        # Should NOT raise — empty path = root for folder ops
        result = backend.is_folder("")
        assert result is True


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_writes(tmp_path: object) -> None:
    """Multiple threads writing different keys concurrently."""
    db_path = pathlib.Path(str(tmp_path)) / "concurrent.db"
    b = SQLBlobBackend(url=f"sqlite:///{db_path}")
    engine = b.unwrap(type(b._engine))
    with engine.connect() as conn:
        assert conn.execute(sa.text("PRAGMA journal_mode")).scalar() == "wal"
    errors: list[Exception] = []

    def writer(i: int) -> None:
        try:
            b.write(f"file_{i}.txt", f"data_{i}".encode())
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    for i in range(20):
        assert b.read_bytes(f"file_{i}.txt") == f"data_{i}".encode()
    b.close()


# ---------------------------------------------------------------------------
# Coverage: optional columns, digest, extra, glob_to_like
# ---------------------------------------------------------------------------


class TestOptionalColumns:
    """Test metadata handling with optional columns (content_type, digest, extra)."""

    def test_write_with_metadata_columns(self, backend: SQLBlobBackend) -> None:
        """Direct SQL insert with content_type, digest, extra to exercise _row_to_file_info."""
        _insert_raw(
            backend,
            "meta.txt",
            data=b"hello",
            size=5,
            modified_at=1000000.0,
            content_type="text/plain",
            digest="sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            extra='{"custom": "value"}',
        )
        info = backend.get_file_info("meta.txt")
        assert info.content_type == "text/plain"
        assert info.digest is not None
        assert info.digest.algorithm == "sha256"
        assert info.extra == {"custom": "value"}

    def test_invalid_digest_format(self, backend: SQLBlobBackend) -> None:
        """Invalid digest hex → digest is None (warning logged)."""
        _insert_raw(
            backend,
            "bad_digest.txt",
            data=b"data",
            size=4,
            modified_at=1000000.0,
            digest="not-a-valid:!!!",
        )
        info = backend.get_file_info("bad_digest.txt")
        assert info.digest is None

    def test_invalid_extra_json(self, backend: SQLBlobBackend) -> None:
        """Malformed JSON in extra column is silently ignored."""
        _insert_raw(
            backend,
            "bad_extra.txt",
            data=b"data",
            size=4,
            modified_at=1000000.0,
            extra="not valid json{{{",
        )
        info = backend.get_file_info("bad_extra.txt")
        assert info.extra == {}


class TestMinimalSchemaFolderInfo:
    """Test get_folder_info on minimal schema (no size, no modified_at columns)."""

    def test_folder_info_minimal_schema(self, minimal_engine: sa.Engine) -> None:
        b = SQLBlobBackend(engine=minimal_engine, table_name="minimal", create_table=False)
        b.write("a/1.txt", b"one")
        b.write("a/2.txt", b"two")
        info = b.get_folder_info("a")
        assert info.file_count == 2
        assert info.total_size >= 0  # computed from length(data)
        assert info.modified_at is None
        b.close()


class TestGlobToLike:
    """Unit tests for the _glob_to_like static method."""

    @pytest.mark.parametrize(
        ("pattern", "expected"),
        [
            ("data/*.txt", "data/%.txt"),
            ("file?.txt", "file_.txt"),
            ("**/*.txt", "%/%.txt"),
            ("*", None),
            ("100%.txt", "100\\%.txt"),
            ("file_name.txt", "file\\_name.txt"),
            ("file[abc].txt", "file_.txt"),
            ("path/to/file.txt", "path/to/file.txt"),
        ],
        ids=[
            "simple_star",
            "question_mark",
            "double_star",
            "bare_star_none",
            "escape_percent",
            "escape_underscore",
            "char_class",
            "literal_chars",
        ],
    )
    def test_glob_to_like(self, pattern: str, expected: str | None) -> None:
        assert SQLBlobBackend._glob_to_like(pattern) == expected

    def test_unclosed_bracket(self) -> None:
        result = SQLBlobBackend._glob_to_like("file[abc.txt")
        assert "[" in result


class TestHealthCheckFailure:
    """Test check_health when the database is unreachable."""

    def test_check_health_failure(self) -> None:
        from unittest.mock import patch

        from remote_store._errors import BackendUnavailable

        b = SQLBlobBackend(url="sqlite:///:memory:")
        with (
            patch.object(b._engine, "connect", side_effect=sa.exc.SQLAlchemyError("mock failure")),
            pytest.raises(BackendUnavailable, match="health check failed"),
        ):
            b.check_health()
        b.close()


class TestSQLBlobResolve:
    """RES-057: SQLBlobBackend.resolve() returns kind='sql-blob' with table_name."""

    @pytest.mark.spec("RES-057")
    def test_kind_is_sql_blob(self, backend: SQLBlobBackend) -> None:
        plan = backend.resolve("file.txt")
        assert plan.kind == "sql-blob"

    @pytest.mark.spec("RES-057")
    def test_details_has_table_name(self, backend: SQLBlobBackend) -> None:
        plan = backend.resolve("file.txt")
        assert "table_name" in plan.details
        assert isinstance(plan.details["table_name"], str)


# ---------------------------------------------------------------------------
# WriteResult (WR-001, WR-003, WR-004, WR-012, WR-013)
# ---------------------------------------------------------------------------


class TestSQLBlobWriteResult:
    """SQLBlobBackend.write/write_atomic return a valid WriteResult (source='native')."""

    @pytest.mark.spec("WR-001")
    @pytest.mark.spec("WR-004")
    def test_write_returns_write_result(self, backend: SQLBlobBackend) -> None:
        from remote_store._path import RemotePath

        result = backend.write("f.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.path == RemotePath("f.txt")
        assert result.size == 5

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"hello world", 11), (b"", 0)])
    def test_write_size_bytes(self, backend: SQLBlobBackend, payload: bytes, expected_size: int) -> None:
        result = backend.write("f.txt", payload)
        assert result.size == expected_size

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"streamed", 8), (b"", 0)])
    def test_write_size_binaryio(self, backend: SQLBlobBackend, payload: bytes, expected_size: int) -> None:
        result = backend.write("f.txt", io.BytesIO(payload))
        assert result.size == expected_size

    @pytest.mark.spec("WR-001")
    def test_write_atomic_returns_write_result(self, backend: SQLBlobBackend) -> None:
        from remote_store._path import RemotePath

        result = backend.write_atomic("f.txt", b"data")
        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.path == RemotePath("f.txt")
        assert result.size == 4

    @pytest.mark.spec("WR-012")
    def test_write_metadata_echoed(self, backend: SQLBlobBackend) -> None:
        result = backend.write("f.txt", b"x", metadata={"k": "v"})
        assert result.metadata == {"k": "v"}

    @pytest.mark.spec("WR-013")
    def test_write_metadata_survives_roundtrip(self, backend: SQLBlobBackend) -> None:
        backend.write("f.txt", b"x", metadata={"k": "v"})
        info = backend.get_file_info("f.txt")
        assert info.metadata == {"k": "v"}

    @pytest.mark.spec("WR-013")
    def test_legacy_schema_without_user_metadata_column_does_not_advertise_user_metadata(
        self, minimal_engine: sa.Engine
    ) -> None:
        """A table with neither modified_at nor user_metadata must not declare USER_METADATA or WRITE_RESULT_NATIVE."""
        b = SQLBlobBackend(engine=minimal_engine, table_name="minimal", create_table=False)
        assert not b.capabilities.supports(Capability.USER_METADATA)
        assert not b.capabilities.supports(Capability.WRITE_RESULT_NATIVE)
        b.close()

    @pytest.mark.spec("WR-013")
    def test_legacy_schema_write_without_metadata_succeeds(self, minimal_engine: sa.Engine) -> None:
        """Write without metadata works fine on a legacy schema; source is basic."""
        b = SQLBlobBackend(engine=minimal_engine, table_name="minimal", create_table=False)
        result = b.write("f.txt", b"data")
        assert isinstance(result, WriteResult)
        assert result.source == "basic"
        assert result.metadata is None
        b.close()

    @pytest.mark.spec("WR-013")
    def test_copy_preserves_user_metadata(self, backend: SQLBlobBackend) -> None:
        """copy() preserves user_metadata on backends that declare USER_METADATA."""
        backend.write("src.txt", b"data", metadata={"env": "test"})
        backend.copy("src.txt", "dst.txt")
        info = backend.get_file_info("dst.txt")
        assert info.metadata == {"env": "test"}


class TestMtimeOnlySchema:
    """SQLBlobBackend with (key, data, modified_at) — no user_metadata column.

    WRITE_RESULT_NATIVE must be declared (modified_at present), USER_METADATA
    must not be declared (user_metadata absent), and write() must return
    source='native' with a populated last_modified.
    """

    @pytest.mark.spec("WR-004")
    @pytest.mark.spec("WR-013")
    def test_declares_write_result_native_but_not_user_metadata(self, mtime_engine: sa.Engine) -> None:
        b = SQLBlobBackend(engine=mtime_engine, table_name="mtime_only", create_table=False)
        assert b.capabilities.supports(Capability.WRITE_RESULT_NATIVE)
        assert not b.capabilities.supports(Capability.USER_METADATA)
        b.close()

    @pytest.mark.spec("WR-004")
    @pytest.mark.spec("WR-013")
    def test_write_returns_native_source_and_last_modified(self, mtime_engine: sa.Engine) -> None:
        b = SQLBlobBackend(engine=mtime_engine, table_name="mtime_only", create_table=False)
        result = b.write("f.txt", b"payload")
        assert result.source == "native"
        assert result.last_modified is not None
        assert result.metadata is None
        b.close()
