"""HTTP request primitive, Microsoft Graph error mapping, and credential masking.

Centralises the three concerns the rest of the Graph sub-package shares: a
single ``graph_send`` request helper that attaches the bearer token and maps
non-2xx responses to ``remote_store`` errors, the status-plus-``error.code``
mapping table, pagination over ``@odata.nextLink``, and ``Authorization``-header
redaction.

String matching on Graph error *messages* is deliberately avoided;
classification keys on the HTTP status plus the structured ``error.code``
field only.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

import httpx

from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
    ResourceLocked,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

    TokenProvider = Callable[[], str] | Callable[[], Awaitable[str]]

BACKEND_NAME = "graph"
"""The backend ``name``; set on every mapped error."""

_REDACTED = "***"
_SENSITIVE_HEADERS = frozenset({"authorization"})

# Transport-level httpx failures (connect/read/write timeouts, DNS, resets)
# map to BackendUnavailable per GR-033 — the request never reached a status.
_TRANSPORT_ERRORS = (httpx.TransportError,)

log = logging.getLogger("remote_store.aio.backends._graph")


# ---------------------------------------------------------------------------
# Credential masking (GR-035)
# ---------------------------------------------------------------------------


def mask_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of *headers* with sensitive values replaced by ``"***"``.

    The ``Authorization`` bearer token must never reach a log record or an
    exception message. Any backend code that logs request/response headers
    routes them through this helper first.
    """
    return {k: (_REDACTED if k.lower() in _SENSITIVE_HEADERS else v) for k, v in headers.items()}


# ---------------------------------------------------------------------------
# Error mapping (GR-028 .. GR-034, GR-045, GR-054)
# ---------------------------------------------------------------------------


def error_code(body: object) -> str | None:
    """Extract the Graph ``error.code`` string from a parsed JSON body.

    Returns ``None`` when the body is not a Graph error envelope (no
    ``{"error": {"code": ...}}`` shape), which the caller treats as an
    unclassifiable response.
    """
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            if isinstance(code, str):
                return code
    return None


def classify_graph_error(
    status: int,
    code: str | None,
    *,
    path: str = "",
    backend: str = BACKEND_NAME,
    scope: Literal["item", "drive"] = "item",
) -> RemoteStoreError:
    """Map an HTTP status plus Graph ``error.code`` to a ``remote_store`` error.

    The single mapping table for the backend. ``scope`` disambiguates the
    ``404`` case: an item/path-scoped ``itemNotFound`` is a per-item
    ``NotFound``, while a drive-scoped ``404`` (or ``resourceNotFound``) is a
    backend-identity failure mapped to ``BackendUnavailable``.

    Never inspects the error *message* — only ``status`` and ``code``.
    """
    if status == 401:
        # GR-029: a refresh+retry is the caller's job (graph_send); by the time
        # an error is being classified the token is valid but insufficient.
        return PermissionDenied(f"Permission denied: {path}", path=path, backend=backend)
    if status == 403:  # GR-030 accessDenied
        return PermissionDenied(f"Permission denied: {path}", path=path, backend=backend)
    if status == 404:  # GR-031 item-vs-drive discrimination
        if scope == "drive" or code == "resourceNotFound":
            return BackendUnavailable(
                f"Drive unavailable (404 {code or 'notFound'}): {path}", path=path, backend=backend
            )
        return NotFound(f"Not found: {path}", path=path, backend=backend)
    if status == 409:  # GR-032 nameAlreadyExists
        return AlreadyExists(f"Already exists: {path}", path=path, backend=backend)
    if status == 423:  # GR-045 resourceLocked (ERR-013, ADR-0024)
        return ResourceLocked(f"Resource locked: {path}", path=path, backend=backend)
    if status == 429:  # GR-034 activityLimitReached
        return BackendUnavailable(
            f"Throttled (429 {code or 'activityLimitReached'}): {path}", path=path, backend=backend
        )
    if status == 507 or code == "quotaLimitReached":  # GR-054
        return BackendUnavailable(
            f"Insufficient storage (507 {code or 'quotaLimitReached'}): {path}", path=path, backend=backend
        )
    if status in (500, 502, 503, 504):  # GR-033 5xx
        return BackendUnavailable(f"Backend unavailable ({status}): {path}", path=path, backend=backend)
    # Any other non-2xx is an unclassified Graph contract surface; surface it
    # as a generic backend error rather than guessing a more specific type.
    return RemoteStoreError(f"Graph request failed ({status} {code or 'unknown'}): {path}", path=path, backend=backend)


def _parse_error(response: httpx.Response) -> str | None:
    """Best-effort extraction of ``error.code`` from a response body."""
    try:
        return error_code(response.json())
    except (ValueError, httpx.DecodingError):  # non-JSON / empty body
        return None


