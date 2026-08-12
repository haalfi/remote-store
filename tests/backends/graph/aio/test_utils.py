"""GraphUtils.resolve_drive_id — the three GR-057 target shapes (respx).

The ``"me"`` shape is additionally reality-checked against live Graph in the
GR-CORE PR; the SharePoint-site and Teams-channel shapes require app-only auth
(unavailable on the consumer test tenant) and are respx/unit-only here.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple

import httpx
import pytest
import respx

import remote_store
from remote_store._errors import BackendUnavailable, InvalidPath, NotFound
from remote_store.aio.backends._graph.utils import GraphUtils

_BASE = "https://graph.microsoft.com/v1.0"

_SITE = "https://contoso.sharepoint.com/sites/marketing"
_SITE_URL = f"{_BASE}/sites/contoso.sharepoint.com:/sites/marketing"


class _Leg(NamedTuple):
    """One 404-classifying call site inside ``resolve_drive_id``.

    ``ok_urls`` are the legs that must succeed for control to reach this one, so
    each entry isolates exactly one lookup.

    This list is hand-written, so on its own it can only catch a *listed* leg
    that regresses — the case that shipped once already. It cannot see a leg
    added without a row, which is the same blind spot in a different coat.
    ``test_every_dispatch_call_site_sends_at_identity_scope`` closes that half by
    reading the module rather than this list; the two together are what make the
    count trustworthy.
    """

    name: str
    target: object
    failing_url: str
    ok_urls: tuple[str, ...] = ()
    ok_body: dict[str, object] = {"id": "site-1"}  # noqa: RUF012 — immutable in practice; NamedTuple default


_LEGS = [
    _Leg("drive_id_from_me", "me", f"{_BASE}/me/drive"),
    _Leg("site_id_from_url", _SITE, _SITE_URL),
    _Leg("default_drive_id", _SITE, f"{_BASE}/sites/site-1/drive", ok_urls=(_SITE_URL,)),
    # Reaches the classifier through iter_pages, not graph_send — the leg a
    # graph_send-shaped sweep misses.
    _Leg("named_drive_id", (_SITE, "Reports"), f"{_BASE}/sites/site-1/drives", ok_urls=(_SITE_URL,)),
    _Leg(
        "drive_id_from_channel",
        {"team_id": "team-1", "channel_id": "chan-1"},
        f"{_BASE}/teams/team-1/channels/chan-1/filesFolder",
    ),
]


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
    @pytest.mark.spec("GR-057", "GR-031")
    @pytest.mark.parametrize("code", ["resourceNotFound", "itemNotFound"])
    @pytest.mark.parametrize("leg", _LEGS, ids=[leg.name for leg in _LEGS])
    async def test_404_discriminates_by_error_code_on_every_leg(self, leg: _Leg, code: str) -> None:
        # Drive resolution addresses no caller-supplied store path, so the
        # absent-container rule that flattens a data-plane 404 to NotFound does
        # not reach it and the drive-identity code still escalates.
        #
        # Enumerated over every leg rather than sampled, because sampling missed
        # one: _named_drive_id reaches the classifier through iter_pages instead
        # of calling graph_send itself, so a fix applied to "every graph_send in
        # this module" left it behind, and the two answers differ only by
        # error.code — every success-path cell above passes either way. The
        # product of (leg x code) is small and exactly enumerable, so it is
        # enumerated.
        for url in leg.ok_urls:
            respx.get(url).mock(return_value=httpx.Response(200, json=leg.ok_body))
        respx.get(leg.failing_url).mock(return_value=httpx.Response(404, json={"error": {"code": code}}))
        expected = BackendUnavailable if code == "resourceNotFound" else NotFound
        with pytest.raises(expected):
            await GraphUtils.aresolve_drive_id(leg.target, token_provider=lambda: "t")

    @pytest.mark.spec("GR-057", "GR-031")
    def test_every_dispatch_call_site_sends_at_identity_scope(self) -> None:
        # The half _LEGS cannot cover: read the module's own call sites instead
        # of a hand-written list, so a *sixth* leg added without a row fails here
        # rather than shipping. That is exactly how the fifth leg got in — the
        # sweep that fixed the other four was shaped by the call name, and
        # _named_drive_id reaches the classifier through iter_pages.
        #
        # Both dispatch helpers count. Keying on the call name is the mistake
        # this test exists to stop repeating, so it asserts over the union.
        source = (Path(remote_store.__file__).parent / "aio/backends/_graph/utils.py").read_text(encoding="utf-8")
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"graph_send", "iter_pages"}
        ]
        assert len(calls) == len(_LEGS), (
            f"utils.py dispatches {len(calls)} 404-classifying calls but _LEGS has "
            f"{len(_LEGS)} rows — add the missing leg to _LEGS, or remove the stale row"
        )
        scopes = {
            call.lineno: next(
                (kw.value.value for kw in call.keywords if kw.arg == "scope" and isinstance(kw.value, ast.Constant)),
                None,
            )
            for call in calls
        }
        assert set(scopes.values()) == {"identity"}, (
            f'every drive-identity lookup must send at scope="identity"; the item default flattens '
            f"a drive-identity 404 to NotFound. By utils.py line number: {scopes}"
        )

    @respx.mock
    @pytest.mark.spec("GR-057")
    def test_sync_wrapper_runs_under_private_loop(self) -> None:
        # The sync entry point drives the async core via asyncio.run; respx
        # patches httpx at the transport layer, so it intercepts the fresh loop.
        respx.get(f"{_BASE}/me/drive").mock(return_value=httpx.Response(200, json={"id": "drive-sync"}))
        assert GraphUtils.resolve_drive_id("me", token_provider=lambda: "t") == "drive-sync"
