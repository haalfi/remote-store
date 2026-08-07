"""``SQLBlobBackend`` under BE-012/BE-013's absent-container rule.

The table is this backend's container, so a dropped table is the SQL spelling of
a deleted bucket, and the rule binds it like every other flat-namespace backend:
``missing_ok=True`` returns cleanly, ``missing_ok=False`` raises ``NotFound``.

Getting there took three refuted attempts at *exempting* it, which is why the
exemption is gone rather than reworded. Each attempt tried to derive a general
scope criterion, and each was circular or false — the last one keyed on whether
a backend's mapping already turns an absent container into ``NotFound``, which
BE-021's own canonical table requires of every backend anyway. Complying costs
one inspector call on an already-failed statement, so there was nothing left for
a criterion to buy.

Four properties matter and each is pinned here, because the three beyond
tolerance all fail *silently* — a regression in any of them leaves the tolerance
cells green:

* **The tolerance reaches the caller** (``TestAbsentTableReadsAsAbsentPath``).
* **It costs nothing on the miss path** (``TestTheProbeStaysOffTheHotPath``). The
  inspector call hangs off ``SQLAlchemyError``, so an ordinary miss — which
  raises this module's own ``NotFound`` from a query that *succeeded* — never
  reaches it. That bound is what makes the rule's no-extra-round-trip budget
  survive.
* **A real fault is not mistaken for a missing table**
  (``TestTheCatchStaysNarrow``). This is the branch whose failure mode is the
  dangerous one: reporting ``NotFound`` for a database that is broken rather
  than empty. Widening the catch would look exactly like success.
* **A closed backend does not reclassify** (``TestAClosedBackendIsNotAnEmptyStore``).
  On an in-memory engine, re-initialising after ``close()`` opens a *different,
  empty* database, so the inspector truthfully finds no table — and answering
  "no such path" there would describe a store the caller destroyed, in
  contradiction with every operation that lacks the wrapper.

``TestContainerExistsByConstruction`` records the constructor's two paths. Worth
pinning because it shapes what a caller can encounter, but note what it does
**not** establish: it does not make the rule vacuous here, since a live instance
can be bound to an absent container by dropping the table under it — which is
exactly what the first class does.

**Coverage bound:** only SQLite runs here. A dropped table raises
``OperationalError`` on SQLite and ``ProgrammingError`` on PostgreSQL and MySQL;
both are ``SQLAlchemyError`` subclasses, so the branch below covers both by
construction, but only the SQLite half is executed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from remote_store._errors import BackendUnavailable, NotFound
from remote_store.backends._sqlalchemy import SQLBlobBackend

if TYPE_CHECKING:
    from pathlib import Path

_TABLE = "remote_store_objects"


def _replace_table_with_incompatible_schema(backend: SQLBlobBackend) -> None:
    """Leave a table of that name in place, but one the delete statement cannot use.

    Produces a genuine driver failure with ``has_table`` still answering yes —
    the state the narrowness branch has to tell apart from a dropped table.
    """
    with backend._engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE {_TABLE}"))
        conn.execute(sa.text(f"CREATE TABLE {_TABLE} (unrelated TEXT)"))


@pytest.fixture
def backend(tmp_path: Path):  # noqa: ANN201 -- yields SQLBlobBackend
    """A file-backed SQLBlob store holding one key."""
    instance = SQLBlobBackend(f"sqlite:///{tmp_path / 'store.db'}")
    instance.write("folder/object.txt", b"payload")
    try:
        yield instance
    finally:
        instance.close()


def _drop_table(backend: SQLBlobBackend) -> None:
    with backend._engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE {_TABLE}"))


@pytest.mark.spec("BE-012", "BE-013", "BE-021", "SQL-BLOB-024", "SQL-BLOB-025")
class TestAbsentTableReadsAsAbsentPath:
    """A dropped table is a missing path, not a failed statement."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_tolerant_delete_returns_cleanly(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        _drop_table(backend)
        assert call(backend) is None, f"{op_name} must tolerate an absent table under missing_ok"

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt")),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_strict_delete_raises_not_found(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """Without ``missing_ok`` the same dropped table is a plain ``NotFound``.

        The tolerance belongs to ``missing_ok``, not to the dropped table: a
        backend that merely stopped raising on the driver error would pass the
        cells above and silently turn a strict delete into a no-op.
        """
        _drop_table(backend)
        with pytest.raises(NotFound) as exc_info:
            call(backend)
        assert exc_info.value.backend == "sql-blob"


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestTheProbeStaysOffTheHotPath:
    """The inspector call is charged to failed statements only, never to a miss."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/absent.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("absent", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_ordinary_miss_never_inspects_the_table(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """An absent *path* on a present table must not spend the extra round trip.

        The contract budgets one probe per miss and forbids paying another to
        tell an absent container from an absent path. This backend honours that
        by hanging the inspection off ``SQLAlchemyError``: an ordinary miss
        raises from a query that succeeded, so the branch is never entered.
        Asserting the call count is the only way to keep that true — the
        tolerance tests above pass just as happily with the probe on every miss.
        """
        with patch.object(
            SQLBlobBackend,
            "_table_is_absent",
            autospec=True,
            side_effect=AssertionError(f"{op_name}: inspected the table on an ordinary miss"),
        ) as probe:
            assert call(backend) is None
        assert probe.call_count == 0


@pytest.mark.spec("BE-021", "SQL-BLOB-050")
class TestTheCatchStaysNarrow:
    """A driver failure on a *live* table keeps its mapping, unreclassified."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_driver_error_with_the_table_present_still_maps(
        self,
        backend: SQLBlobBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The failure mode this guards is reporting ``NotFound`` for a broken database.

        Everything else in this module asserts that a ``SQLAlchemyError`` becomes
        a missing path. This asserts the converse — that it does so *only* when
        the table is really gone — which is the half a widened catch would break
        while leaving the tolerance cells green.

        Nothing is mocked: the table is replaced with one that has no ``key``
        column, so the real statement fails with a real ``OperationalError``
        while ``has_table`` truthfully answers yes. That is the exact state the
        branch discriminates on, produced rather than simulated.
        """
        _replace_table_with_incompatible_schema(backend)
        with pytest.raises(BackendUnavailable) as exc_info:
            call(backend)
        assert exc_info.value.backend == "sql-blob", op_name

    def test_a_failed_inspection_leaves_the_original_error_standing(self, backend: SQLBlobBackend) -> None:
        """``_table_is_absent`` fails closed, so an unanswerable probe reclassifies nothing.

        The table really is gone here, so the tolerance *would* fire — but the
        inspection cannot run, and the conservative answer keeps the operation's
        own error rather than inventing a verdict from a probe that failed.
        """
        _drop_table(backend)
        with (
            patch(
                "sqlalchemy.inspect",
                side_effect=sa.exc.OperationalError("inspect", {}, Exception("cannot inspect")),
            ),
            pytest.raises(BackendUnavailable),
        ):
            backend.delete("folder/object.txt", missing_ok=True)


@pytest.mark.spec("BE-020", "BE-021", "SQL-BLOB-041")
class TestAClosedBackendIsNotAnEmptyStore:
    """Re-initialising an in-memory engine is not the same as finding no path."""

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_use_after_close_on_memory_still_reports_unavailable(
        self,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """``close()`` on ``:memory:`` destroys the store; the deletes must say so.

        ``close_is_terminal`` is ``False`` here, so the backend re-initialises
        lazily — but for an in-memory engine that opens a *different* database
        with no table, and the inspector cannot tell that from a dropped one.
        Without the closed-backend gate these two calls answered "nothing to
        delete" while ``read`` on the same instance still raised
        ``BackendUnavailable``: two verdicts for one dead store, which is the
        defect class the absent-container rule exists to remove.
        """
        instance = SQLBlobBackend("sqlite:///:memory:")
        instance.write("folder/object.txt", b"payload")
        instance.close()
        with pytest.raises(BackendUnavailable):
            call(instance)

    def test_read_and_delete_agree_after_close(self) -> None:
        """The property the gate exists for, asserted as the agreement it is."""
        instance = SQLBlobBackend("sqlite:///:memory:")
        instance.write("folder/object.txt", b"payload")
        instance.close()
        with pytest.raises(BackendUnavailable):
            instance.read_bytes("folder/object.txt")
        with pytest.raises(BackendUnavailable):
            instance.delete("folder/object.txt", missing_ok=True)

    def test_a_borrowed_engine_keeps_the_tolerance_after_close(self, tmp_path: Path) -> None:
        """``close()`` disposes nothing here, so the store is untouched and the rule holds.

        The gate's condition is "did closing discard the store", not "was
        ``close()`` called", and this is one of the two cases that separates
        them. SQL-BLOB-041 makes ``close()`` a no-op for a borrowed engine, so
        an instance closed and reused is working against the same live database
        — and a table dropped afterwards is exactly what the clause governs.
        """
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'borrowed.db'}")
        try:
            instance = SQLBlobBackend(engine=engine)
            instance.write("folder/object.txt", b"payload")
            instance.close()
            _drop_table(instance)
            assert instance.delete("folder/object.txt", missing_ok=True) is None
        finally:
            engine.dispose()

    def test_an_owned_file_engine_keeps_the_tolerance_after_close(self, tmp_path: Path) -> None:
        """Disposing a file engine loses nothing: it reopens with its contents.

        The second separating case. ``close_is_terminal=False`` permits closing
        and resuming, and the resumed instance is on the same database, so it
        must still reclassify a table dropped later. Gating on ``close()``
        alone silently disabled the rule for the rest of the instance's life.
        """
        instance = SQLBlobBackend(f"sqlite:///{tmp_path / 'owned.db'}")
        instance.write("folder/object.txt", b"payload")
        instance.close()
        instance.write("folder/other.txt", b"payload")  # resume: reopens the same file
        _drop_table(instance)
        assert instance.delete("folder/object.txt", missing_ok=True) is None
        instance.close()


class TestContainerExistsByConstruction:
    """The two constructor paths, recorded for what a caller can encounter."""

    @pytest.mark.spec("BE-012", "BE-013", "SQL-BLOB-010")
    def test_default_creates_the_table(self, backend: SQLBlobBackend) -> None:
        """``create_table=True`` means the container exists the moment the backend does."""
        assert sa.inspect(backend._engine).has_table(_TABLE)

    @pytest.mark.spec("BE-012", "BE-013", "SQL-BLOB-012")
    def test_reflection_refuses_an_absent_table(self, tmp_path: Path) -> None:
        """``create_table=False`` cannot bind to a table that is not there."""
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        try:
            with pytest.raises(sa.exc.NoSuchTableError):
                SQLBlobBackend(engine=engine, table_name=_TABLE, create_table=False)
        finally:
            engine.dispose()
