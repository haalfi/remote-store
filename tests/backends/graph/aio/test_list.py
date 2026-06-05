"""GraphBackend listing path: iter_children, list_files/list_folders, folder info.

respx stubs ``httpx.AsyncClient`` so the real ``GraphBackend`` / ``iter_pages`` /
item-mapping code runs against canned ``/children`` collection responses
(GR-014 listing, GR-016 pagination). Recursion + ``max_depth`` precedence
(ASYNC-014) and the recursive folder-info aggregate (BE-017) are exercised
against a multi-level tree of mocked child endpoints.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from remote_store._errors import BackendUnavailable, InvalidPath, NotFound
from remote_store._models import FileInfo, FolderEntry
from remote_store.aio.backends._graph.backend import GraphBackend

_DRIVE = "b!driveid123"
_BASE = "https://graph.microsoft.com/v1.0"


def _make() -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok")


def _meta_url(path: str) -> str:
    """The item-metadata endpoint the backend GETs for *path*, via the real builder."""
    return _make()._item_url(path)


def _children_url(path: str) -> str:
    """The ``/children`` endpoint the backend lists, via the real URL builder."""
    return _make()._children_url(path)


def _file_child(name: str, size: int = 3) -> dict[str, object]:
    return {
        "name": name,
        "size": size,
        "lastModifiedDateTime": "2024-01-15T10:30:00Z",
        "eTag": f'"{{{name}}},1"',
        "file": {"mimeType": "text/plain"},
    }


def _folder_child(name: str) -> dict[str, object]:
    return {"name": name, "folder": {"childCount": 1}}


def _page(items: list[dict[str, object]], next_link: str | None = None) -> httpx.Response:
    body: dict[str, object] = {"value": items}
    if next_link is not None:
        body["@odata.nextLink"] = next_link
    return httpx.Response(200, json=body)


def _not_found() -> httpx.Response:
    return httpx.Response(404, json={"error": {"code": "itemNotFound"}})


class TestChildrenUrl:
    """GR-014: the drive root takes the bare ``/root/children`` form."""

    @pytest.mark.spec("GR-014")
    def test_root_uses_bare_children(self) -> None:
        assert _children_url("") == f"{_BASE}/drives/{_DRIVE}/root/children"

    @pytest.mark.spec("GR-014")
    def test_folder_uses_path_addressed_children(self) -> None:
        assert _children_url("a/b") == f"{_BASE}/drives/{_DRIVE}/root:/a/b:/children"


class TestIterChildren:
    """GR-014: single ``/children`` pass yields files and folders in order."""

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_interleaves_files_and_folders(self) -> None:
        respx.get(_children_url("d")).mock(
            return_value=_page([_folder_child("sub"), _file_child("a.txt"), _file_child("b.txt")])
        )
        async with _make() as backend:
            entries = [e async for e in backend.iter_children("d")]
        assert [type(e).__name__ for e in entries] == ["FolderEntry", "FileInfo", "FileInfo"]
        assert [str(e.path) for e in entries] == ["d/sub", "d/a.txt", "d/b.txt"]

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_missing_path_yields_nothing(self) -> None:
        respx.get(_children_url("gone")).mock(return_value=_not_found())
        async with _make() as backend:
            assert [e async for e in backend.iter_children("gone")] == []

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_skips_item_without_name(self) -> None:
        # A malformed driveItem with no ``name`` is defensively skipped.
        respx.get(_children_url("d")).mock(
            return_value=_page([{"file": {"mimeType": "text/plain"}}, _file_child("a.txt")])
        )
        async with _make() as backend:
            entries = [e async for e in backend.iter_children("d")]
        assert [str(e.path) for e in entries] == ["d/a.txt"]


class TestListFolders:
    """GR-014: list_folders yields only the folder-faceted children."""

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_only_folders(self) -> None:
        respx.get(_children_url("d")).mock(
            return_value=_page([_folder_child("sub"), _file_child("a.txt"), _folder_child("sub2")])
        )
        async with _make() as backend:
            folders = [f async for f in backend.list_folders("d")]
        assert all(isinstance(f, FolderEntry) for f in folders)
        assert {str(f.path) for f in folders} == {"d/sub", "d/sub2"}

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_file_path_yields_nothing(self) -> None:
        respx.get(_children_url("f.txt")).mock(return_value=_not_found())
        async with _make() as backend:
            assert [f async for f in backend.list_folders("f.txt")] == []


# DEPTH_TREE mirrored as a set of mocked /children endpoints:
#   pc/a.txt, pc/d1/b.txt, pc/d1/c.txt, pc/d1/d2/d.txt, pc/d1/d2/d3/e.txt
def _seed_depth_tree() -> None:
    respx.get(_children_url("pc")).mock(return_value=_page([_file_child("a.txt"), _folder_child("d1")]))
    respx.get(_children_url("pc/d1")).mock(
        return_value=_page([_file_child("b.txt"), _file_child("c.txt"), _folder_child("d2")])
    )
    respx.get(_children_url("pc/d1/d2")).mock(return_value=_page([_file_child("d.txt"), _folder_child("d3")]))
    respx.get(_children_url("pc/d1/d2/d3")).mock(return_value=_page([_file_child("e.txt")]))


class TestListFiles:
    """GR-014 / ASYNC-014: recursion and inclusive max_depth precedence."""

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_non_recursive_immediate_only(self) -> None:
        _seed_depth_tree()
        async with _make() as backend:
            files = [f async for f in backend.list_files("pc")]
        assert {f.name for f in files} == {"a.txt"}

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_skips_item_without_name(self) -> None:
        # The recursive walk defensively skips a child with no ``name``.
        respx.get(_children_url("d")).mock(
            return_value=_page([{"file": {"mimeType": "text/plain"}}, _file_child("a.txt")])
        )
        async with _make() as backend:
            files = [f async for f in backend.list_files("d")]
        assert {f.name for f in files} == {"a.txt"}

    @respx.mock
    @pytest.mark.spec("GR-014")
    async def test_recursive_unbounded(self) -> None:
        _seed_depth_tree()
        async with _make() as backend:
            files = [f async for f in backend.list_files("pc", recursive=True)]
        assert {f.name for f in files} == {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}
        assert all(isinstance(f, FileInfo) for f in files)

    @respx.mock
    @pytest.mark.spec("ASYNC-014")
    @pytest.mark.parametrize(
        ("max_depth", "expected"),
        [
            (0, {"a.txt"}),
            (1, {"a.txt", "b.txt", "c.txt"}),
            (2, {"a.txt", "b.txt", "c.txt", "d.txt"}),
            (3, {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}),
        ],
    )
    async def test_max_depth_inclusive(self, max_depth: int, expected: set[str]) -> None:
        _seed_depth_tree()
        async with _make() as backend:
            # recursive=False is ignored once max_depth is set (ASYNC-014 precedence).
            files = [f async for f in backend.list_files("pc", recursive=False, max_depth=max_depth)]
        assert {f.name for f in files} == expected


class TestPagination:
    """GR-016: follow @odata.nextLink; empty page + link is not the end."""

    @respx.mock
    @pytest.mark.spec("GR-016")
    async def test_follows_next_link(self) -> None:
        # A Graph @odata.nextLink is an opaque absolute URL — modelled here as a
        # distinct path so it cannot collide with the first /children route.
        nxt = f"{_BASE}/_page/p-skiptoken-PAGE2"
        respx.get(_children_url("p")).mock(return_value=_page([_file_child("f1.txt")], next_link=nxt))
        respx.get(nxt).mock(return_value=_page([_file_child("f2.txt")]))
        async with _make() as backend:
            files = [f async for f in backend.list_files("p")]
        assert {f.name for f in files} == {"f1.txt", "f2.txt"}

    @respx.mock
    @pytest.mark.spec("GR-016")
    async def test_empty_value_with_next_link_is_followed(self) -> None:
        nxt = f"{_BASE}/_page/p-skiptoken-PAGE2"
        respx.get(_children_url("p")).mock(return_value=_page([], next_link=nxt))
        respx.get(nxt).mock(return_value=_page([_file_child("f1.txt")]))
        async with _make() as backend:
            files = [f async for f in backend.list_files("p")]
        assert {f.name for f in files} == {"f1.txt"}

    @respx.mock
    @pytest.mark.spec("GR-016")
    async def test_malformed_next_link_raises(self) -> None:
        respx.get(_children_url("p")).mock(return_value=_page([_file_child("f1.txt")], next_link="not-a-url"))
        async with _make() as backend:
            with pytest.raises(BackendUnavailable):
                _ = [f async for f in backend.list_files("p")]


class TestGetFolderInfo:
    """BE-017 / ASYNC-017: recursive aggregate; file/missing path failures."""

    @respx.mock
    @pytest.mark.spec("ASYNC-017")
    async def test_recursive_aggregate(self) -> None:
        respx.get(_meta_url("fi")).mock(
            return_value=httpx.Response(
                200, json={"name": "fi", "folder": {}, "lastModifiedDateTime": "2024-01-15T10:30:00Z"}
            )
        )
        respx.get(_children_url("fi")).mock(return_value=_page([_file_child("a.txt", size=3), _folder_child("sub")]))
        respx.get(_children_url("fi/sub")).mock(return_value=_page([_file_child("b.txt", size=2)]))
        async with _make() as backend:
            info = await backend.get_folder_info("fi")
        assert info.file_count == 2
        assert info.total_size == 5
        assert info.modified_at is not None

    @respx.mock
    @pytest.mark.spec("ASYNC-017")
    async def test_on_file_raises_invalid_path(self) -> None:
        respx.get(_meta_url("f.txt")).mock(
            return_value=httpx.Response(200, json={"name": "f.txt", "size": 1, "file": {"mimeType": "text/plain"}})
        )
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="f.txt"):
                await backend.get_folder_info("f.txt")

    @respx.mock
    @pytest.mark.spec("ASYNC-017")
    async def test_missing_raises_not_found(self) -> None:
        respx.get(_meta_url("gone")).mock(return_value=_not_found())
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend.get_folder_info("gone")
