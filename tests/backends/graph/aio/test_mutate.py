"""GraphBackend mutate path: delete, delete_folder, copy, move + close() poller-cancel.

respx stubs ``httpx.AsyncClient`` so the real ``GraphBackend`` mutate methods and
the ``monitor.poll_monitor`` loop run against canned Graph responses: ``delete``
type-checks via one GET then DELETEs (GR-041); ``delete_folder`` honours
recursive/childCount/probe (GR-042/043); ``copy`` POSTs and awaits the 202 monitor
(GR-025/026); ``move`` PATCHes sync-or-async (GR-027); self-op short-circuits after
one GET (GR-044); destination ``409`` discriminates (BE-008); ``close()`` cancels a
pending poller (GR-051 poller-cancel half).
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from remote_store._config import RetryPolicy
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from remote_store.aio.backends._graph.backend import GraphBackend

if TYPE_CHECKING:
    from typing import Any

_DRIVE = "b!driveid123"
_BASE = "https://graph.microsoft.com/v1.0"
_MONITOR = "https://my.microsoftpersonalcontent.com/op/01ABC?tempauth=secret"

# Whole-URL regex routes (mirrors test_write.py): the item-address form ends at
# the trailing ':' (no query, no /copy suffix); copy appends '/copy'; move (PATCH)
# carries a conflictBehavior query.
_ITEM_RE = re.compile(re.escape(_BASE) + r"/drives/[^/]+/root:/[^:?]+:$")
_COPY_RE = re.compile(re.escape(_BASE) + r"/drives/[^/]+/root:/[^:]+:/copy(\?.*)?$")
_MOVE_RE = re.compile(re.escape(_BASE) + r"/drives/[^/]+/root:/[^:?]+:(\?.*)?$")

_FAST = RetryPolicy(max_attempts=3, backoff_base=0.0, backoff_max=0.0, jitter=0.0)


def _make(retry: RetryPolicy | None = None) -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok", retry=retry)


def _file_item(name: str = "a.txt", **extra: object) -> dict[str, Any]:
    item: dict[str, Any] = {"id": "01ITEM", "name": name, "size": 4, "file": {"mimeType": "text/plain"}}
    item.update(extra)
    return item


def _folder_item(name: str = "dir", child_count: int | None = 0, **extra: object) -> dict[str, Any]:
    folder: dict[str, Any] = {} if child_count is None else {"childCount": child_count}
    item: dict[str, Any] = {"id": "01FOLDER", "name": name, "folder": folder}
    item.update(extra)
    return item


# ===========================================================================
# delete() (GR-041)
# ===========================================================================


class TestDelete:
    @respx.mock
    @pytest.mark.spec("GR-041")
    async def test_delete_file_gets_then_deletes(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        delete = respx.delete(_ITEM_RE).mock(return_value=httpx.Response(204))
        async with _make() as backend:
            await backend.delete("a.txt")
        assert delete.called
        assert delete.calls.last.request.url.path == f"/v1.0/drives/{_DRIVE}/root:/a.txt:"

    @respx.mock
    @pytest.mark.spec("GR-041")
    async def test_delete_folder_path_raises_invalid_path(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item()))
        delete = respx.delete(_ITEM_RE).mock(return_value=httpx.Response(204))
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.delete("dir")
        assert not delete.called  # type mismatch: no DELETE issued

    @respx.mock
    @pytest.mark.spec("GR-041")
    async def test_delete_missing_raises_not_found(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend.delete("gone.txt")

    @respx.mock
    @pytest.mark.spec("GR-041")
    async def test_delete_missing_ok_swallows_not_found(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        delete = respx.delete(_ITEM_RE).mock(return_value=httpx.Response(204))
        async with _make() as backend:
            await backend.delete("gone.txt", missing_ok=True)
        assert not delete.called


# ===========================================================================
# delete_folder() (GR-042 recursive / GR-043 non-recursive)
# ===========================================================================


class TestDeleteFolder:
    @respx.mock
    @pytest.mark.spec("GR-042")
    async def test_recursive_single_delete(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item(child_count=5)))
        delete = respx.delete(_ITEM_RE).mock(return_value=httpx.Response(204))
        async with _make() as backend:
            await backend.delete_folder("dir", recursive=True)
        assert delete.called  # recursive deletes a non-empty folder in one call

    @respx.mock
    @pytest.mark.spec("GR-043")
    async def test_non_recursive_empty_deletes_via_childcount(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item(child_count=0)))
        delete = respx.delete(_ITEM_RE).mock(return_value=httpx.Response(204))
        async with _make() as backend:
            await backend.delete_folder("dir", recursive=False)
        assert delete.called

    @respx.mock
    @pytest.mark.spec("GR-043")
    async def test_non_recursive_nonempty_raises_directory_not_empty(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item(child_count=2)))
        delete = respx.delete(_ITEM_RE).mock(return_value=httpx.Response(204))
        async with _make() as backend:
            with pytest.raises(DirectoryNotEmpty):
                await backend.delete_folder("dir", recursive=False)
        assert not delete.called

    @respx.mock
    @pytest.mark.spec("GR-043")
    async def test_non_recursive_falls_back_to_children_probe_when_count_absent(self) -> None:
        # childCount absent -> probe /children; a child present -> DirectoryNotEmpty.
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item(child_count=None)))
        respx.get(re.compile(re.escape(_BASE) + r"/drives/[^/]+/root:/dir:/children$")).mock(
            return_value=httpx.Response(200, json={"value": [_file_item("child.txt")]})
        )
        async with _make() as backend:
            with pytest.raises(DirectoryNotEmpty):
                await backend.delete_folder("dir", recursive=False)

    @respx.mock
    @pytest.mark.spec("GR-043")
    async def test_non_recursive_probe_empty_deletes(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item(child_count=None)))
        respx.get(re.compile(re.escape(_BASE) + r"/drives/[^/]+/root:/dir:/children$")).mock(
            return_value=httpx.Response(200, json={"value": []})
        )
        delete = respx.delete(_ITEM_RE).mock(return_value=httpx.Response(204))
        async with _make() as backend:
            await backend.delete_folder("dir", recursive=False)
        assert delete.called

    @respx.mock
    @pytest.mark.spec("GR-043")
    async def test_delete_folder_on_file_raises_invalid_path(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="file"):
                await backend.delete_folder("a.txt")

    @respx.mock
    @pytest.mark.spec("GR-043")
    async def test_delete_folder_missing_ok(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            await backend.delete_folder("gone", missing_ok=True)
            with pytest.raises(NotFound):
                await backend.delete_folder("gone")


# ===========================================================================
# copy() (GR-025 + GR-026 monitor)
# ===========================================================================


class TestCopy:
    @respx.mock
    @pytest.mark.spec("GR-025")
    async def test_copy_posts_then_awaits_monitor_to_completion(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        post = respx.post(_COPY_RE).mock(return_value=httpx.Response(202, headers={"Location": _MONITOR}))
        monitor = respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"status": "completed"}))
        async with _make() as backend:
            await backend.copy("a.txt", "b.txt")
        assert post.called
        assert monitor.called
        assert backend._pending_pollers == set()  # poller deregistered after await

    @respx.mock
    @pytest.mark.spec("GR-056")
    async def test_copy_body_parent_reference_targets_configured_drive(self) -> None:
        import json as _json

        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        post = respx.post(_COPY_RE).mock(return_value=httpx.Response(202, headers={"Location": _MONITOR}))
        respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"status": "completed"}))
        async with _make() as backend:
            await backend.copy("a.txt", "sub/b.txt")
        req = post.calls.last.request
        body = _json.loads(req.content)
        # GR-056: there is no syntax to address another drive; parentReference
        # resolves against the one configured drive, with the dst parent by path.
        assert body["parentReference"]["driveId"] == _DRIVE
        assert body["parentReference"]["path"] == f"/drives/{_DRIVE}/root:/sub"
        assert body["name"] == "b.txt"
        # conflictBehavior rides the query on the copy action (live-verified: a
        # body field is ignored), not the body.
        assert "@microsoft.graph.conflictBehavior" not in body
        assert req.url.params["@microsoft.graph.conflictBehavior"] == "fail"

    @respx.mock
    @pytest.mark.spec("GR-025")
    async def test_copy_overwrite_maps_to_replace(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        post = respx.post(_COPY_RE).mock(return_value=httpx.Response(202, headers={"Location": _MONITOR}))
        respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"status": "completed"}))
        async with _make() as backend:
            await backend.copy("a.txt", "b.txt", overwrite=True)
        assert post.calls.last.request.url.params["@microsoft.graph.conflictBehavior"] == "replace"

    @respx.mock
    @pytest.mark.spec("GR-044")
    async def test_self_copy_short_circuits_after_one_get(self) -> None:
        get = respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        post = respx.post(_COPY_RE).mock(return_value=httpx.Response(202, headers={"Location": _MONITOR}))
        async with _make() as backend:
            await backend.copy("a.txt", "a.txt")
        assert get.call_count == 1  # one existence GET, then short-circuit
        assert not post.called

    @respx.mock
    @pytest.mark.spec("GR-044")
    async def test_self_copy_missing_src_raises_not_found(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend.copy("a.txt", "a.txt")

    @respx.mock
    @pytest.mark.spec("GR-025")
    async def test_copy_missing_src_raises_not_found(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(404, json={"error": {"code": "itemNotFound"}}))
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend.copy("a.txt", "b.txt")

    @respx.mock
    @pytest.mark.spec("GR-025")
    async def test_copy_folder_src_raises_invalid_path(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item()))
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.copy("dir", "b.txt")

    @respx.mock
    @pytest.mark.spec("GR-025")
    async def test_copy_destination_conflict_409_discriminates_already_exists(self) -> None:
        # Live-verified: a copy to an existing dst with conflictBehavior=fail
        # returns a SYNCHRONOUS 409 (not an async monitor failure).
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.post(_COPY_RE).mock(return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}}))
        async with _make() as backend:
            with pytest.raises(AlreadyExists):
                await backend.copy("a.txt", "b.txt")

    @respx.mock
    @pytest.mark.spec("GR-025")
    async def test_copy_destination_folder_409_discriminates_invalid_path(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.post(_COPY_RE).mock(
            return_value=httpx.Response(
                409, json={"error": {"code": "nameAlreadyExists", "details": [{"name": "b.txt", "folder": {}}]}}
            )
        )
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.copy("a.txt", "b.txt")

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_copy_202_without_location_is_backend_unavailable(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.post(_COPY_RE).mock(return_value=httpx.Response(202))  # no Location header
        async with _make() as backend:
            with pytest.raises(BackendUnavailable, match="Location"):
                await backend.copy("a.txt", "b.txt")

    @respx.mock
    @pytest.mark.spec("GR-026")
    async def test_copy_monitor_failure_propagates(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.post(_COPY_RE).mock(return_value=httpx.Response(202, headers={"Location": _MONITOR}))
        respx.get(_MONITOR).mock(
            return_value=httpx.Response(200, json={"status": "failed", "error": {"code": "itemNotFound"}})
        )
        async with _make() as backend:
            with pytest.raises(NotFound):
                await backend.copy("a.txt", "b.txt")
        assert backend._pending_pollers == set()  # deregistered even on failure


# ===========================================================================
# move() (GR-027)
# ===========================================================================


class TestMove:
    @respx.mock
    @pytest.mark.spec("GR-027")
    async def test_move_sync_200_no_poll(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        patch = respx.patch(_MOVE_RE).mock(return_value=httpx.Response(200, json=_file_item("b.txt")))
        async with _make() as backend:
            await backend.move("a.txt", "b.txt")
        assert patch.called
        assert patch.calls.last.request.url.params["@microsoft.graph.conflictBehavior"] == "fail"

    @respx.mock
    @pytest.mark.spec("GR-027")
    async def test_move_overwrite_maps_to_replace(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        patch = respx.patch(_MOVE_RE).mock(return_value=httpx.Response(200, json=_file_item("b.txt")))
        async with _make() as backend:
            await backend.move("a.txt", "b.txt", overwrite=True)
        assert patch.calls.last.request.url.params["@microsoft.graph.conflictBehavior"] == "replace"

    @respx.mock
    @pytest.mark.spec("GR-027")
    async def test_move_async_202_awaits_monitor(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.patch(_MOVE_RE).mock(return_value=httpx.Response(202, headers={"Location": _MONITOR}))
        monitor = respx.get(_MONITOR).mock(return_value=httpx.Response(200, json={"status": "completed"}))
        async with _make() as backend:
            await backend.move("a.txt", "big/b.txt")
        assert monitor.called

    @respx.mock
    @pytest.mark.spec("GR-027")
    async def test_move_request_body_parent_and_name(self) -> None:
        import json as _json

        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        patch = respx.patch(_MOVE_RE).mock(return_value=httpx.Response(200, json=_file_item("b.txt")))
        async with _make() as backend:
            await backend.move("a.txt", "sub/b.txt")
        body = _json.loads(patch.calls.last.request.content)
        assert body["parentReference"]["path"] == f"/drives/{_DRIVE}/root:/sub"
        assert body["name"] == "b.txt"
        # move carries conflictBehavior as a query param, not in the body.
        assert "@microsoft.graph.conflictBehavior" not in body

    @respx.mock
    @pytest.mark.spec("GR-044")
    async def test_self_move_short_circuits_after_one_get(self) -> None:
        get = respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        patch = respx.patch(_MOVE_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        async with _make() as backend:
            await backend.move("a.txt", "a.txt")
        assert get.call_count == 1
        assert not patch.called

    @respx.mock
    @pytest.mark.spec("GR-027")
    async def test_move_folder_src_raises_invalid_path(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_folder_item()))
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="folder"):
                await backend.move("dir", "b.txt")

    @respx.mock
    @pytest.mark.spec("GR-027")
    async def test_move_destination_conflict_409_discriminates(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.patch(_MOVE_RE).mock(return_value=httpx.Response(409, json={"error": {"code": "nameAlreadyExists"}}))
        async with _make() as backend:
            with pytest.raises(AlreadyExists):
                await backend.move("a.txt", "b.txt")

    @respx.mock
    @pytest.mark.spec("GR-027")
    async def test_move_ancestor_file_409_discriminates_invalid_path(self) -> None:
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.patch(_MOVE_RE).mock(
            return_value=httpx.Response(
                409, json={"error": {"code": "nameAlreadyExists", "details": [{"name": "parent", "file": {}}]}}
            )
        )
        async with _make() as backend:
            with pytest.raises(InvalidPath, match="ancestor"):
                await backend.move("a.txt", "parent/b.txt")


# ===========================================================================
# close() poller-cancel half (GR-051)
# ===========================================================================


class TestClosePollerCancel:
    @respx.mock
    @pytest.mark.spec("GR-051")
    async def test_close_cancels_pending_poller(self) -> None:
        # Mirrors the session-abort test: register a never-terminal poller task and
        # assert close() cancels it without leaking the task or raising.
        backend = _make()

        async def _never() -> None:
            await asyncio.Event().wait()

        task: asyncio.Task[None] = asyncio.ensure_future(_never())
        backend._pending_pollers.add(task)
        await backend.aclose()
        assert task.cancelled()
        assert backend._pending_pollers == set()

    @respx.mock
    @pytest.mark.spec("GR-051")
    async def test_close_during_inflight_copy_cancels_the_copy(self) -> None:
        # A real copy mid-poll (monitor never completes); close() cancels the
        # registered poller, which surfaces as CancelledError out of copy().
        respx.get(_ITEM_RE).mock(return_value=httpx.Response(200, json=_file_item()))
        respx.post(_COPY_RE).mock(return_value=httpx.Response(202, headers={"Location": _MONITOR}))
        respx.get(_MONITOR).mock(return_value=httpx.Response(202, json={"status": "inProgress"}))
        backend = _make()
        copy_task = asyncio.ensure_future(backend.copy("a.txt", "b.txt"))
        while not backend._pending_pollers:
            await asyncio.sleep(0)  # let copy() reach the poll loop
        await backend.aclose()
        with pytest.raises(asyncio.CancelledError):
            await copy_task
        assert backend._pending_pollers == set()
