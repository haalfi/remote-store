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
    RemoteStoreError,
)
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
    backend.write("f.txt", b"data")
    stream = backend.read("f.txt")
    assert stream.seekable()
    assert stream.read() == b"data"
    stream.close()


@pytest.mark.spec("SQL-BLOB-021")
def test_read_bytes_roundtrip(backend: SQLBlobBackend) -> None:
    backend.write("f.txt", b"hello world")
    assert backend.read_bytes("f.txt") == b"hello world"


@pytest.mark.spec("SQL-BLOB-021")
def test_read_bytes_not_found(backend: SQLBlobBackend) -> None:
    with pytest.raises(NotFound):
        backend.read_bytes("missing.txt")


@pytest.mark.spec("SQL-BLOB-020")
def test_read_not_found(backend: SQLBlobBackend) -> None:
    with pytest.raises(NotFound):
        backend.read("missing.txt")


@pytest.mark.spec("SQL-BLOB-022")
def test_write_new_file(backend: SQLBlobBackend) -> None:
    backend.write("new.txt", b"content")
    assert backend.read_bytes("new.txt") == b"content"


@pytest.mark.spec("SQL-BLOB-022")
def test_write_overwrite_false_raises(backend: SQLBlobBackend) -> None:
    backend.write("f.txt", b"first")
    with pytest.raises(AlreadyExists):
        backend.write("f.txt", b"second")


@pytest.mark.spec("SQL-BLOB-022")
def test_write_overwrite_true(backend: SQLBlobBackend) -> None:
    backend.write("f.txt", b"first")
    backend.write("f.txt", b"second", overwrite=True)
    assert backend.read_bytes("f.txt") == b"second"


@pytest.mark.spec("SQL-BLOB-022")
def test_write_binaryio(backend: SQLBlobBackend) -> None:
    backend.write("f.txt", io.BytesIO(b"stream data"))
    assert backend.read_bytes("f.txt") == b"stream data"


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
# Atomic writes
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-023")
def test_write_atomic(backend: SQLBlobBackend) -> None:
    backend.write_atomic("f.txt", b"atomic content")
    assert backend.read_bytes("f.txt") == b"atomic content"


@pytest.mark.spec("SQL-BLOB-023")
def test_write_atomic_overwrite(backend: SQLBlobBackend) -> None:
    backend.write_atomic("f.txt", b"first")
    backend.write_atomic("f.txt", b"second", overwrite=True)
    assert backend.read_bytes("f.txt") == b"second"


@pytest.mark.spec("SQL-BLOB-023")
def test_open_atomic_success(backend: SQLBlobBackend) -> None:
    with backend.open_atomic("f.txt") as f:
        f.write(b"buffered")
    assert backend.read_bytes("f.txt") == b"buffered"


@pytest.mark.spec("SQL-BLOB-023")
def test_open_atomic_exception_discards(backend: SQLBlobBackend) -> None:
    with pytest.raises(RuntimeError, match="abort"), backend.open_atomic("f.txt") as f:  # noqa: PT012
        f.write(b"partial")
        raise RuntimeError("abort")
    assert not backend.exists("f.txt")


@pytest.mark.spec("SQL-BLOB-023")
def test_open_atomic_already_exists(backend: SQLBlobBackend) -> None:
    backend.write("f.txt", b"existing")
    with pytest.raises(AlreadyExists), backend.open_atomic("f.txt") as f:
        f.write(b"new")


# ---------------------------------------------------------------------------
# Delete operations
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-024")
def test_delete(backend: SQLBlobBackend) -> None:
    backend.write("f.txt", b"data")
    backend.delete("f.txt")
    assert not backend.exists("f.txt")


@pytest.mark.spec("SQL-BLOB-024")
def test_delete_not_found(backend: SQLBlobBackend) -> None:
    with pytest.raises(NotFound):
        backend.delete("missing.txt")


@pytest.mark.spec("SQL-BLOB-024")
def test_delete_missing_ok(backend: SQLBlobBackend) -> None:
    result = backend.delete("missing.txt", missing_ok=True)
    assert result is None


