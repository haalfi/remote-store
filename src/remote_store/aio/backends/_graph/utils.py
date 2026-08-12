"""``GraphUtils`` — the ``resolve_drive_id`` on-ramp helper.

Citizen developers rarely hold a raw ``drive_id``; they have "my OneDrive", a
SharePoint site URL, or a Teams channel. ``GraphUtils.resolve_drive_id`` turns
each of those three shapes into the opaque ``drive.id`` string that
``GraphBackend(drive_id=...)`` requires. ``GraphUtils`` is a namespace class of
``@staticmethod`` helpers, mirroring ``SFTPUtils`` (``backends/_sftp.py``).

The sync ``resolve_drive_id`` is a one-shot application-wiring entry point; it
runs the async resolution under a private event loop (``asyncio.run``). Callers
already inside an event loop use the async counterpart ``aresolve_drive_id``
directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from remote_store._errors import InvalidPath
from remote_store.aio.backends._graph.http import BACKEND_NAME, graph_send, iter_pages

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    TokenProvider = Callable[[], str] | Callable[[], Awaitable[str]]

_DEFAULT_BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphUtils:
    """Namespace for Graph configuration helpers.

    Carries only ``@staticmethod`` helpers; it is never instantiated. Lives in
    a namespace class rather than on ``GraphBackend`` so it is usable without
    constructing a backend, and so future configuration probes have a home that
    does not crowd the top-level package namespace.
    """

    @staticmethod
    def resolve_drive_id(
        target: str | tuple[str, str] | Mapping[str, str],
        *,
        token_provider: TokenProvider,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> str:
        """Resolve a ``drive_id`` from one of the three target shapes.

        Sync entry point for application wiring; runs ``aresolve_drive_id``
        under a private event loop. See ``aresolve_drive_id`` for the accepted
        shapes and raised errors.
        """
        return asyncio.run(
            GraphUtils.aresolve_drive_id(
                target, token_provider=token_provider, http_client=http_client, base_url=base_url
            )
        )

    @staticmethod
    async def aresolve_drive_id(
        target: str | tuple[str, str] | Mapping[str, str],
        *,
        token_provider: TokenProvider,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> str:
        """Resolve a ``drive_id`` from one of three target shapes.

        Accepted shapes:

        - ``"me"`` — the authenticated user's default drive (``GET /me/drive``).
        - a SharePoint site URL ``str`` — the site's default drive; or a
          ``(site_url, library_name)`` tuple — the named document library.
        - a ``{"team_id": ..., "channel_id": ...}`` mapping — a Teams
          channel's backing drive.

        Args:
            target: One of the shapes above.
            token_provider: Bearer-token callable (sync or async).
            http_client: Reuse an existing client; one is created and closed
                per call when omitted.
            base_url: Graph API root.

        Returns:
            The opaque Graph ``drive.id`` string.

        Raises:
            InvalidPath: If ``target`` matches no accepted shape, the SharePoint
                site URL has no host, or the named library does not exist.
            NotFound: If a site/team/channel id resolves but returns ``404``.
            PermissionDenied: If Graph returns ``403`` for the lookup.
            BackendUnavailable: If Graph reports the target as a drive-identity
                failure (``404 resourceNotFound``) — these lookups resolve a
                drive rather than address a path, so a resource that is not
                there is a configuration error, not an absence. Also for a
                transport error, a retryable ``5xx`` / ``429`` / ``507``, or a
                malformed ``@odata.nextLink`` while paging a site's document
                libraries.
        """
        client = http_client if http_client is not None else httpx.AsyncClient()
        owns_client = http_client is None
        try:
            if isinstance(target, str):
                if target == "me":
                    return await _drive_id_from_me(client, base_url, token_provider)
                if target.startswith(("http://", "https://")):
                    site_id = await _site_id_from_url(client, base_url, target, token_provider)
                    return await _default_drive_id(client, base_url, site_id, token_provider)
                raise InvalidPath(f"Unrecognised resolve_drive_id target: {target!r}", backend=BACKEND_NAME)
            if isinstance(target, tuple) and len(target) == 2 and all(isinstance(x, str) for x in target):
                site_url, library_name = target
                site_id = await _site_id_from_url(client, base_url, site_url, token_provider)
                return await _named_drive_id(client, base_url, site_id, library_name, token_provider)
            if isinstance(target, Mapping) and {"team_id", "channel_id"} <= set(target.keys()):
                return await _drive_id_from_channel(
                    client, base_url, target["team_id"], target["channel_id"], token_provider
                )
            raise InvalidPath(f"Unrecognised resolve_drive_id target: {target!r}", backend=BACKEND_NAME)
        finally:
            if owns_client:
                await client.aclose()


# Drive-identity resolution runs before any backend exists and addresses no
# caller-supplied store path, so the absent-container contract does not reach it
# (ADR-0038) and Graph's own drive-identity rule governs: all *five* lookups
# below send at scope="identity", keeping a `404 resourceNotFound` mapped to
# BackendUnavailable. Left at the item default they silently start reporting an
# unresolvable drive as NotFound.
#
# Count the legs, do not count the graph_send calls: _named_drive_id reaches the
# classifier through iter_pages rather than directly, which is how it was missed
# once already.
#
# tests/backends/graph/aio/test_utils.py holds both halves of that, because a
# hand-written table can only catch the half it lists. A listed leg downgraded to
# the item default fails its own cell in the (leg x 404 code) product; a *sixth*
# leg added with no cell at all fails
# test_every_dispatch_call_site_sends_at_identity_scope, which reads this
# module's call sites instead of a list.
async def _drive_id_from_me(client: httpx.AsyncClient, base_url: str, token_provider: TokenProvider) -> str:
    response = await graph_send(
        client, "GET", f"{base_url}/me/drive", token_provider=token_provider, path="me/drive", scope="identity"
    )
    return str(response.json()["id"])


async def _site_id_from_url(
    client: httpx.AsyncClient, base_url: str, site_url: str, token_provider: TokenProvider
) -> str:
    parsed = urlparse(site_url)
    if not parsed.netloc:
        raise InvalidPath(f"Not a valid SharePoint site URL: {site_url!r}", backend=BACKEND_NAME)
    server_relative = parsed.path or "/"
    # Graph addresses a site by hostname + server-relative path: /sites/{host}:{path}
    url = f"{base_url}/sites/{parsed.netloc}:{server_relative}"
    response = await graph_send(client, "GET", url, token_provider=token_provider, path=site_url, scope="identity")
    return str(response.json()["id"])


async def _default_drive_id(
    client: httpx.AsyncClient, base_url: str, site_id: str, token_provider: TokenProvider
) -> str:
    response = await graph_send(
        client,
        "GET",
        f"{base_url}/sites/{site_id}/drive",
        token_provider=token_provider,
        path=site_id,
        scope="identity",
    )
    return str(response.json()["id"])


async def _named_drive_id(
    client: httpx.AsyncClient, base_url: str, site_id: str, library_name: str, token_provider: TokenProvider
) -> str:
    url = f"{base_url}/sites/{site_id}/drives"
    async for page in iter_pages(client, url, token_provider=token_provider, path=site_id, scope="identity"):
        for drive in page.get("value", []):
            if drive.get("name") == library_name:
                return str(drive["id"])
    raise InvalidPath(f"No document library named {library_name!r} on site {site_id!r}", backend=BACKEND_NAME)


async def _drive_id_from_channel(
    client: httpx.AsyncClient, base_url: str, team_id: str, channel_id: str, token_provider: TokenProvider
) -> str:
    url = f"{base_url}/teams/{team_id}/channels/{channel_id}/filesFolder"
    response = await graph_send(
        client, "GET", url, token_provider=token_provider, path=f"{team_id}/{channel_id}", scope="identity"
    )
    return str(response.json()["parentReference"]["driveId"])
