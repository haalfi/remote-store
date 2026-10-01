"""BUG-296: the depth path of get_folder_info skips the unknown-time sentinel.

A file whose ``modified_at`` is unknown carries the sentinel. The folder's
``modified_at`` is the latest *known* file time, or ``None`` when none is
known, on the depth-limited path as on the plain call (FOLDERINFO-001).

File-backed SQLite: the async Store runs sync calls on worker threads, and a
``:memory:`` database is per-connection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa

from remote_store._store import Store
from remote_store.aio import AsyncStore
from remote_store.backends._sqlalchemy import SQLBlobBackend

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator


def _engine(tmp_path: pathlib.Path, *, with_mtime: bool) -> sa.Engine:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'blob.db'}")
    cols = [sa.Column("key", sa.Text, primary_key=True), sa.Column("data", sa.LargeBinary, nullable=False)]
    if with_mtime:
        # Nullable, so a row can hold an unknown time beside known ones.
        cols.append(sa.Column("modified_at", sa.Float, nullable=True))
    sa.Table("objs", sa.MetaData(), *cols).create(engine)
    return engine


@pytest.fixture
def no_mtime(tmp_path: pathlib.Path) -> Iterator[SQLBlobBackend]:
    """Table without a ``modified_at`` column: every file carries the sentinel."""
    engine = _engine(tmp_path, with_mtime=False)
    b = SQLBlobBackend(engine=engine, table_name="objs", create_table=False)
    b.write("d/a.txt", b"a")
    b.write("d/sub/b.txt", b"bb")
    yield b
    b.close()
    engine.dispose()


@pytest.fixture
def mixed(tmp_path: pathlib.Path) -> Iterator[SQLBlobBackend]:
    """One known time and one unknown (NULL) time under the same folder."""
    engine = _engine(tmp_path, with_mtime=True)
    b = SQLBlobBackend(engine=engine, table_name="objs", create_table=False)
    b.write("d/a.txt", b"a")
    b.write("d/sub/b.txt", b"bb")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE objs SET modified_at = NULL WHERE key = 'd/sub/b.txt'"))
    yield b
    b.close()
    engine.dispose()


@pytest.mark.spec("FOLDERINFO-001")
@pytest.mark.parametrize("max_depth", [0, 5])
def test_no_known_time_answers_none(no_mtime: SQLBlobBackend, max_depth: int) -> None:
    store = Store(backend=no_mtime)
    assert store.get_folder_info("d").modified_at is None
    assert store.get_folder_info("d", max_depth=max_depth).modified_at is None


@pytest.mark.spec("FOLDERINFO-001")
@pytest.mark.parametrize("max_depth", [0, 5])
async def test_async_no_known_time_answers_none(no_mtime: SQLBlobBackend, max_depth: int) -> None:
    store = AsyncStore(no_mtime)
    assert (await store.get_folder_info("d")).modified_at is None
    assert (await store.get_folder_info("d", max_depth=max_depth)).modified_at is None


@pytest.mark.spec("FOLDERINFO-001")
def test_known_time_wins_over_sentinel(mixed: SQLBlobBackend) -> None:
    store = Store(backend=mixed)
    known = store.get_file_info("d/a.txt").modified_at
    plain = store.get_folder_info("d")
    depth = store.get_folder_info("d", max_depth=5)
    assert depth.file_count == 2
    assert plain.modified_at == known
    assert depth.modified_at == known


@pytest.mark.spec("FOLDERINFO-001")
async def test_async_known_time_wins_over_sentinel(mixed: SQLBlobBackend) -> None:
    store = AsyncStore(mixed)
    known = (await store.get_file_info("d/a.txt")).modified_at
    plain = await store.get_folder_info("d")
    depth = await store.get_folder_info("d", max_depth=5)
    assert depth.file_count == 2
    assert plain.modified_at == known
    assert depth.modified_at == known
