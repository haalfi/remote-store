"""Tests for SQLQueryBackend — read-only SQL query materializer."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pyarrow.csv as pcsv
import pyarrow.ipc as pipc
import pyarrow.parquet as pq
import pytest
import sqlalchemy as sa

from remote_store._capabilities import Capability
from remote_store._errors import (
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo
from remote_store.backends._sqlalchemy import (
    ArrowSerializer,
    SQLQueryBackend,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    """SQLite engine with a pre-populated test table."""
    eng = sa.create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE sales (id INTEGER, amount REAL, region TEXT)"))
        conn.execute(
            sa.text("INSERT INTO sales VALUES (:id, :amount, :region)"),
            [
                {"id": 1, "amount": 100.0, "region": "north"},
                {"id": 2, "amount": 200.0, "region": "south"},
                {"id": 3, "amount": 150.0, "region": "north"},
            ],
        )
    yield eng
    eng.dispose()


@pytest.fixture
def backend(engine: sa.Engine) -> Iterator[SQLQueryBackend]:
    """Backend with explicit query mappings."""
    b = SQLQueryBackend(
        engine=engine,
        queries={
            "reports/sales.parquet": "SELECT * FROM sales",
            "reports/sales.csv": "SELECT * FROM sales",
            "reports/sales.arrow": "SELECT * FROM sales",
            "reports/north.parquet": "SELECT * FROM sales WHERE region = 'north'",
            "summaries/total.parquet": "SELECT SUM(amount) AS total FROM sales",
        },
    )
    yield b
    b.close()


# ---------------------------------------------------------------------------
# Construction & properties
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-001")
class TestConstruction:
    def test_url_creates_backend(self) -> None:
        b = SQLQueryBackend(url="sqlite:///:memory:", queries={"t.parquet": "SELECT 1"})
        assert b.name == "sql-query"
        b.close()

    def test_engine_creates_backend(self, engine: sa.Engine) -> None:
        b = SQLQueryBackend(engine=engine, queries={"t.parquet": "SELECT 1"})
        assert b.name == "sql-query"
        b.close()

    def test_both_url_and_engine_raises(self, engine: sa.Engine) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            SQLQueryBackend(url="sqlite:///:memory:", engine=engine)

    def test_neither_url_nor_engine_raises(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            SQLQueryBackend()

    @pytest.mark.parametrize(
        "queries",
        [
            {"": "SELECT 1"},
            {"t.parquet": ""},
            {"  ": "SELECT 1"},
            {"t.parquet": "  "},
        ],
        ids=["empty_key", "empty_sql", "whitespace_key", "whitespace_sql"],
    )
    def test_invalid_queries_raise(self, queries: dict[str, str]) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            SQLQueryBackend(url="sqlite:///:memory:", queries=queries)

    def test_no_queries_is_valid(self) -> None:
        b = SQLQueryBackend(url="sqlite:///:memory:")
        assert len(list(b.list_files(""))) == 0
        b.close()


@pytest.mark.spec("SQL-QUERY-002")
class TestName:
    def test_name(self, backend: SQLQueryBackend) -> None:
        assert backend.name == "sql-query"


@pytest.mark.spec("SQL-QUERY-003")
class TestCapabilities:
    def test_capabilities(self, backend: SQLQueryBackend) -> None:
        caps = backend.capabilities
        assert Capability.READ in caps
        assert Capability.LIST in caps
        assert Capability.METADATA in caps
        assert Capability.GLOB in caps
        assert Capability.SEEKABLE_READ in caps
        # Not supported
        assert Capability.WRITE not in caps
        assert Capability.DELETE not in caps
        assert Capability.MOVE not in caps
        assert Capability.COPY not in caps
        assert Capability.ATOMIC_WRITE not in caps
        assert Capability.ATOMIC_MOVE not in caps


@pytest.mark.spec("SQL-QUERY-004")
class TestRepr:
    def test_repr(self, backend: SQLQueryBackend) -> None:
        r = repr(backend)
        assert "sql-query" not in r  # uses class name
        assert "SQLQueryBackend" in r
        assert "sqlite" in r
        assert "keys=5" in r
        assert "strict=True" in r


@pytest.mark.spec("SQL-QUERY-011")
class TestStrictMode:
    def test_strict_false_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            SQLQueryBackend(url="sqlite:///:memory:", strict=False)


@pytest.mark.spec("SQL-QUERY-005")
class TestRegistration:
    def test_sql_query_registered(self) -> None:
        from remote_store._registry import _BACKEND_FACTORIES, _register_builtin_backends

        _register_builtin_backends()
        assert _BACKEND_FACTORIES.get("sql-query") is SQLQueryBackend


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-012")
class TestFormatDetection:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("data.parquet", "parquet"),
            ("data.csv", "csv"),
            ("data.arrow", "arrow"),
            ("data.ipc", "arrow"),
        ],
        ids=["parquet", "csv", "arrow", "ipc"],
    )
    def test_supported_extensions(self, backend: SQLQueryBackend, path: str, expected: str) -> None:
        assert backend._detect_format(path) == expected

    @pytest.mark.parametrize("path", ["data.xlsx", "data"], ids=["unknown_ext", "no_ext"])
    def test_unsupported_extension_raises(self, backend: SQLQueryBackend, path: str) -> None:
        with pytest.raises(InvalidPath, match="Unsupported format"):
            backend._detect_format(path)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-013")
@pytest.mark.spec("SQL-QUERY-014")
class TestArrowSerializer:
    _ROWS = [(1, "a"), (2, "b")]
    _COLS = ["id", "name"]

    @pytest.mark.parametrize(
        ("fmt", "reader"),
        [
            ("parquet", lambda d: pq.read_table(io.BytesIO(d))),
            ("csv", lambda d: pcsv.read_csv(io.BytesIO(d))),
            ("arrow", lambda d: pipc.open_file(io.BytesIO(d)).read_all()),
        ],
        ids=["parquet", "csv", "arrow_ipc"],
    )
    def test_serialize_format(self, fmt: str, reader: object) -> None:
        data = ArrowSerializer().serialize(self._ROWS, self._COLS, fmt)
        table = reader(data)  # type: ignore[operator]
        assert table.num_rows == 2

    def test_serialize_empty_result(self) -> None:
        s = ArrowSerializer()
        data = s.serialize([], ["id", "name"], "parquet")
        table = pq.read_table(io.BytesIO(data))
        assert table.num_rows == 0
        assert table.column_names == ["id", "name"]

    def test_unsupported_format_raises(self) -> None:
        s = ArrowSerializer()
        with pytest.raises(ValueError, match="Unsupported serialization format"):
            s.serialize([], ["id"], "xlsx")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-020")
class TestRead:
    @pytest.mark.parametrize(
        ("key", "reader"),
        [
            ("reports/sales.parquet", lambda d: pq.read_table(io.BytesIO(d))),
            ("reports/sales.csv", lambda d: pcsv.read_csv(io.BytesIO(d))),
            ("reports/sales.arrow", lambda d: pipc.open_file(io.BytesIO(d)).read_all()),
        ],
        ids=["parquet", "csv", "arrow"],
    )
    def test_read_format(self, backend: SQLQueryBackend, key: str, reader: object) -> None:
        stream = backend.read(key)
        data = stream.read()
        table = reader(data)  # type: ignore[operator]
        assert table.num_rows == 3

    def test_read_filtered_query(self, backend: SQLQueryBackend) -> None:
        data = backend.read_bytes("reports/north.parquet")
        table = pq.read_table(io.BytesIO(data))
        assert table.num_rows == 2
        assert all(r == "north" for r in table.column("region").to_pylist())

    def test_read_aggregate_query(self, backend: SQLQueryBackend) -> None:
        data = backend.read_bytes("summaries/total.parquet")
        table = pq.read_table(io.BytesIO(data))
        assert table.num_rows == 1
        assert table.column("total").to_pylist()[0] == 450.0

    @pytest.mark.spec("SQL-QUERY-010")
    def test_read_not_found(self, backend: SQLQueryBackend) -> None:
        with pytest.raises(NotFound, match="No query registered"):
            backend.read("nonexistent.parquet")

    def test_read_is_seekable(self, backend: SQLQueryBackend) -> None:
        stream = backend.read("reports/sales.parquet")
        stream.seek(0)
        data1 = stream.read()
        stream.seek(0)
        data2 = stream.read()
        assert data1 == data2

    def test_read_empty_result(self, engine: sa.Engine) -> None:
        b = SQLQueryBackend(
            engine=engine,
            queries={"empty.parquet": "SELECT * FROM sales WHERE 1=0"},
        )
        data = b.read_bytes("empty.parquet")
        table = pq.read_table(io.BytesIO(data))
        assert table.num_rows == 0
        assert "id" in table.column_names
        b.close()


@pytest.mark.spec("SQL-QUERY-021")
class TestReadBytes:
    def test_read_bytes_returns_bytes(self, backend: SQLQueryBackend) -> None:
        data = backend.read_bytes("reports/sales.parquet")
        assert isinstance(data, bytes)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# Existence checks
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-042")
class TestExists:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("reports/sales.parquet", True),
            ("nonexistent.parquet", False),
            ("reports", True),
            ("missing", False),
            ("", True),
        ],
        ids=["file", "file_missing", "folder", "folder_missing", "root"],
    )
    def test_exists(self, backend: SQLQueryBackend, path: str, expected: bool) -> None:
        assert backend.exists(path) is expected


@pytest.mark.spec("SQL-QUERY-043")
class TestIsFile:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("reports/sales.parquet", True),
            ("reports", False),
            ("", False),
        ],
        ids=["file", "folder", "root"],
    )
    def test_is_file(self, backend: SQLQueryBackend, path: str, expected: bool) -> None:
        assert backend.is_file(path) is expected


@pytest.mark.spec("SQL-QUERY-044")
class TestIsFolder:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("reports", True),
            ("", True),
            ("reports/sales.parquet", False),
            ("nonexistent", False),
        ],
        ids=["prefix", "root", "file", "missing"],
    )
    def test_is_folder(self, backend: SQLQueryBackend, path: str, expected: bool) -> None:
        assert backend.is_folder(path) is expected


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-030")
class TestListFiles:
    def test_list_all(self, backend: SQLQueryBackend) -> None:
        files = list(backend.list_files("", recursive=True))
        assert len(files) == 5
        assert all(isinstance(f, FileInfo) for f in files)

    def test_list_non_recursive(self, backend: SQLQueryBackend) -> None:
        # No direct files under root — all are in subfolders
        files = list(backend.list_files(""))
        assert len(files) == 0

    def test_list_prefix(self, backend: SQLQueryBackend) -> None:
        files = list(backend.list_files("reports", recursive=True))
        assert len(files) == 4  # sales.parquet, sales.csv, sales.arrow, north.parquet

    def test_list_direct_children(self, backend: SQLQueryBackend) -> None:
        files = list(backend.list_files("reports"))
        assert len(files) == 4

    def test_list_empty_prefix(self, backend: SQLQueryBackend) -> None:
        files = list(backend.list_files("summaries"))
        assert len(files) == 1
        assert files[0].name == "total.parquet"

    def test_list_max_depth(self, backend: SQLQueryBackend) -> None:
        """DEPTH-003: the bound applies only when ``recursive=True``.

        Previously this asserted ``list_files("", max_depth=1) == 5`` — depth
        taking precedence over the default ``recursive=False``. BK-324 facet 3
        settled the Backend-ABC rule the other way, so that combination is now
        inert and the recursive form carries the depth assertions.
        """
        assert len(list(backend.list_files("", recursive=True, max_depth=0))) == 0  # all files are at depth 1
        assert len(list(backend.list_files("", recursive=True, max_depth=1))) == 5

        # recursive=False ignores the bound rather than letting it take
        # precedence: only depth-0 files, and every file here is one level down.
        assert len(list(backend.list_files("", max_depth=1))) == 0

    def test_file_info_sentinel_values(self, backend: SQLQueryBackend) -> None:
        files = list(backend.list_files("reports"))
        for f in files:
            assert f.size == 0
            assert f.extra.get("materialized") is False


@pytest.mark.spec("SQL-QUERY-031")
class TestListFolders:
    def test_list_root_folders(self, backend: SQLQueryBackend) -> None:
        folders = list(backend.list_folders(""))
        names = {f.name for f in folders}
        assert names == {"reports", "summaries"}
        assert all(isinstance(f, FolderEntry) for f in folders)

    def test_list_no_subfolders(self, backend: SQLQueryBackend) -> None:
        folders = list(backend.list_folders("reports"))
        assert len(folders) == 0


@pytest.mark.spec("SQL-QUERY-030")
class TestIterChildren:
    def test_iter_children_root(self, backend: SQLQueryBackend) -> None:
        children = list(backend.iter_children(""))
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in folders} == {"reports", "summaries"}

    def test_iter_children_prefix(self, backend: SQLQueryBackend) -> None:
        children = list(backend.iter_children("reports"))
        files = [c for c in children if isinstance(c, FileInfo)]
        assert len(files) == 4

    def test_iter_children_leaf(self, backend: SQLQueryBackend) -> None:
        children = list(backend.iter_children("summaries"))
        files = [c for c in children if isinstance(c, FileInfo)]
        assert len(files) == 1
        assert files[0].name == "total.parquet"


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-040")
class TestGetFileInfo:
    def test_get_file_info(self, backend: SQLQueryBackend) -> None:
        info = backend.get_file_info("reports/sales.parquet")
        assert isinstance(info, FileInfo)
        assert info.name == "sales.parquet"
        assert info.size == 0
        assert info.extra.get("materialized") is False

    def test_get_file_info_not_found(self, backend: SQLQueryBackend) -> None:
        with pytest.raises(NotFound):
            backend.get_file_info("missing.parquet")


@pytest.mark.spec("SQL-QUERY-041")
class TestGetFolderInfo:
    def test_get_folder_info(self, backend: SQLQueryBackend) -> None:
        info = backend.get_folder_info("reports")
        assert isinstance(info, FolderInfo)
        assert info.file_count == 4
        assert info.total_size == 0

    def test_get_folder_info_root(self, backend: SQLQueryBackend) -> None:
        info = backend.get_folder_info("")
        assert info.file_count == 5

    def test_get_folder_info_not_found(self, backend: SQLQueryBackend) -> None:
        with pytest.raises(NotFound, match="Folder not found"):
            backend.get_folder_info("missing")


# ---------------------------------------------------------------------------
# Glob
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-032")
class TestGlob:
    def test_glob_parquet(self, backend: SQLQueryBackend) -> None:
        files = list(backend.glob("**/*.parquet"))
        assert len(files) == 3  # sales, north, total

    def test_glob_csv(self, backend: SQLQueryBackend) -> None:
        files = list(backend.glob("**/*.csv"))
        assert len(files) == 1
        assert files[0].name == "sales.csv"

    def test_glob_prefix(self, backend: SQLQueryBackend) -> None:
        files = list(backend.glob("reports/*"))
        assert len(files) == 4

    def test_glob_no_match(self, backend: SQLQueryBackend) -> None:
        files = list(backend.glob("**/*.xlsx"))
        assert len(files) == 0


# ---------------------------------------------------------------------------
# Unsupported operations
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-050")
class TestUnsupportedOps:
    @pytest.mark.parametrize(
        ("method", "args"),
        [
            ("write", ("x.parquet", b"data")),
            ("write_atomic", ("x.parquet", b"data")),
            ("open_atomic", ("x.parquet",)),
            ("delete", ("x.parquet",)),
            ("delete_folder", ("reports",)),
            ("move", ("a.parquet", "b.parquet")),
            ("copy", ("a.parquet", "b.parquet")),
        ],
        ids=["write", "write_atomic", "open_atomic", "delete", "delete_folder", "move", "copy"],
    )
    def test_unsupported_op(self, backend: SQLQueryBackend, method: str, args: tuple[object, ...]) -> None:
        with pytest.raises(CapabilityNotSupported, match="read-only"):
            getattr(backend, method)(*args)


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-070")
class TestErrorMapping:
    def test_bad_sql_raises(self, engine: sa.Engine) -> None:
        from remote_store._errors import RemoteStoreError

        b = SQLQueryBackend(
            engine=engine,
            queries={"bad.parquet": "SELECT * FROM nonexistent_table"},
        )
        with pytest.raises(RemoteStoreError):
            b.read_bytes("bad.parquet")
        b.close()

    def test_key_not_found(self, backend: SQLQueryBackend) -> None:
        with pytest.raises(NotFound, match="No query registered"):
            backend.read("unknown.parquet")


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-080")
class TestPathValidation:
    @pytest.mark.parametrize(
        ("path", "match"),
        [
            ("test\x00.parquet", "null byte"),
            ("/test.parquet", "Absolute"),
            ("../test.parquet", "\\.\\."),
        ],
        ids=["null_byte", "absolute", "dotdot"],
    )
    def test_invalid_path(self, backend: SQLQueryBackend, path: str, match: str) -> None:
        with pytest.raises(InvalidPath, match=match):
            backend.read(path)


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.spec("SQL-QUERY-060")
class TestHealthCheck:
    def test_check_health(self, backend: SQLQueryBackend) -> None:
        result = backend.check_health()
        assert result is None


@pytest.mark.spec("SQL-QUERY-062")
class TestUnwrap:
    def test_unwrap_engine(self, backend: SQLQueryBackend) -> None:
        engine = backend.unwrap(sa.Engine)
        assert isinstance(engine, sa.Engine)
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))


class TestSQLQueryResolve:
    """RES-058: SQLQueryBackend.resolve() returns kind='sql-query' with source and format."""

    @pytest.mark.spec("RES-058")
    def test_kind_is_sql_query(self, backend: SQLQueryBackend) -> None:
        plan = backend.resolve("reports/sales.parquet")
        assert plan.kind == "sql-query"

    @pytest.mark.spec("RES-058")
    def test_details_has_source(self, backend: SQLQueryBackend) -> None:
        plan = backend.resolve("reports/sales.parquet")
        assert "source" in plan.details
        assert plan.details["source"] == "explicit"

    @pytest.mark.spec("RES-058")
    def test_details_has_format(self, backend: SQLQueryBackend) -> None:
        plan = backend.resolve("reports/sales.parquet")
        assert "format" in plan.details
        assert plan.details["format"] == "parquet"

    @pytest.mark.spec("RES-058")
    def test_csv_format(self, backend: SQLQueryBackend) -> None:
        plan = backend.resolve("reports/sales.csv")
        assert plan.details["format"] == "csv"


# ---------------------------------------------------------------------------
# Root path (BE-029)
# ---------------------------------------------------------------------------


class TestRootPath:
    """BE-029 on a LIST-capable, WRITE-less backend.

    These cells predate the fixture registration. BK-340 registered
    ``sqlquery``, so ``conformance/test_io.py::TestBackendRootPath`` now runs
    the BE-029 lane against this backend directly (24 cells) — the durable fix
    for the gap that let a root-spelling defect survive a source-wide sweep,
    where the sweep found the sites and nothing ran them.

    They are kept rather than deleted because they assert something the
    conformance lane structurally cannot: the **populated** store. The
    conformance fixture registers an empty query mapping, since every
    conformance fixture starts from an empty store and
    ``test_get_folder_info_on_empty_root_does_not_raise`` asserts exactly that;
    seeding it is impossible because the suite seeds through ``backend.write``
    and this backend is read-only (ID-244). So the ``file_count == 5``
    assertions below have no cross-backend equivalent, and the empty-store
    cells here are the deliberate overlap that keeps the pair comparable.
    """

    @pytest.mark.spec("BE-029")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_root_is_a_folder(self, backend: SQLQueryBackend, root: str) -> None:
        assert backend.exists(root) is True
        assert backend.is_folder(root) is True
        assert backend.is_file(root) is False

    @pytest.mark.spec("BE-029")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_root_is_a_folder_with_no_queries(self, engine: sa.Engine, root: str) -> None:
        """An empty mapping still has a root.

        The empty store is where a truthiness test shows: ``""`` short-circuits
        before the lookup, ``"."`` falls through to it and finds nothing.
        """
        empty = SQLQueryBackend(engine=engine, queries={})
        assert empty.exists(root) is True
        assert empty.is_folder(root) is True
        assert empty.is_file(root) is False

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-017")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_get_folder_info_on_root_aggregates(self, backend: SQLQueryBackend, root: str) -> None:
        assert backend.get_folder_info(root).file_count == 5

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-017")
    @pytest.mark.parametrize("root", ["", "."], ids=["empty", "dot"])
    def test_get_folder_info_on_empty_root_does_not_raise(self, engine: sa.Engine, root: str) -> None:
        """Zero registered queries aggregates to zero, not ``NotFound``."""
        empty = SQLQueryBackend(engine=engine, queries={})
        assert empty.get_folder_info(root).file_count == 0

    @pytest.mark.spec("BE-025")
    @pytest.mark.spec("BE-029")
    def test_native_path_agrees_on_both_root_spellings(self, backend: SQLQueryBackend) -> None:
        assert backend.native_path(".") == backend.native_path("")
