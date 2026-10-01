"""BUG-296: the depth path of get_folder_info skips the unknown-time sentinel.

SQLQueryBackend files carry the sentinel, so no file time is known and both
the plain and the depth-limited call answer ``None`` (FOLDERINFO-001).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._store import Store
from remote_store.aio import AsyncStore
from remote_store.backends._sqlalchemy import SQLQueryBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

_QUERIES = {
    "reports/a.parquet": "SELECT 1 AS x",
    "reports/deep/b.parquet": "SELECT 2 AS x",
}


@pytest.fixture
def backend() -> Iterator[SQLQueryBackend]:
    b = SQLQueryBackend(url="sqlite:///:memory:", queries=_QUERIES)
    yield b
    b.close()


@pytest.mark.spec("FOLDERINFO-001")
@pytest.mark.parametrize("max_depth", [0, 5])
def test_depth_path_answers_none_like_plain_call(backend: SQLQueryBackend, max_depth: int) -> None:
    store = Store(backend=backend)
    plain = store.get_folder_info("reports")
    depth = store.get_folder_info("reports", max_depth=max_depth)
    assert plain.modified_at is None
    assert depth.modified_at is None
    assert depth.file_count == (1 if max_depth == 0 else 2)


@pytest.mark.spec("FOLDERINFO-001")
@pytest.mark.parametrize("max_depth", [0, 5])
async def test_async_depth_path_answers_none_like_plain_call(backend: SQLQueryBackend, max_depth: int) -> None:
    store = AsyncStore(backend)
    plain = await store.get_folder_info("reports")
    depth = await store.get_folder_info("reports", max_depth=max_depth)
    assert plain.modified_at is None
    assert depth.modified_at is None
    assert depth.file_count == (1 if max_depth == 0 else 2)
