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

import asyncio
import inspect
import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
    ResourceLocked,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

    from remote_store._config import RetryPolicy

    TokenProvider = Callable[[], str] | Callable[[], Awaitable[str]]

BACKEND_NAME = "graph"
"""The backend ``name``; set on every mapped error."""

_REDACTED = "***"
_SENSITIVE_HEADERS = frozenset({"authorization"})

# Transport-level httpx failures (connect/read/write timeouts, DNS, resets)
# map to BackendUnavailable per GR-033 — the request never reached a status.
_TRANSPORT_ERRORS = (httpx.TransportError,)

# Statuses the retry loop treats as transient (GR-033 5xx, GR-034 429). Every
# other non-2xx is terminal and raised on the first attempt. 507 / 423 / 403 /
# 404 / 409 are deliberately absent — they do not clear on short-term retry
# (RET-015 terminal conditions).
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

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


def redact_presigned_url(url: str) -> str:
    """Return *url* with its query (and fragment) stripped — for pre-signed URLs.

    The Graph pre-signed surfaces — the read download URL, the upload-session
    URL, and the copy/move monitor URL — each carry their own credential in the
    query string. A token must never reach an exception message or log record, so
    when such a URL is surfaced for out-of-band diagnosis the query is dropped
    while the scheme / host / path still identify the operation. Used by both the
    monitor poller and the upload-session ``423`` handler so the masking rule
    applies once, the same way, to both pre-signed sites.
    """
    # Credential masking (GR-035) for the GR-015 / GR-038 / GR-026 pre-signed URLs.
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


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
    if status == 416:  # GR-055 invalidRange on a range read (malformed-bounds case)
        return RemoteStoreError(f"Invalid range (416 {code or 'invalidRange'}): {path}", path=path, backend=backend)
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


# Reverse map for a Graph error.code that arrives without an HTTP status — the
# async-operation monitor reports a failed copy/move as a `error.code` string in
# the poll body (GR-026), not as a transport status. Each known code is mapped to
# the status its synchronous form would carry so the single classify table stays
# authoritative; an unrecognised code falls through to BackendUnavailable.
_CODE_TO_STATUS = {
    "accessDenied": 403,
    "itemNotFound": 404,
    "nameAlreadyExists": 409,
    "resourceLocked": 423,
    "activityLimitReached": 429,
    "quotaLimitReached": 507,
    "insufficientStorage": 507,
}


def classify_graph_error_code(
    code: str | None,
    *,
    path: str = "",
    backend: str = BACKEND_NAME,
) -> RemoteStoreError:
    """Map a status-less Graph ``error.code`` to a ``remote_store`` error.

    A failed async operation (copy / may-be-async move) reports its failure as an
    ``error.code`` string in the monitor poll body with no HTTP status of its own.
    This reuses the single ``classify_graph_error`` table via the known
    code→status reverse map; an unknown or missing code maps to
    ``BackendUnavailable`` (the operation failed and the cause is not classifiable).
    """
    status = _CODE_TO_STATUS.get(code or "")
    if status is None:
        return BackendUnavailable(f"Graph operation failed ({code or 'unknown'}): {path}", path=path, backend=backend)
    return classify_graph_error(status, code, path=path, backend=backend)


def _parse_error(response: httpx.Response) -> str | None:
    """Best-effort extraction of ``error.code`` from a response body."""
    try:
        return error_code(response.json())
    except (ValueError, httpx.DecodingError):  # non-JSON / empty body
        return None


def response_json(response: httpx.Response) -> object | None:
    """Return the parsed JSON body, or ``None`` for a non-JSON / empty body.

    Used by the write path, which inspects ``409`` conflict bodies the flat
    status→error table is deliberately blind to.
    """
    try:
        body: object = response.json()
    except (ValueError, httpx.DecodingError):
        return None
    return body


def _conflict_candidates(body: object) -> list[dict[str, Any]]:
    """Return the driveItem-shaped dicts a ``409`` conflict body may carry.

    Graph surfaces the conflicting item either as ``error.details`` entries or,
    under ``@microsoft.graph.conflictBehavior=fail``, as the echoed target item
    at the body top level. Both shapes are accepted; non-dict members are
    dropped so a malformed body degrades to the plain ``AlreadyExists`` default.
    """
    candidates: list[dict[str, Any]] = []
    if not isinstance(body, dict):
        return candidates
    err = body.get("error")
    if isinstance(err, dict):
        details = err.get("details")
        if isinstance(details, list):
            candidates.extend(d for d in details if isinstance(d, dict))
    if "folder" in body or "file" in body:
        candidates.append(body)
    return candidates


