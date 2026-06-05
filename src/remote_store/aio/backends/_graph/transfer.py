"""Resilient range-download driver for the Graph read path.

The pre-signed ``@microsoft.graph.downloadUrl`` is the only Graph surface that
honours ``Range`` reliably (the ``/content`` endpoint ``302``-redirects to it),
and it is pre-signed, so requests against it carry **no** ``Authorization``
header. This module drives reads against that URL:

* a full read streams the whole entity with no ``Range`` header (the happy
  path), while a partial read sends ``Range: bytes=<start>-<end>``;
* if the URL expires mid-read (``401`` / ``403`` from the pre-signed host) the
  driver re-fetches item metadata for a fresh URL and verifies the ``eTag`` is
  unchanged before resuming from the next unread byte — a changed ``eTag`` means
  the file was mutated underneath the read, which surfaces as
  ``BackendUnavailable`` rather than a mixed-version byte stream;
* some SharePoint drive backings ignore ``Range`` and answer a ranged request
  with the **full** entity (``200``); the driver then falls back to the spool
  strategy (buffer to a ``SpooledTemporaryFile``, serve the requested window),
  emits a WARNING carrying the ``graph.read.range_fallback`` marker, and lets the
  backend flag the condition on any ``FileInfo`` it returns for the same item;
* a ``416`` whose start is at or past EOF yields an empty remainder (no error);
  a ``416`` provoked by a malformed (inverted) range is a backend bug and
  surfaces as ``RemoteStoreError`` carrying the HTTP status.

The driver is internal: ``SEEKABLE_READ`` stays withheld, and the request shape
may change without a public-API deprecation.
"""

from __future__ import annotations

import logging
import tempfile
from typing import TYPE_CHECKING

import httpx

from remote_store._errors import BackendUnavailable
from remote_store.aio.backends._graph.http import BACKEND_NAME, classify_graph_error
from remote_store.aio.backends._graph.items import download_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
    from typing import Any

    from remote_store._config import RetryPolicy

    Refetch = Callable[[], Awaitable[Mapping[str, Any]]]
    OnFallback = Callable[[], None]

log = logging.getLogger("remote_store.aio.backends._graph")

RANGE_FALLBACK_FLAG = "graph.read.range_fallback"
"""Key set ``True`` on ``FileInfo.extra`` (and the WARNING-log marker) when a
SharePoint drive ignores ``Range`` and the read falls back to the spool."""

# Window the spooled fallback body back out in bounded reads rather than one
# slice, so a large full-entity fallback stays disk-backed end to end.
_SPOOL_READ_CHUNK = 1024 * 1024


def _require_url(item: Mapping[str, Any], path: str, backend: str) -> str:
    """Return the pre-signed download URL, or raise if the item carries none.

    A file item should always carry a download URL (even a 0-byte file); its
    absence is a Graph contract gap, not a silent empty read.
    """
    url = download_url(item)
    if url is None:
        raise BackendUnavailable(f"Graph returned no download URL for: {path}", path=path, backend=backend)
    return url


def _range_header(offset: int, end: int | None) -> str:
    """Build a ``Range`` header value: ``bytes=<offset>-`` or ``bytes=<offset>-<end>``."""
    return f"bytes={offset}-" if end is None else f"bytes={offset}-{end}"


async def stream_range(
    client: httpx.AsyncClient,
    path: str,
    item: Mapping[str, Any],
    *,
    start: int = 0,
    length: int | None = None,
    refetch: Refetch,
    on_fallback: OnFallback,
    retry: RetryPolicy | None = None,
    backend: str = BACKEND_NAME,
) -> AsyncIterator[bytes]:
    """Stream ``[start, start+length)`` of a file from its download URL.

    ``start=0, length=None`` is a full read and sends no ``Range`` header; any
    other window sends one. Yields the body in chunks; recovers across
    download-URL expiry (re-fetching metadata via *refetch* and re-checking the
    ``eTag``) and degrades to a spooled full-entity read when the drive ignores
    ``Range`` (*on_fallback* is invoked once when that happens).

    Expiry is a status-time signal (``401`` / ``403`` arrives before any byte of
    the body), so the failed attempt delivered nothing and recovery re-requests
    the same window — there is no partial-delivery cursor to advance.

    Raises:
        BackendUnavailable: Missing download URL, expiry that does not clear
            within the retry budget, an ``eTag`` change mid-read, a non-range
            error status, or a transport failure on the pre-signed host.
        RemoteStoreError: A ``416`` provoked by a malformed (inverted) range.
    """
    end = None if length is None else start + length - 1
    sent_range = start > 0 or end is not None
    headers = {"Range": _range_header(start, end)} if sent_range else {}
    etag = item.get("eTag")
    url = _require_url(item, path, backend)
    refetches = 0
    max_refetch = retry.max_attempts if retry is not None else 1

    while True:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                status = response.status_code
                if status in (401, 403):
                    # Download URL expired before serving a byte: re-fetch metadata
                    # for a fresh URL and re-request, bounded by the retry budget.
                    await response.aread()
                    refetches += 1
                    if refetches > max_refetch:
                        raise BackendUnavailable(
                            f"Download URL kept expiring after {refetches} re-fetch(es): {path}",
                            path=path,
                            backend=backend,
                        )
                    item = await refetch()
                    new_etag = item.get("eTag")
                    if new_etag != etag:
                        raise BackendUnavailable(
                            f"File changed under read (eTag {etag!r} != {new_etag!r}): {path}",
                            path=path,
                            backend=backend,
                        )
                    url = _require_url(item, path, backend)
                    continue
                if status == 416:
                    await response.aread()
                    if end is not None and end < start:
                        # Inverted bounds are a backend bug, not an empty read.
                        raise classify_graph_error(416, "invalidRange", path=path, backend=backend)
                    return  # start at/past EOF → empty remainder
                if sent_range and status == 200:
                    # SharePoint ignored Range and sent the full entity: spool it
                    # and serve the requested window rather than streaming mid-file.
                    on_fallback()
                    log.warning("%s: drive ignored Range; spooling full entity for %r", RANGE_FALLBACK_FLAG, path)
                    async for chunk in _spooled_window(response, skip=start, remaining=length):
                        yield chunk
                    return
                if not response.is_success:
                    await response.aread()
                    raise BackendUnavailable(f"Graph download failed ({status}): {path}", path=path, backend=backend)
                async for chunk in response.aiter_bytes():
                    yield chunk
                return
        except httpx.TransportError as exc:
            raise BackendUnavailable(f"Graph download transport error: {exc}", path=path, backend=backend) from None


async def _spooled_window(
    response: httpx.Response,
    *,
    skip: int,
    remaining: int | None,
) -> AsyncIterator[bytes]:
    """Buffer a full-entity response to a spool, then yield the ``[skip, skip+remaining)`` window.

    Used only on the SharePoint range-fallback path, where the drive returned the
    whole file in answer to a ``Range`` request. The body is spooled to disk (via
    ``SpooledTemporaryFile``) so a large fallback does not balloon memory, then
    the requested window is read back out in bounded chunks.
    """
    with tempfile.SpooledTemporaryFile(max_size=_SPOOL_READ_CHUNK) as spool:
        async for chunk in response.aiter_bytes():
            spool.write(chunk)
        spool.seek(skip)
        owed = remaining
        while owed is None or owed > 0:
            want = _SPOOL_READ_CHUNK if owed is None else min(_SPOOL_READ_CHUNK, owed)
            data = spool.read(want)
            if not data:
                return
            if owed is not None:
                owed -= len(data)
            yield data
