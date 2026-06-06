"""Async monitor-URL poller for Graph copy / may-be-async move.

Microsoft Graph answers a long-running ``copy`` (always) and a large or
cross-folder ``move`` (sometimes) with ``202 Accepted`` plus a ``Location``
header pointing to a monitor URL the client polls until the operation reaches a
terminal state. This module drives that poll loop.

It is **backend-local**, not a shared facility: one consumer (the Graph
backend), one location. The loop is parser-driven so a future second consumer
could reuse it without an API redesign — ``parse_graph_monitor_response`` is the
Graph-specific classifier, injectable via ``status_parser``.

The monitor URL is pre-authenticated (like the ``downloadUrl`` reads and the
upload-session ``uploadUrl``): the poll GET carries **no** ``Authorization``
header, so the Graph bearer is never leaked cross-host. Redirects are not
followed — a completion ``3xx`` is read as success rather than chased to the new
item.
"""

# Design: ADR-0023 (backend-local monitor poller); contract: spec 044 GR-026.
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Literal, NamedTuple
from urllib.parse import urlsplit, urlunsplit

import httpx

from remote_store._errors import BackendUnavailable
from remote_store.aio.backends._graph.http import (
    BACKEND_NAME,
    classify_graph_error_code,
    response_json,
)
from remote_store.aio.backends._graph.http import _parse_retry_after as parse_retry_after

if TYPE_CHECKING:
    from collections.abc import Callable

    from remote_store._errors import RemoteStoreError

log = logging.getLogger("remote_store.aio.backends._graph")

POLL_COMPLETE_MARKER = "graph.copy.poll_complete"
"""DEBUG-log marker carrying the poll count + duration when a monitor reaches a
terminal *succeeded* state (GR-026). ``caplog`` is the test channel; the full
monitor URL is deliberately **not** logged here (it may carry a pre-auth token)."""

# Poll cadence defaults (GR-026 / ADR-0023). Resolved at call time (not bound as
# argument defaults) so a test can monkeypatch them to 0 and run without real
# waits, and so the backend gets the spec cadence without restating it.
_INITIAL_INTERVAL = 1.0
_MAX_INTERVAL = 30.0
_BACKOFF_FACTOR = 2.0

MonitorState = Literal["pending", "succeeded", "failed"]


class MonitorResult(NamedTuple):
    """Outcome of classifying one monitor poll response.

    ``state`` is the terminal-or-not verdict; ``error`` is the Graph error
    envelope on a ``failed`` poll (``{"code": ..., "message": ...}``), ``None``
    otherwise. ``classified`` is ``False`` when the parser could not find a
    status in the body — a *pending* outcome that the loop tracks separately as
    a ``parse-error`` so the timeout message can distinguish "still running" from
    "kept returning an unreadable body".
    """

    state: MonitorState
    error: dict[str, Any] | None = None
    classified: bool = True


_SUCCEEDED_STATES = frozenset({"completed", "succeeded"})
_FAILED_STATES = frozenset({"failed", "deletefailed"})


def parse_graph_monitor_response(response: httpx.Response) -> MonitorResult:
    """Classify a Graph monitor poll response into pending / succeeded / failed.

    A completion ``3xx`` redirect is success (the operation finished and Graph is
    redirecting to the new item, which the poll deliberately does not follow). A
    ``2xx`` body carries a ``status`` field — ``completed`` / ``succeeded`` is
    terminal success, ``failed`` / ``deleteFailed`` is terminal failure (with the
    ``error`` envelope), and any in-flight status (``inProgress`` /
    ``notStarted`` / ``updating`` / ``waiting`` / ``deletePending``) is pending. A
    body with no readable ``status`` is treated as pending-but-unclassified so the
    loop keeps polling rather than failing on a single odd response.
    """
    if 300 <= response.status_code < 400:
        return MonitorResult("succeeded")
    body = response_json(response)
    if not isinstance(body, dict):
        return MonitorResult("pending", classified=False)
    status = body.get("status")
    if not isinstance(status, str):
        return MonitorResult("pending", classified=False)
    normalized = status.lower()
    if normalized in _SUCCEEDED_STATES:
        return MonitorResult("succeeded")
    if normalized in _FAILED_STATES:
        error = body.get("error")
        return MonitorResult("failed", error=error if isinstance(error, dict) else None)
    return MonitorResult("pending")