def discriminate_write_conflict(body: object, path: str, *, backend: str = BACKEND_NAME) -> RemoteStoreError:
    """Map a ``409`` write-conflict body to a typed error.

    Graph's ``409 nameAlreadyExists`` alone does not discriminate the
    precondition outcomes, so the structured body (facets on the conflicting
    item, never the error *message*) is inspected:

    * a ``folder`` facet on the **target** name → the target is an existing
      folder → ``InvalidPath``;
    * a ``file`` facet on an **ancestor** name (file-as-directory-component) →
      ``InvalidPath`` regardless of ``overwrite``;
    * otherwise the target is a file at the requested name → ``AlreadyExists``.

    The ancestor and folder cases are overwrite-independent: ``overwrite=True``
    sends ``conflictBehavior=replace``, so a plain target-file never reaches
    this discriminator — only the structurally-invalid cases do.
    """
    # GR-018 / BE-008 precondition discrimination; ancestor-file is ID-209.
    target = path.rsplit("/", 1)[-1]
    for entry in _conflict_candidates(body):
        name = entry.get("name") or entry.get("target")
        if "folder" in entry and name in (None, target):
            return InvalidPath(f"Cannot write — '{path}' names an existing folder", path=path, backend=backend)
        if "file" in entry and name is not None and name != target:
            return InvalidPath(f"Cannot write — ancestor '{name}' is a file: {path}", path=path, backend=backend)
    return AlreadyExists(f"Already exists: {path}", path=path, backend=backend)


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header into seconds.

    Supports both forms RFC 7231 allows: delta-seconds (``"120"``) and an
    HTTP-date (``"Wed, 21 Oct 2025 07:28:00 GMT"``), the latter expressed as the
    remaining seconds until that instant (never negative). Returns ``None`` when
    the header is absent or unparseable, so the caller falls back to the
    computed backoff.
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    return max(0.0, (target - datetime.now(tz=timezone.utc)).total_seconds())


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


