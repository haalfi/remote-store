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

import io
import logging
import tempfile
from typing import TYPE_CHECKING

import httpx

from remote_store._errors import BackendUnavailable, RemoteStoreError, ResourceLocked
from remote_store.aio.backends._graph.http import (
    BACKEND_NAME,
    classify_graph_error,
    discriminate_write_conflict,
    error_code,
    graph_send,
    response_json,
)
from remote_store.aio.backends._graph.items import download_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
    from typing import Any, BinaryIO

    from remote_store._config import RetryPolicy

    Refetch = Callable[[], Awaitable[Mapping[str, Any]]]
    OnFallback = Callable[[], None]
    TokenProvider = Callable[[], str] | Callable[[], Awaitable[str]]

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


# ---------------------------------------------------------------------------
# Upload-session driver (GR-019 .. GR-024, GR-038, GR-045)
# ---------------------------------------------------------------------------

UPLOAD_SPOOL_MARKER = "graph.upload.spool_spilled"
"""DEBUG-log marker emitted when an unknown-length write iterator spills to disk
(GR-019). The spool path rides the record so callers on small temp volumes can
diagnose ``TMPDIR`` pressure."""

UPLOAD_ABORT_MARKER = "graph.upload.abort_failed"
"""DEBUG-log marker emitted when a best-effort upload-session ``DELETE`` fails
(GR-024 / GR-051). Cleanup never propagates."""

# Rollover threshold for an unknown-length write iterator. Matches the GR-018
# small-file boundary so an iterator that stays small is replayed from memory
# (no spill, no marker) and only a genuine large write spills to disk.
_UPLOAD_SPOOL_MAX_SIZE = 4 * 1024 * 1024


async def spool_content(content: bytes | AsyncIterator[bytes], *, path: str) -> tuple[BinaryIO, int]:
    """Materialise write *content* into a seekable, replayable reader + its length.

    ``bytes`` is wrapped in an in-memory ``BytesIO`` (no spill). An
    ``AsyncIterator[bytes]`` of unknown length is drained into a
    ``SpooledTemporaryFile`` (system temp, no ``dir=``) so the total can be
    measured before the upload session opens (Graph's ``Content-Range`` needs a
    known total); a spill past the in-memory threshold emits the
    ``graph.upload.spool_spilled`` DEBUG marker. The reader is positioned at
    ``0`` and supports ``seek``/``read`` so chunks replay safely across retries.
    The caller owns closing it.
    """
    if isinstance(content, (bytes, bytearray)):
        return io.BytesIO(bytes(content)), len(content)
    # Returned to the caller, which owns closing it (write()'s finally) — a
    # context manager here would close it before the upload reads from it.
    spool: Any = tempfile.SpooledTemporaryFile(max_size=_UPLOAD_SPOOL_MAX_SIZE)  # noqa: SIM115
    async for chunk in content:
        spool.write(chunk)
    total = spool.tell()
    if total > _UPLOAD_SPOOL_MAX_SIZE:
        log.debug("%s: spilled %d bytes to %s for %r", UPLOAD_SPOOL_MARKER, total, spool.name, path)
    spool.seek(0)
    return spool, total


async def upload_session(
    client: httpx.AsyncClient,
    create_url: str,
    reader: BinaryIO,
    total: int,
    *,
    path: str,
    token_provider: TokenProvider,
    chunk_size: int,
    overwrite: bool,
    retry: RetryPolicy | None,
    on_session_open: Callable[[str], None],
    on_session_close: Callable[[str], None],
    backend: str = BACKEND_NAME,
) -> dict[str, Any]:
    """Upload *reader* (``total`` bytes) via a Graph upload session; return the driveItem.

    Opens a session with ``POST createUploadSession``, then PUTs aligned chunks
    with ``Content-Range: bytes {start}-{end}/{total}``. Each chunk is an
    in-memory byte slice, so the shared retry loop may re-send it on a transient
    ``5xx`` / ``429`` without restarting the session; a ``202`` resumes from the
    server's ``nextExpectedRanges`` rather than the client cursor; a ``401``
    re-acquires the token and retries the same chunk against the same
    (pre-authorised) session URL.

    On an unrecoverable failure the session is ``DELETE``d best-effort; a ``423``
    is the exception — the session URL stays valid for caller-driven resume, so
    it surfaces as ``ResourceLocked`` (carrying the session URL and last
    ``nextExpectedRanges``) without an abort. ``on_session_open`` /
    ``on_session_close`` register the live session URL so the backend's
    ``close()`` can abort it if a write is mid-flight.
    """
    # GR-019..GR-024, GR-038 (token expiry), GR-045 (423), GR-051 (close-abort).
    session_url = await _create_upload_session(
        client, create_url, path=path, token_provider=token_provider, overwrite=overwrite, retry=retry, backend=backend
    )
    on_session_open(session_url)
    try:
        return await _upload_chunks(
            client,
            session_url,
            reader,
            total,
            path=path,
            token_provider=token_provider,
            chunk_size=chunk_size,
            retry=retry,
            backend=backend,
        )
    except ResourceLocked:
        # GR-045: leave the session alive for caller-driven resume — no abort.
        raise
    except BaseException:
        await abort_upload_session(client, session_url, token_provider=token_provider)
        raise
    finally:
        on_session_close(session_url)


