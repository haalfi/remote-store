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
* **The rule holds across its whole condition space**
  (``TestTheReclassificationOverItsWholeConditionSpace``). Ownership x locality
  x lifecycle x table, generated as a product rather than hand-listed. Three
  review rounds each found the reclassification keyed on the wrong condition
  because the reasoning was argued rather than enumerated; the table answers
  the question by exhaustion, and every reachable cell answers the same way.

``TestADiscardedInMemoryStoreReadsAsEmpty`` documents the one residue: dispose an
in-memory engine and the deletes tolerate while ``read`` raises, because only the
deletes carry the reclassification. That asymmetry is BUG-246. A guard against it
shipped briefly and was withdrawn — "was the store discarded" is not decidable
from configuration, and every version of the check made behaviour depend on how
the caller spelled the URL.

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


@pytest.mark.spec("BE-012", "BE-013", "BE-020", "BE-021")
class TestADiscardedInMemoryStoreReadsAsEmpty:
    """Disposing an in-memory engine leaves an empty store, and the deletes say so.

    Recorded because it is the one place the rule produces an answer that reads
    oddly, and because a guard against it shipped briefly and was withdrawn.

    Disposing an in-memory SQLite engine destroys the data, so the next
    statement opens a *different, empty* database. The deletes then tolerate —
    correctly, by the rule — while ``read`` raises ``BackendUnavailable``,
    because only the deletes carry the reclassification. That asymmetry is
    BUG-246, not a defect in this clause: once ``read`` and ``exists`` answer
    for an absent table the way the contract requires, every operation agrees
    that a discarded store is an empty one.

    The withdrawn guard is worth a sentence, since three review rounds went into
    it. "Was the store discarded" is not decidable from configuration: keyed on
    ``close()`` it broke two live stores, keyed additionally on an in-memory URL
    it still missed the URI-form spellings, and it could never see an owner
    disposing a *borrowed* engine, which touches this object not at all. Each
    version made behaviour depend on URL spelling rather than on the store.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "sqlite:///:memory:",
            "sqlite://",
            "sqlite:///file::memory:?uri=true",
            "sqlite:///file:memdb1?mode=memory&cache=shared&uri=true",
        ],
        ids=["memory", "bare", "uri-anonymous", "uri-named-shared"],
    )
    def test_every_in_memory_spelling_answers_the_same(self, url: str) -> None:
        """All four in-memory spellings, so the answer cannot depend on the URL.

        The withdrawn guard covered the first two and not the last two, which is
        precisely the failure mode: a caller who spells an in-memory database
        the URI way got different delete semantics from one who did not.
        """
        instance = SQLBlobBackend(url)
        instance.write("folder/object.txt", b"payload")
        instance.close()
        assert instance.delete("folder/object.txt", missing_ok=True) is None
        assert instance.delete_folder("folder", recursive=True, missing_ok=True) is None

    def test_a_borrowed_engine_disposed_by_its_owner_answers_the_same(self) -> None:
        """No call reaches this object, so no guard here could ever have seen it.

        The case that showed the detection was not merely incomplete but
        unavailable: the owner disposes the engine directly, and the backend
        learns of it only by failing.
        """
        engine = sa.create_engine("sqlite:///:memory:")
        instance = SQLBlobBackend(engine=engine)
        instance.write("folder/object.txt", b"payload")
        engine.dispose()
        assert instance.delete("folder/object.txt", missing_ok=True) is None

    def test_the_read_asymmetry_is_bug_246_not_this_clause(self) -> None:
        """Pins the residue, so closing BUG-246 is visible here rather than silent."""
        instance = SQLBlobBackend("sqlite:///:memory:")
        instance.write("folder/object.txt", b"payload")
        instance.close()
        assert instance.delete("folder/object.txt", missing_ok=True) is None
        with pytest.raises(BackendUnavailable):
            instance.read_bytes("folder/object.txt")


class TestTheReclassificationOverItsWholeConditionSpace:
    """Every reachable state of the reclassification, as a truth table.

    Three review rounds each found this keyed on the wrong condition, and each
    time the fix was argued rather than enumerated — so each time a reviewer
    found a state the argument had not considered. The condition space is small
    and finite, so this closes it by exhaustion instead: ownership (owned /
    borrowed) x locality (in-memory / file) x lifecycle (open / closed) x table
    (present / dropped).

    **Every reachable state answers the same way**, and that uniformity is the
    result rather than a coincidence. Earlier versions carved out a state — the
    discarded in-memory store — and each carve-out was either wrong or
    undetectable; withdrawing it left a rule with no exceptions, which is the
    only shape this table can state exhaustively. A dropped table is tolerated
    under ``missing_ok`` wherever the statement can reach a database at all.

    Two cells are unreachable rather than untested, and saying which matters:
    disposing an owned in-memory engine *is* what discards the table, so
    "closed, owned, in-memory" cannot be paired with either table state
    meaningfully — the store is new and empty whichever was requested. Both are
    covered by ``TestADiscardedInMemoryStoreReadsAsEmpty`` instead, which is
    where the residue and its BUG-246 link are documented.
    """

    @pytest.mark.parametrize("owned", [True, False], ids=["owned", "borrowed"])
    @pytest.mark.parametrize("in_memory", [True, False], ids=["memory", "file"])
    @pytest.mark.parametrize("close_first", [True, False], ids=["closed", "open"])
    @pytest.mark.parametrize("drop_table", [True, False], ids=["dropped", "present"])
    # BE-012 only: this cell exercises ``delete``. ``delete_folder`` (BE-013) is
    # covered over the same axes by the classes above; running the whole product
    # twice would double the cell count to re-assert one shared code path.
    @pytest.mark.spec("BE-012", "BE-020", "BE-021")
    def test_tolerant_delete_over_the_matrix(
        self,
        tmp_path: Path,
        owned: bool,
        in_memory: bool,
        close_first: bool,
        drop_table: bool,
    ) -> None:
        """One operation, every state: ``delete(missing_ok=True)`` on an absent key.

        Parametrised on the axes themselves rather than on a hand-written list
        of tuples, so the product is generated and no coordinate can be omitted
        or mislabelled by hand — an earlier hand-listed version had a row whose
        id disagreed with its coordinates and a guard for a row that was not
        there.
        """
        url = "sqlite:///:memory:" if in_memory else f"sqlite:///{tmp_path / 'matrix.db'}"
        engine = None if owned else sa.create_engine(url)
        backend = SQLBlobBackend(url) if owned else SQLBlobBackend(engine=engine)
        try:
            backend.write("folder/object.txt", b"payload")
            if close_first:
                backend.close()
            if drop_table and not (in_memory and close_first):
                # An in-memory store that has been closed is already empty; there
                # is nothing left to drop, and the DROP would fail on a fresh db.
                _drop_table(backend)
            assert backend.delete("folder/absent.txt", missing_ok=True) is None
        finally:
            backend.close()
            if engine is not None:
                engine.dispose()


class TestContainerExistsByConstruction:
    """The two constructor paths, recorded for what a caller can encounter.

    No BE-012 / BE-013 mark here: neither cell calls a delete. They record how a
    caller reaches the absent-container state at all, which is context for the
    rule rather than a test of it.
    """

    @pytest.mark.spec("SQL-BLOB-010")
    def test_default_creates_the_table(self, backend: SQLBlobBackend) -> None:
        """``create_table=True`` means the container exists the moment the backend does."""
        assert sa.inspect(backend._engine).has_table(_TABLE)

    @pytest.mark.spec("SQL-BLOB-012")
    def test_reflection_refuses_an_absent_table(self, tmp_path: Path) -> None:
        """``create_table=False`` cannot bind to a table that is not there."""
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        try:
            with pytest.raises(sa.exc.NoSuchTableError):
                SQLBlobBackend(engine=engine, table_name=_TABLE, create_table=False)
        finally:
            engine.dispose()