# ---------------------------------------------------------------------------
# Token acquisition (GR-008) and the request primitive (GR-028, GR-029)
# ---------------------------------------------------------------------------


async def acquire_token(token_provider: TokenProvider) -> str:
    """Invoke *token_provider*, awaiting it when it is an async callable.

    Supports both ``Callable[[], str]`` and ``Callable[[], Awaitable[str]]``.
    The callable is invoked lazily by the caller — never from
    ``GraphBackend.__init__``.
    """
    result = token_provider()
    if inspect.isawaitable(result):
        return await result
    return result


async def graph_send(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    token_provider: TokenProvider,
    path: str = "",
    scope: Literal["item", "drive"] = "item",
    **kwargs: Any,
) -> httpx.Response:
    """Send an authenticated Graph request and map failures to typed errors.

    Attaches ``Authorization: Bearer <token>`` from *token_provider*, sends the
    request, and on a non-2xx response raises the mapped ``remote_store`` error.
    A ``401 InvalidAuthenticationToken`` triggers one token refresh and a single
    retry; a second ``401`` raises ``PermissionDenied``. Transport-level failures
    map to ``BackendUnavailable``.

    The retry/back-off loop for transient ``5xx`` / ``429`` is the read/write
    paths' concern and is layered on by later steps; this primitive is a single
    attempt plus the one-shot auth refresh.

    Caveat: the ``401`` refresh re-issues the request with the same ``kwargs``,
    so it is only safe when the body is replayable. A streaming body (an
    ``AsyncIterator`` ``content=`` / generator ``data=``) is consumed by the
    first attempt and would replay empty — the write path must re-materialise or
    re-open such a body before relying on the refresh.
    """
    token = await acquire_token(token_provider)
    headers = {**kwargs.pop("headers", {}), "Authorization": f"Bearer {token}"}
    if log.isEnabledFor(logging.DEBUG):
        # GR-035: the bearer token is redacted before the record is formatted.
        log.debug("graph request %s %s headers=%s", method, url, mask_headers(headers))

    try:
        response = await client.request(method, url, headers=headers, **kwargs)
    except _TRANSPORT_ERRORS as exc:
        raise BackendUnavailable(f"Graph transport error: {exc}", path=path, backend=BACKEND_NAME) from None

    if response.status_code == 401:
        # Parse the 401 body once and branch on the code (GR-029).
        code = _parse_error(response)
        if code == "InvalidAuthenticationToken":
            # One-shot refresh + retry, independent of RetryPolicy. A second
            # 401 falls through to the classification below.
            token = await acquire_token(token_provider)
            headers["Authorization"] = f"Bearer {token}"
            try:
                response = await client.request(method, url, headers=headers, **kwargs)
            except _TRANSPORT_ERRORS as exc:
                raise BackendUnavailable(f"Graph transport error: {exc}", path=path, backend=BACKEND_NAME) from None
        else:
            # Any other 401 code is a permission failure a refresh cannot fix.
            raise classify_graph_error(401, code, path=path, scope=scope)

    if response.is_success:
        return response
    raise classify_graph_error(response.status_code, _parse_error(response), path=path, scope=scope)


# ---------------------------------------------------------------------------
# Pagination (GR-016)
# ---------------------------------------------------------------------------


async def iter_pages(
    client: httpx.AsyncClient,
    url: str,
    *,
    token_provider: TokenProvider,
    path: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Yield each page body of a Graph collection, following ``@odata.nextLink``.

    Terminates when a page omits ``@odata.nextLink``. An empty ``value`` array
    carrying a ``nextLink`` is followed, not treated as the end. A ``nextLink``
    that is malformed, or that points to a different scheme/host than the
    original request, is a Graph contract violation and maps to
    ``BackendUnavailable`` rather than being followed: each page is re-fetched
    through ``graph_send`` (which attaches the bearer token), so following a
    cross-host link would leak the token to an unrelated host.
    """
    trusted = urlsplit(url)
    next_url: str | None = url
    while next_url:
        response = await graph_send(client, "GET", next_url, token_provider=token_provider, path=path)
        body = response.json()
        yield body
        link = body.get("@odata.nextLink") if isinstance(body, dict) else None
        if link is None:
            return
        parts = urlsplit(link) if isinstance(link, str) else None
        if parts is None or (parts.scheme, parts.netloc) != (trusted.scheme, trusted.netloc):
            raise BackendUnavailable(
                f"Graph returned a cross-host or malformed @odata.nextLink: {link!r}",
                path=path,
                backend=BACKEND_NAME,
            )
        next_url = link
