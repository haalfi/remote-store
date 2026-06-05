"""GraphUtils.resolve_drive_id — the three GR-057 target shapes (respx).

The ``"me"`` shape is additionally reality-checked against live Graph in the
GR-CORE PR; the SharePoint-site and Teams-channel shapes require app-only auth
(unavailable on the consumer test tenant) and are respx/unit-only here.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from remote_store._errors import InvalidPath
from remote_store.aio.backends._graph.utils import GraphUtils

_BASE = "https://graph.microsoft.com/v1.0"


class TestResolveDriveId:
    @respx.mock
    @pytest.mark.spec("GR-057")
    async def test_me_shape(self) -> None:
        respx.get(f"{_BASE}/me/drive").mock(return_value=httpx.Response(200, json={"id": "drive-me"}))
        assert await GraphUtils.aresolve_drive_id("me", token_provider=lambda: "t") == "drive-me"

    @respx.mock
    @pytest.mark.spec("GR-057")
    async def test_sharepoint_bare_site_url(self) -> None:
        site = "https://contoso.sharepoint.com/sites/marketing"
        respx.get(f"{_BASE}/sites/contoso.sharepoint.com:/sites/marketing").mock(
            return_value=httpx.Response(200, json={"id": "site-1"})
        )
        respx.get(f"{_BASE}/sites/site-1/drive").mock(return_value=httpx.Response(200, json={"id": "drive-default"}))
        assert await GraphUtils.aresolve_drive_id(site, token_provider=lambda: "t") == "drive-default"

    @respx.mock
    @pytest.mark.spec("GR-057")
    async def test_sharepoint_named_library(self) -> None:
        site = "https://contoso.sharepoint.com/sites/marketing"
        respx.get(f"{_BASE}/sites/contoso.sharepoint.com:/sites/marketing").mock(
            return_value=httpx.Response(200, json={"id": "site-1"})
        )
        respx.get(f"{_BASE}/sites/site-1/drives").mock(
            return_value=httpx.Response(
                200, json={"value": [{"name": "Documents", "id": "d1"}, {"name": "Reports", "id": "d2"}]}
            )
        )
        got = await GraphUtils.aresolve_drive_id((site, "Reports"), token_provider=lambda: "t")
        assert got == "d2"

    @respx.mock
    @pytest.mark.spec("GR-057")
    async def test_teams_channel(self) -> None:
        respx.get(f"{_BASE}/teams/team-1/channels/chan-1/filesFolder").mock(
            return_value=httpx.Response(200, json={"parentReference": {"driveId": "drive-teams"}})
        )
        got = await GraphUtils.aresolve_drive_id(
            {"team_id": "team-1", "channel_id": "chan-1"}, token_provider=lambda: "t"
        )
        assert got == "drive-teams"

    @respx.mock
    @pytest.mark.spec("GR-057")
    async def test_named_library_not_found_is_invalid_path(self) -> None:
        site = "https://contoso.sharepoint.com/sites/marketing"
        respx.get(f"{_BASE}/sites/contoso.sharepoint.com:/sites/marketing").mock(
            return_value=httpx.Response(200, json={"id": "site-1"})
        )
        respx.get(f"{_BASE}/sites/site-1/drives").mock(
            return_value=httpx.Response(200, json={"value": [{"name": "Documents", "id": "d1"}]})
        )
        with pytest.raises(InvalidPath, match="document library"):
            await GraphUtils.aresolve_drive_id((site, "Missing"), token_provider=lambda: "t")

    @pytest.mark.spec("GR-057")
    @pytest.mark.parametrize("target", ["not-me", "ftp://x/y", 123, {"team_id": "t"}])
    async def test_unrecognised_target_is_invalid_path(self, target: object) -> None:
        with pytest.raises(InvalidPath):
            await GraphUtils.aresolve_drive_id(target, token_provider=lambda: "t")  # type: ignore[arg-type]

    @pytest.mark.spec("GR-057")
    async def test_http_url_without_host_is_invalid_path(self) -> None:
        with pytest.raises(InvalidPath, match="SharePoint site URL"):
            await GraphUtils.aresolve_drive_id("https://", token_provider=lambda: "t")

    @respx.mock
    @pytest.mark.spec("GR-057")
    def test_sync_wrapper_runs_under_private_loop(self) -> None:
        # The sync entry point drives the async core via asyncio.run; respx
        # patches httpx at the transport layer, so it intercepts the fresh loop.
        respx.get(f"{_BASE}/me/drive").mock(return_value=httpx.Response(200, json={"id": "drive-sync"}))
        assert GraphUtils.resolve_drive_id("me", token_provider=lambda: "t") == "drive-sync"