async def _create_upload_session(
    client: httpx.AsyncClient,
    create_url: str,
    *,
    path: str,
    token_provider: TokenProvider,
    overwrite: bool,
    retry: RetryPolicy | None,
    backend: str,
) -> str:
    """Open an upload session and return its (pre-authorised) ``uploadUrl``.

    A ``409`` at creation discriminates the conflict outcome; a missing
    ``uploadUrl`` is a Graph contract gap mapped to ``BackendUnavailable``.
    """
    behavior = "replace" if overwrite else "fail"
    response = await graph_send(
        client,
        "POST",
        create_url,
        token_provider=token_provider,
        path=path,
        retry=retry,
        return_on=frozenset({409}),
        json={"item": {"@microsoft.graph.conflictBehavior": behavior}},
    )
    if response.status_code == 409:
        raise discriminate_write_conflict(response_json(response), path, backend=backend)
    data = response.json()
    session_url = data.get("uploadUrl") if isinstance(data, dict) else None
    if not isinstance(session_url, str) or not session_url:
        raise BackendUnavailable(f"Graph createUploadSession returned no uploadUrl: {path}", path=path, backend=backend)
    return session_url


async def _upload_chunks(
    client: httpx.AsyncClient,
    session_url: str,
    reader: BinaryIO,
    total: int,
    *,
    path: str,
    token_provider: TokenProvider,
    chunk_size: int,
    retry: RetryPolicy | None,
    backend: str,
) -> dict[str, Any]:
    """PUT aligned chunks to *session_url* until the final ``200`` / ``201`` driveItem."""
    offset = 0
    last_ranges: list[str] | None = None
    while offset < total:
        length = min(chunk_size, total - offset)  # chunk_size is pre-aligned; final chunk is the remainder
        end = offset + length - 1
        reader.seek(offset)
        data = reader.read(length)
        response = await graph_send(
            client,
            "PUT",
            session_url,
            token_provider=token_provider,
            path=path,
            retry=retry,
            return_on=frozenset({409, 423}),
            # The session URL is pre-authorised and lives on a different host; a
            # cross-host bearer leaks the token and is rejected (live-verified).
            authenticated=False,
            headers={"Content-Range": f"bytes {offset}-{end}/{total}"},
            content=data,
        )
        status = response.status_code
        if status == 423:
            raise _resource_locked_mid_session(session_url, last_ranges, path, backend)
        if status == 409:
            body = response_json(response)
            if error_code(body) == "invalidRange":
                raise RemoteStoreError(
                    f"Upload chunk rejected (409 invalidRange) at bytes {offset}-{end}: {path}",
                    path=path,
                    backend=backend,
                )
            raise discriminate_write_conflict(body, path, backend=backend)
        if status in (200, 201):
            item: dict[str, Any] = response.json()
            return item
        # 202 Accepted: more chunks expected — resume from the server's offset.
        last_ranges = _next_expected_ranges(response_json(response))
        offset = _resume_offset(last_ranges, path=path, backend=backend)
    raise BackendUnavailable(f"Upload session completed without a final driveItem: {path}", path=path, backend=backend)


def _next_expected_ranges(body: object) -> list[str] | None:
    """Return the ``nextExpectedRanges`` string list from a ``202`` body, or ``None``."""
    if isinstance(body, dict):
        ranges = body.get("nextExpectedRanges")
        if isinstance(ranges, list):
            return [r for r in ranges if isinstance(r, str)]
    return None


def _resume_offset(ranges: list[str] | None, *, path: str, backend: str) -> int:
    """Parse the first ``nextExpectedRanges`` start offset.

    A missing or malformed list on a ``202`` (when one is expected) is a Graph
    contract violation mapped to ``BackendUnavailable`` — the server's offset is
    authoritative, so there is no client-cursor fallback.
    """
    if not ranges:
        raise BackendUnavailable(
            f"Graph upload returned no nextExpectedRanges mid-session: {path}", path=path, backend=backend
        )
    try:
        return int(ranges[0].split("-", 1)[0])
    except (ValueError, IndexError):
        raise BackendUnavailable(
            f"Graph upload returned malformed nextExpectedRanges {ranges!r}: {path}", path=path, backend=backend
        ) from None


def _resource_locked_mid_session(session_url: str, ranges: list[str] | None, path: str, backend: str) -> ResourceLocked:
    """Build the mid-session ``ResourceLocked`` carrying resume context.

    There is no structured ``RemoteStoreError.context`` surface, so the
    unfinished session URL and last-known ``nextExpectedRanges`` ride the
    message text — the session URL stays valid and the caller (or a test) can
    resume from them without re-deriving the offset.
    """
    ranges_text = ", ".join(ranges) if ranges else "unknown"
    return ResourceLocked(
        f"Resource locked during upload session (423): {path}. The session URL stays valid for "
        f"caller-driven resume — sessionUrl={session_url} nextExpectedRanges=[{ranges_text}].",
        path=path,
        backend=backend,
    )


async def abort_upload_session(client: httpx.AsyncClient, session_url: str, *, token_provider: TokenProvider) -> None:
    """Issue a best-effort ``DELETE`` against *session_url*.

    Every failure — a mapped error, a transport drop, a non-2xx status — is
    swallowed to a DEBUG record; cleanup must never propagate.
    """
    try:
        # The session URL is pre-authorised (no cross-host bearer) — as for chunks.
        await graph_send(client, "DELETE", session_url, token_provider=token_provider, authenticated=False)
    except Exception:  # noqa: BLE001 -- best-effort cleanup never propagates
        log.debug("%s: best-effort DELETE of upload session failed", UPLOAD_ABORT_MARKER, exc_info=True)