@pytest.mark.spec("SQL-BLOB-025")
def test_delete_folder_recursive(populated: SQLBlobBackend) -> None:
    populated.delete_folder("a", recursive=True)
    assert not populated.exists("a/1.txt")
    assert not populated.exists("a/b/deep.txt")
    assert populated.exists("c/3.txt")  # Untouched


@pytest.mark.spec("SQL-BLOB-025")
def test_delete_folder_not_recursive_raises(populated: SQLBlobBackend) -> None:
    with pytest.raises(DirectoryNotEmpty):
        populated.delete_folder("a")


@pytest.mark.spec("SQL-BLOB-025")
def test_delete_folder_not_found(backend: SQLBlobBackend) -> None:
    with pytest.raises(NotFound):
        backend.delete_folder("nonexistent")


@pytest.mark.spec("SQL-BLOB-025")
def test_delete_folder_missing_ok(backend: SQLBlobBackend) -> None:
    result = backend.delete_folder("nonexistent", missing_ok=True)
    assert result is None


# ---------------------------------------------------------------------------
# Existence checks
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-026")
class TestExistence:
    def test_exists_file(self, populated: SQLBlobBackend) -> None:
        assert populated.exists("a/1.txt")

    def test_exists_folder(self, populated: SQLBlobBackend) -> None:
        assert populated.exists("a")

    def test_exists_root(self, populated: SQLBlobBackend) -> None:
        assert populated.exists("")

    def test_exists_missing(self, backend: SQLBlobBackend) -> None:
        assert not backend.exists("nope")

    def test_is_file_true(self, populated: SQLBlobBackend) -> None:
        assert populated.is_file("a/1.txt")

    def test_is_file_false_for_folder(self, populated: SQLBlobBackend) -> None:
        assert not populated.is_file("a")

    def test_is_file_root(self, backend: SQLBlobBackend) -> None:
        assert not backend.is_file("")

    def test_is_folder_true(self, populated: SQLBlobBackend) -> None:
        assert populated.is_folder("a")

    def test_is_folder_root(self, backend: SQLBlobBackend) -> None:
        assert backend.is_folder("")

    def test_is_folder_false_for_file(self, populated: SQLBlobBackend) -> None:
        assert not populated.is_folder("a/1.txt")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-027")
class TestListFiles:
    def test_list_files_non_recursive(self, populated: SQLBlobBackend) -> None:
        files = list(populated.list_files("a"))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt"}

    def test_list_files_recursive(self, populated: SQLBlobBackend) -> None:
        files = list(populated.list_files("a", recursive=True))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt", "deep.txt"}

    def test_list_files_root(self, populated: SQLBlobBackend) -> None:
        files = list(populated.list_files("", recursive=True))
        assert len(files) == 4

    def test_list_files_empty_folder(self, backend: SQLBlobBackend) -> None:
        files = list(backend.list_files(""))
        assert files == []

    def test_list_files_max_depth(self, populated: SQLBlobBackend) -> None:
        files = list(populated.list_files("a", max_depth=0))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt"}

    def test_list_files_max_depth_deep(self, populated: SQLBlobBackend) -> None:
        files = list(populated.list_files("a", max_depth=1))
        names = {f.name for f in files}
        assert names == {"1.txt", "2.txt", "deep.txt"}


@pytest.mark.spec("SQL-BLOB-028")
class TestListFolders:
    def test_list_folders(self, populated: SQLBlobBackend) -> None:
        folders = list(populated.list_folders(""))
        names = {f.name for f in folders}
        assert names == {"a", "c"}

    def test_list_folders_nested(self, populated: SQLBlobBackend) -> None:
        folders = list(populated.list_folders("a"))
        names = {f.name for f in folders}
        assert names == {"b"}

    def test_list_folders_no_subfolders(self, populated: SQLBlobBackend) -> None:
        folders = list(populated.list_folders("c"))
        assert folders == []


# ---------------------------------------------------------------------------
# iter_children
# ---------------------------------------------------------------------------