def _failed_error(error: dict[str, Any] | None, *, path: str, backend: str) -> RemoteStoreError:
    """Map a ``failed`` monitor body's ``error`` envelope to a typed error."""
    code = error.get("code") if isinstance(error, dict) else None
    return classify_graph_error_code(code if isinstance(code, str) else None, path=path, backend=backend)


def _redact_url(url: str) -> str:
    """Return *url* with its query stripped — the monitor URL is pre-signed.

    The Graph copy/move monitor URL lives on a pre-authenticated cross-host
    endpoint (live-verified: ``my.microsoftpersonalcontent.com``) and carries its
    own credential in the query string. The timeout message embeds the monitor URL
    for out-of-band diagnosis, but a token must never reach an exception message;
    stripping the query satisfies both — the scheme / host / path identify the
    operation without leaking the credential.
    """
    # GR-026 (embed monitor URL) reconciled with GR-035 (no token in messages).
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


async def poll_monitor(
    monitor_url: str,
    client: httpx.AsyncClient,
    *,
    status_parser: Callable[[httpx.Response], MonitorResult] | None = None,
    initial_interval: float | None = None,
    max_interval: float | None = None,
    backoff_factor: float | None = None,
    timeout: float | None = None,
    path: str = "",
    backend: str = BACKEND_NAME,
) -> None:
    """Poll *monitor_url* until the operation finishes; return on success, raise on failure.

    Polls with exponential backoff (``initial_interval`` floor, ``max_interval``
    ceiling, ``backoff_factor`` growth — defaults 1 s / 30 s / 2). A
    ``Retry-After`` header on a poll response raises the wait to at least its
    value. Transient ``5xx`` responses and transport errors during polling are
    treated as *pending*, not failure. ``timeout`` (the backend's
    ``copy_timeout``) bounds the total wall-clock; ``None`` means no ceiling — the
    poll runs until Graph reports a terminal state.

    Raises:
        BackendUnavailable: On ``timeout`` expiry (the message embeds the monitor
            URL, the poll count, and a ``last_status`` token), or mapped from a
            ``failed`` poll whose ``error.code`` is unknown.
        RemoteStoreError: Mapped from a ``failed`` poll body's ``error.code`` via
            the standard table (e.g. ``AlreadyExists`` for ``nameAlreadyExists``).
    """
    # GR-026 / ADR-0023. Cancellation (asyncio.CancelledError from close()) is not
    # caught — it propagates out so the awaiting caller unwinds cleanly.
    parser = status_parser or parse_graph_monitor_response
    interval = _INITIAL_INTERVAL if initial_interval is None else initial_interval
    ceiling = _MAX_INTERVAL if max_interval is None else max_interval
    factor = _BACKOFF_FACTOR if backoff_factor is None else backoff_factor
    start = time.monotonic()
    polls = 0
    last_status = "pending"
    while True:
        polls += 1
        retry_after: float | None = None
        try:
            # follow_redirects=False: a completion 3xx must surface as success,
            # not be chased to the new item (whose body has no monitor status).
            response = await client.get(monitor_url, follow_redirects=False)
        except httpx.TransportError:
            last_status = "5xx"  # a dropped poll is transient, like a 5xx
        else:
            if response.status_code >= 500:
                last_status = "5xx"
            else:
                result = parser(response)
                if result.state == "succeeded":
                    log.debug(
                        "%s: %r succeeded after %d poll(s) in %.3fs",
                        POLL_COMPLETE_MARKER,
                        path,
                        polls,
                        time.monotonic() - start,
                    )
                    return
                if result.state == "failed":
                    raise _failed_error(result.error, path=path, backend=backend)
                last_status = "pending" if result.classified else "parse-error"
                retry_after = parse_retry_after(response.headers.get("retry-after"))
        delay = min(interval, ceiling)
        if retry_after is not None and retry_after > delay:
            delay = retry_after
        if timeout is not None and (time.monotonic() - start) + delay >= timeout:
            raise BackendUnavailable(
                f"Copy/move monitor timed out after {polls} poll(s) "
                f"(last_status={last_status}, monitorUrl={_redact_url(monitor_url)}): {path}",
                path=path,
                backend=backend,
            )
        await asyncio.sleep(delay)
        interval = min(interval * factor, ceiling)
