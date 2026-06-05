"""Resilient range-download driver for the Graph read path.

The pre-signed ``@microsoft.graph.downloadUrl`` is the only Graph surface that
honours ``Range`` reliably (the ``/content`` endpoint ``302``-redirects to it),
and it is pre-signed, so requests against it carry **no** ``Authorization``
header. This module drives reads against that URL:

* a full read streams the whole entity with no ``Range`` header (the happy
  path), while a partial read sends ``Range: bytes=<start>-<end>``;
* if the read is interrupted — the pre-signed URL expires (``401`` / ``403``)
  or the connection drops mid-body (``httpx.TransportError``, possibly after
  some bytes have already streamed) — the driver re-fetches item metadata for a
  fresh URL, verifies the ``eTag`` is unchanged, and resumes from the next unread
  byte with a ``Range`` request; a changed ``eTag`` means the file was mutated
  underneath the read, which surfaces as ``BackendUnavailable`` rather than a
  mixed-version byte stream. Recovery is bounded by the retry budget;
* some SharePoint drive backings ignore ``Range`` and answer a ranged request
  with the **full** entity (``200``) — or reject it with a non-``416`` ``4xx``;
  the driver then treats the URL as range-incapable, falls back to the spool
  strategy (re-read the full entity into a ``SpooledTemporaryFile``, serve the
  requested window), emits a WARNING carrying the ``graph.read.range_fallback``
  marker, and lets the backend flag the condition on any ``FileInfo`` it returns
  for the same item;
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

# Rollover threshold for the fallback spool: a full-entity body larger than this
# spills from memory to a temp file, so a large fallback does not balloon memory.
_SPOOL_MAX_SIZE = 1024 * 1024
# Read-back window size: the spooled body is served out in chunks of this size,
# kept independent of the rollover threshold so tuning one cannot silently move
# the other.
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


def _remaining(length: int | None, consumed: int) -> int | None:
    """Bytes still owed to the caller after *consumed* yielded; ``None`` = to EOF."""
    return None if length is None else max(0, length - consumed)


def _resume_url(item: Mapping[str, Any], expected_etag: object, path: str, backend: str) -> str:
    """Return a fresh download URL from re-fetched *item*, guarding the ``eTag``.

    A changed ``eTag`` means the file was mutated mid-read; rather than splice two
    versions, raise ``BackendUnavailable`` carrying both eTags.
    """
    new_etag = item.get("eTag")
    if new_etag != expected_etag:
        raise BackendUnavailable(
            f"File changed under read (eTag {expected_etag!r} != {new_etag!r}): {path}", path=path, backend=backend
        )
    return _require_url(item, path, backend)


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
    other window sends one. Yields the body in chunks, tracking how many it has
    delivered so an interrupted read resumes from the next unread byte:

    * a status-time expiry (``401`` / ``403``) or a connection drop
      (``httpx.TransportError``, possibly mid-body after some chunks have already
      been yielded) re-fetches metadata for a fresh URL, verifies the ``eTag`` is
      unchanged, and re-requests from ``start + delivered`` with a ``Range``
      header — bounded by ``retry.max_attempts``;
    * a drive that ignores ``Range`` (``200`` full entity) or rejects it with a
      non-``416`` ``4xx`` is treated as range-incapable: the full entity is
      re-read into a spool and the requested window served from it
      (*on_fallback* fires once).

    Raises:
        BackendUnavailable: Missing download URL, recovery that does not clear
            within the retry budget, an ``eTag`` change mid-read, a non-range
            error status, or a transport failure on the pre-signed host.
        RemoteStoreError: A ``416`` provoked by a malformed (inverted) range.
    """
    end = None if length is None else start + length - 1
    etag = item.get("eTag")
    url = _require_url(item, path, backend)
    delivered = 0  # bytes already yielded to the caller; resume offset is start + delivered
    attempts = 0
    max_attempts = retry.max_attempts if retry is not None else 1
    range_incapable = False  # the drive ignores/rejects Range: read full + window

    while True:
        offset = start + delivered
        sent_range = (offset > 0 or end is not None) and not range_incapable
        headers = {"Range": _range_header(offset, end)} if sent_range else {}
        try:
            async with client.stream("GET", url, headers=headers) as response:
                status = response.status_code
                if status in (401, 403):
                    # Download URL expired: re-fetch for a fresh URL and resume,
                    # bounded by the retry budget.
                    await response.aread()
                    attempts += 1
                    if attempts >= max_attempts:
                        raise BackendUnavailable(
                            f"Download URL kept expiring after {attempts} attempt(s): {path}",
                            path=path,
                            backend=backend,
                        )
                    url = _resume_url(await refetch(), etag, path, backend)
                    continue
                if sent_range and status == 416:
                    await response.aread()
                    if end is not None and end < offset:
                        # Inverted bounds are a backend bug, not an empty read.
                        raise classify_graph_error(416, "invalidRange", path=path, backend=backend)
                    return  # offset at/past EOF → empty remainder
                if sent_range and (status == 200 or 400 <= status < 500):
                    # The drive ignored Range (200 full entity) or rejected it
                    # (non-401/403/416 4xx): treat the URL as range-incapable.
                    on_fallback()
                    log.warning("%s: drive ignored Range; spooling full entity for %r", RANGE_FALLBACK_FLAG, path)
                    if status != 200:
                        # A 4xx carries no usable body — re-issue without a Range.
                        await response.aread()
                        range_incapable = True
                        continue
                    async for chunk in _spooled_window(response, skip=offset, remaining=_remaining(length, delivered)):
                        delivered += len(chunk)
                        yield chunk
                    return
                if not response.is_success:
                    await response.aread()
                    raise BackendUnavailable(f"Graph download failed ({status}): {path}", path=path, backend=backend)
                # 2xx body. In range-incapable mode the response is the full entity
                # (no Range honoured), so window it through the spool; otherwise
                # stream it straight. A drop mid-body raises below and resumes.
                source = (
                    _spooled_window(response, skip=offset, remaining=_remaining(length, delivered))
                    if range_incapable
                    else response.aiter_bytes()
                )
                async for chunk in source:
                    delivered += len(chunk)
                    yield chunk
                return
        except httpx.TransportError as exc:
            # Connection failed or dropped mid-body (after `delivered` bytes):
            # re-fetch for a fresh URL, verify the file is unchanged, and resume
            # from the next unread byte — bounded by the retry budget.
            attempts += 1
            if attempts >= max_attempts:
                raise BackendUnavailable(f"Graph download transport error: {exc}", path=path, backend=backend) from None
            url = _resume_url(await refetch(), etag, path, backend)


async def _spooled_window(
    response: httpx.Response,
    *,
    skip: int,
    remaining: int | None,
) -> AsyncIterator[bytes]:
    """Buffer a full-entity response to a spool, then yield the ``[skip, skip+remaining)`` window.

    Used only on the SharePoint range-fallback path, where the drive returned the
    whole file (the ``200`` it answered a ranged GET with, or the re-issued
    no-``Range`` GET after a ``4xx`` range rejection). The body is spooled, rolling
    over from memory to a temp file past ``_SPOOL_MAX_SIZE`` so a large fallback
    does not balloon memory, then the requested window is read back out in
    ``_SPOOL_READ_CHUNK`` slices.
    """
    with tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_SIZE) as spool:
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