def test_iter_children(populated: SQLBlobBackend) -> None:
    from remote_store._models import FileInfo, FolderEntry

    children = list(populated.iter_children("a"))
    files = [c for c in children if isinstance(c, FileInfo)]
    folders = [c for c in children if isinstance(c, FolderEntry)]
    assert {f.name for f in files} == {"1.txt", "2.txt"}
    assert {f.name for f in folders} == {"b"}


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-029")
class TestGetFileInfo:
    def test_basic(self, populated: SQLBlobBackend) -> None:
        info = populated.get_file_info("a/1.txt")
        assert info.name == "1.txt"
        assert info.size == 3  # len(b"one")
        assert str(info.path) == "a/1.txt"
        assert info.modified_at.tzinfo is not None

    def test_not_found(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(NotFound):
            backend.get_file_info("missing.txt")


@pytest.mark.spec("SQL-BLOB-030")
class TestGetFolderInfo:
    def test_basic(self, populated: SQLBlobBackend) -> None:
        info = populated.get_folder_info("a")
        assert info.file_count == 3  # 1.txt, 2.txt, b/deep.txt
        assert info.total_size == 3 + 3 + 4  # one + two + deep
        assert info.modified_at is not None

    def test_root(self, populated: SQLBlobBackend) -> None:
        info = populated.get_folder_info("")
        assert info.file_count == 4

    def test_not_found(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(NotFound):
            backend.get_folder_info("nonexistent")


# ---------------------------------------------------------------------------
# Move / Copy
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-BLOB-031")
class TestMove:
    def test_basic(self, backend: SQLBlobBackend) -> None:
        backend.write("src.txt", b"data")
        backend.move("src.txt", "dst.txt")
        assert not backend.exists("src.txt")
        assert backend.read_bytes("dst.txt") == b"data"

    def test_overwrite(self, backend: SQLBlobBackend) -> None:
        backend.write("src.txt", b"new")
        backend.write("dst.txt", b"old")
        backend.move("src.txt", "dst.txt", overwrite=True)
        assert backend.read_bytes("dst.txt") == b"new"
        assert not backend.exists("src.txt")

    def test_no_overwrite_raises(self, backend: SQLBlobBackend) -> None:
        backend.write("src.txt", b"data")
        backend.write("dst.txt", b"existing")
        with pytest.raises(AlreadyExists):
            backend.move("src.txt", "dst.txt")

    def test_source_not_found(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(NotFound):
            backend.move("missing.txt", "dst.txt")

    def test_same_path_noop(self, backend: SQLBlobBackend) -> None:
        backend.write("f.txt", b"data")
        backend.move("f.txt", "f.txt")
        assert backend.read_bytes("f.txt") == b"data"

    def test_same_path_missing_source(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(NotFound):
            backend.move("missing.txt", "missing.txt")


@pytest.mark.spec("SQL-BLOB-032")
class TestCopy:
    def test_basic(self, backend: SQLBlobBackend) -> None:
        backend.write("src.txt", b"data")
        backend.copy("src.txt", "dst.txt")
        assert backend.read_bytes("src.txt") == b"data"
        assert backend.read_bytes("dst.txt") == b"data"

    def test_overwrite(self, backend: SQLBlobBackend) -> None:
        backend.write("src.txt", b"new")
        backend.write("dst.txt", b"old")
        backend.copy("src.txt", "dst.txt", overwrite=True)
        assert backend.read_bytes("dst.txt") == b"new"

    def test_no_overwrite_raises(self, backend: SQLBlobBackend) -> None:
        backend.write("src.txt", b"data")
        backend.write("dst.txt", b"existing")
        with pytest.raises(AlreadyExists):
            backend.copy("src.txt", "dst.txt")

    def test_source_not_found(self, backend: SQLBlobBackend) -> None:
        with pytest.raises(NotFound):
            backend.copy("missing.txt", "dst.txt")


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
    b = SQLBlobBackend(url="sqlite:///:memory:")
    b.write("f.txt", b"data")
    b.close()
    # After close, operations should fail (engine disposed)
    with pytest.raises((RemoteStoreError, Exception)):
        b.read_bytes("f.txt")


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
    assert col_names == {"key", "data", "size", "modified_at", "content_type", "digest", "extra"}


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