async def _send_attempt(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    token_provider: TokenProvider,
    authenticated: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    """One request attempt plus the one-shot ``401`` auth refresh.

    Returns the raw ``httpx.Response`` — success or error status alike;
    status classification is the caller's job (``graph_send``). A
    ``401 InvalidAuthenticationToken`` triggers exactly one token refresh and a
    single re-issue; a still-``401`` response (second 401, or a non-refresh
    code) is returned for the caller to map to ``PermissionDenied``. Transport
    failures propagate as ``httpx.TransportError`` for the retry loop to handle.

    ``authenticated=False`` attaches no bearer token and skips the refresh — for
    pre-signed targets (the upload-session ``uploadUrl``) that carry their own
    token in the URL and reject a cross-host ``Authorization`` header, mirroring
    the auth-free ``downloadUrl`` reads.

    ``kwargs`` is consumed locally (``headers`` is popped from the callee's own
    copy), so a caller may re-invoke with the same ``kwargs`` across retries; a
    streaming body would still replay empty, so the retry loop is only wired to
    replayable (non-streaming) requests.
    """
    headers = dict(kwargs.pop("headers", {}))
    if authenticated:
        token = await acquire_token(token_provider)
        headers["Authorization"] = f"Bearer {token}"
    if log.isEnabledFor(logging.DEBUG):
        # GR-035: the bearer token is redacted before the record is formatted.
        log.debug("graph request %s %s headers=%s", method, url, mask_headers(headers))
    response = await client.request(method, url, headers=headers, **kwargs)
    if authenticated and response.status_code == 401 and _parse_error(response) == "InvalidAuthenticationToken":
        # One-shot refresh + re-issue, independent of RetryPolicy.
        token = await acquire_token(token_provider)
        headers["Authorization"] = f"Bearer {token}"
        response = await client.request(method, url, headers=headers, **kwargs)
    return response


async def graph_send(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    token_provider: TokenProvider,
    path: str = "",
    scope: Literal["item", "drive"] = "item",
    retry: RetryPolicy | None = None,
    return_on: frozenset[int] = frozenset(),
    authenticated: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    """Send an authenticated Graph request and map failures to typed errors.

    Attaches ``Authorization: Bearer <token>`` from *token_provider*, sends the
    request, and on a non-2xx response raises the mapped ``remote_store`` error.
    A ``401 InvalidAuthenticationToken`` triggers one token refresh and a single
    re-issue; a second ``401`` raises ``PermissionDenied``. Transport-level
    failures map to ``BackendUnavailable``.

    Retry: when *retry* is supplied with ``max_attempts > 1``, a transient
    response (a retryable ``5xx`` / ``429``, or a transport error) is retried
    with exponential backoff ``min(backoff_max, backoff_base * 2**attempt)`` plus
    uniform ``[0, jitter]``; a ``Retry-After`` header (HTTP-date or delta-seconds)
    raises the wait to at least its value. ``retry.timeout`` bounds the whole
    loop. Terminal mappings (``PermissionDenied`` / ``NotFound`` /
    ``AlreadyExists`` / ``ResourceLocked`` / insufficient-storage) raise on the
    first attempt — they do not clear on short-term retry. ``retry=None`` is a
    single attempt (the default for every call site until it opts in), so the
    auth refresh is the only re-issue.

    ``return_on`` lists non-2xx statuses the caller wants to classify itself:
    a response whose status is in the set is **returned raw** instead of
    mapped-and-raised, and is never treated as transient (so it is not retried).
    The write path uses this to inspect a ``409`` body for the
    folder / ancestor-file / already-exists discrimination and to surface a
    mid-session ``423`` with the unfinished session context — cases the flat
    status→error table cannot disambiguate. The default empty set leaves every
    existing call site byte-identical.

    ``authenticated=False`` sends no bearer token (and skips the ``401`` refresh)
    for a pre-signed, self-authenticating target such as the upload-session
    ``uploadUrl`` — which lives on a different host and rejects a cross-host
    ``Authorization`` header, exactly like the ``downloadUrl`` reads.

    Caveat: both the auth refresh and the retry loop re-issue the request with
    the same ``kwargs``, so they are only safe when the body is replayable. A
    streaming body (an ``AsyncIterator`` ``content=`` / generator ``data=``) is
    consumed by the first attempt and would replay empty — the write path must
    re-materialise such a body, and must not pass a retry policy that would
    re-send it.
    """
    attempts = retry.max_attempts if retry is not None else 1
    start = time.monotonic()
    last_error: RemoteStoreError | None = None
    for attempt in range(attempts):
        retry_after: float | None = None
        try:
            response = await _send_attempt(
                client, method, url, token_provider=token_provider, authenticated=authenticated, **kwargs
            )
        except _TRANSPORT_ERRORS as exc:
            last_error = BackendUnavailable(f"Graph transport error: {exc}", path=path, backend=BACKEND_NAME)
        else:
            if response.is_success or response.status_code in return_on:
                return response
            code = _parse_error(response)
            if response.status_code in _RETRYABLE_STATUSES:
                last_error = classify_graph_error(response.status_code, code, path=path, scope=scope)
                retry_after = _parse_retry_after(response.headers.get("retry-after"))
            else:
                # Terminal (incl. 401/403 → PermissionDenied, 404, 409, 423, 507).
                raise classify_graph_error(response.status_code, code, path=path, scope=scope)

        # Reached only on a retryable outcome. Stop if this was the last attempt
        # or the wall-clock budget is spent; otherwise back off and retry.
        if retry is None or attempt >= attempts - 1:
            break
        delay = min(retry.backoff_base * (2**attempt), retry.backoff_max) + random.uniform(0, retry.jitter)  # noqa: S311
        if retry_after is not None:
            delay = max(delay, retry_after)
        if retry.timeout is not None and time.monotonic() - start + delay >= retry.timeout:
            break
        await asyncio.sleep(delay)

    assert last_error is not None  # noqa: S101 — the loop only exits here via a retryable outcome
    raise last_error


# ---------------------------------------------------------------------------
# Pagination (GR-016)
# ---------------------------------------------------------------------------


async def iter_pages(
    client: httpx.AsyncClient,
    url: str,
    *,
    token_provider: TokenProvider,
    path: str = "",
    retry: RetryPolicy | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield each page body of a Graph collection, following ``@odata.nextLink``.

    Terminates when a page omits ``@odata.nextLink``. An empty ``value`` array
    carrying a ``nextLink`` is followed, not treated as the end. A ``nextLink``
    that is malformed, or that points to a different scheme/host than the
    original request, is a Graph contract violation and maps to
    ``BackendUnavailable`` rather than being followed: each page is re-fetched
    through ``graph_send`` (which attaches the bearer token), so following a
    cross-host link would leak the token to an unrelated host.

    Each page fetch is retried per *retry* (threaded straight into
    ``graph_send``); ``None`` keeps the single-attempt default.
    """
    trusted = urlsplit(url)
    next_url: str | None = url
    while next_url:
        response = await graph_send(client, "GET", next_url, token_provider=token_provider, path=path, retry=retry)
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
