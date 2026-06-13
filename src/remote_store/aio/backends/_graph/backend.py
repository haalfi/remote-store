"""``GraphBackend`` — the ``AsyncBackend`` implementation for Microsoft Graph.

This module holds the public surface and request/error foundation —
construction and validation, the capability declaration, path addressing and
segment encoding, the native-client escape hatch, ``close()``, and a
credential-safe ``repr`` — together with the full data plane: read, write,
list, delete / delete_folder, and move / copy (the last two awaiting the
backend-local ``monitor`` poller when Graph answers ``202 Accepted``).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypeVar
from urllib.parse import quote, unquote

import httpx

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy
from remote_store._errors import (
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from remote_store._models import FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio.backends._graph.http import (
    BACKEND_NAME,
    classify_graph_error,
    discriminate_write_conflict,
    graph_send,
    iter_pages,
    response_json,
)
from remote_store.aio.backends._graph.items import (
    is_file_item,
    is_folder_item,
    item_to_fileinfo,
    item_to_write_result,
    parse_graph_datetime,
)
from remote_store.aio.backends._graph.monitor import poll_monitor
from remote_store.aio.backends._graph.transfer import (
    RANGE_FALLBACK_FLAG,
    abort_upload_session,
    spool_content,
    stream_range,
    upload_session,
)
from remote_store.backends._flat_ns import _acheck_no_file_ancestor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

    from remote_store._models import FileInfo, WriteResult
    from remote_store._resolution import ResolutionPlan
    from remote_store.aio._types import AsyncWritableContent

    TokenProvider = Callable[[], str] | Callable[[], Awaitable[str]]

T = TypeVar("T")

_DEFAULT_BASE_URL = "https://graph.microsoft.com/v1.0"
_CHUNK_ALIGNMENT = 320 * 1024  # Graph's documented upload-chunk alignment (GR-020)
_MAX_UPLOAD_CHUNK_SIZE = 60 * 1024 * 1024  # Graph rejects any single chunk PUT >= 60 MiB (GR-005)
_DEFAULT_UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MiB (GR-001)
_SMALL_FILE_MAX_SIZE = 4 * 1024 * 1024  # PUT /content vs upload-session boundary (GR-018)

# GR-003: the declared capability set. GLOB, ATOMIC_MOVE, SEEKABLE_READ, and
# USER_METADATA are deliberately withheld (see spec 044 GR-003 for rationale).
_GRAPH_CAPABILITIES = CapabilitySet(
    {
        Capability.READ,
        Capability.WRITE,
        Capability.DELETE,
        Capability.LIST,
        Capability.MOVE,
        Capability.COPY,
        Capability.METADATA,
        Capability.ATOMIC_WRITE,
        Capability.LAZY_READ,
        Capability.WRITE_RESULT_NATIVE,
    }
)


def _encode_segment(segment: str) -> str:
    """Percent-encode one path segment per RFC 3986.

    Encodes spaces, ``#``, ``?``, ``+`` (all non-unreserved characters via
    ``quote(safe="")``) plus trailing dots, which Graph mishandles even though
    RFC 3986 treats ``.`` as unreserved.
    """
    encoded = quote(segment, safe="")
    stripped = encoded.rstrip(".")
    trailing_dots = len(encoded) - len(stripped)
    return stripped + "%2E" * trailing_dots


def _child_key(parent: str, name: str) -> str:
    """Join a parent folder key and a child name into a store key."""
    return f"{parent}/{name}" if parent else name


def _split_parent(path: str) -> tuple[str, str]:
    """Split a store path into ``(parent_key, basename)``.

    ``"a/b/c.txt"`` → ``("a/b", "c.txt")``; a top-level ``"c.txt"`` →
    ``("", "c.txt")``. Leading/trailing slashes are stripped first.
    """
    key = path.strip("/")
    parent, _, name = key.rpartition("/")
    return parent, name


class GraphBackend(AsyncBackend):
    """Async Microsoft Graph backend over OneDrive / SharePoint / Teams files.

    A single instance targets one drive, identified by an immutable
    ``drive_id``. Items are addressed by ``/``-rooted POSIX path; transport is
    ``httpx``; auth is a token-provider callable (the built-in ``GraphAuth``
    helper, or any user-supplied callable).

    Args:
        drive_id: Opaque Graph drive id. Resolve one from a URL / "me" /
            Teams channel with ``GraphUtils.resolve_drive_id``.
        token_provider: ``Callable[[], str]`` or ``Callable[[], Awaitable[str]]``
            returning a bearer token, invoked lazily (never in ``__init__``).
        base_url: Graph API root (default ``https://graph.microsoft.com/v1.0``).
        http_client: Reuse an existing ``httpx.AsyncClient``; the caller owns
            its lifecycle and ``close()`` does not close it. When omitted, one
            is created lazily on first use and closed by ``close()``.
        retry: Retry policy for transient failures; ``None`` uses the default
            ``RetryPolicy()`` profile.
        upload_chunk_size: Upload-session chunk size; must be a positive
            multiple of 320 KiB and strictly less than 60 MiB (Graph's
            per-request ceiling). Default 10 MiB.
        copy_timeout: Wall-clock budget for copy/move monitor polling, or
            ``None`` for no backend-imposed ceiling. When set, must be a
            positive float.
        base_path: Optional drive subfolder to scope every operation under.
            When set, all keys are addressed relative to this folder and keys
            returned by listing / ``to_key`` stay relative to it, so the backend
            behaves as if ``base_path`` were its root. Defaults to the drive root.
        client_options: Extra options passed through to the internal
            ``httpx.AsyncClient``. (When a future revision adds an explicit
            httpx-level constructor parameter, it takes precedence over a
            ``client_options`` key of the same name; the backend has no such
            parameter today, so this is passthrough only.)

    Raises:
        ValueError: For an empty ``drive_id``, a non-callable
            ``token_provider``, a non-string ``base_path``, an
            ``upload_chunk_size`` that is not a positive 320 KiB multiple
            below 60 MiB, or a non-positive ``copy_timeout``.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _GRAPH_CAPABILITIES

    def __init__(
        self,
        drive_id: str,
        *,
        token_provider: TokenProvider,
        base_url: str = _DEFAULT_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        retry: RetryPolicy | None = None,
        upload_chunk_size: int = _DEFAULT_UPLOAD_CHUNK_SIZE,
        copy_timeout: float | None = None,
        base_path: str = "",
        client_options: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(drive_id, str) or not drive_id.strip():
            raise ValueError("drive_id must be a non-empty string")
        if not callable(token_provider):
            raise ValueError("token_provider must be callable")
        if not isinstance(base_path, str):
            raise ValueError("base_path must be a string")
        if upload_chunk_size <= 0 or upload_chunk_size % _CHUNK_ALIGNMENT != 0:
            raise ValueError("upload_chunk_size must be a positive multiple of 320 KiB")
        if upload_chunk_size >= _MAX_UPLOAD_CHUNK_SIZE:
            raise ValueError("upload_chunk_size must be strictly less than 60 MiB (Graph's per-request ceiling)")
        if copy_timeout is not None and copy_timeout <= 0:
            raise ValueError("copy_timeout must be a positive float or None")

        self._drive_id = drive_id
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        # GR-058: scope every key under this drive subfolder. Normalised to a
        # slash-trimmed segment list so native_path / parentReference prepend it
        # and keys returned to callers stay base_path-relative.
        self._base_segments = [s for s in base_path.split("/") if s]
        self._http_client = http_client
        self._owned_client: httpx.AsyncClient | None = None
        self._retry = retry if retry is not None else RetryPolicy()
        self._upload_chunk_size = upload_chunk_size
        self._copy_timeout = copy_timeout
        self._client_options = client_options or {}
        # Most-recent range observation for this drive (SharePoint
        # range-fallback, GR-015). None = no ranged read yet, True = a 206
        # honoured Range, False = the drive ignored/rejected Range and the read
        # fell back to the spool. Range capability is a tenant/drive property,
        # so one tri-state per backend (one drive) covers every path — no
        # per-path set to grow or go stale — and a later honoured ranged read
        # self-heals the mark. get_file_info flags FileInfo while this is False.
        self._range_capable: bool | None = None
        # Upload-session URLs with a write mid-chunk-loop: close() aborts each
        # via best-effort DELETE (GR-051 upload-session-abort half).
        self._active_upload_sessions: set[str] = set()
        # In-flight copy/move monitor-poll tasks: close() cancels each
        # cooperatively (GR-051 poller-cancel half).
        self._pending_pollers: set[asyncio.Task[None]] = set()

    # region: properties

    @property
    def name(self) -> str:
        """Unique identifier for this backend type — ``"graph"``."""
        return BACKEND_NAME

    @property
    def capabilities(self) -> CapabilitySet:
        """Declared capabilities of this backend."""
        return self.CAPABILITIES

    @property
    def drive_id(self) -> str:
        """The immutable target drive id."""
        return self._drive_id

    @property
    def _client(self) -> httpx.AsyncClient:
        """Lazily-created (or caller-supplied) ``httpx.AsyncClient``."""
        if self._http_client is not None:
            return self._http_client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(**self._client_options)
        return self._owned_client

    # endregion

    # region: addressing (GR-009/010/036/036a)

    def native_path(self, path: str) -> str:
        """Return the Graph item-by-path metadata endpoint for ``path``.

        ``/drives/{drive_id}/root:{encoded_path}:`` with each segment
        percent-encoded. The empty key returns ``/drives/{drive_id}/root:``
        (Graph's drive-root form, no trailing colon delimiter). A configured
        ``base_path`` is prepended so every key is scoped under it.
        """
        root = f"/drives/{self._drive_id}/root:"
        segments = self._base_segments + [s for s in path.split("/") if s]
        if not segments:
            return root
        encoded = "/".join(_encode_segment(s) for s in segments)
        return f"{root}/{encoded}:"

    def to_key(self, native_path: str) -> str:
        """Strip the drive-root prefix/delimiter and decode back to a key.

        Inverse of ``native_path``: removes ``/drives/{drive_id}/root:`` and the
        trailing ``:`` delimiter, then percent-decodes each segment. Inputs
        without the prefix are returned unchanged; the drive root maps to ``""``.
        """
        prefix = f"/drives/{self._drive_id}/root:"
        if not native_path.startswith(prefix):
            return native_path
        rest = native_path[len(prefix) :]
        if rest.endswith(":"):
            rest = rest[:-1]
        rest = rest.lstrip("/")
        if not rest:
            return ""
        decoded = [unquote(seg) for seg in rest.split("/")]
        # GR-058: drop the configured base_path prefix so the key is returned
        # relative to the backend's scoped root (inverse of native_path).
        if self._base_segments == decoded[: len(self._base_segments)]:
            decoded = decoded[len(self._base_segments) :]
        return "/".join(decoded)

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` carrying the drive id and base URL."""
        from remote_store._resolution import ResolutionPlan as _RP

        return _RP(
            kind=self.name,
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={"drive_id": self._drive_id, "base_url": self._base_url},
        )

    # endregion

    # region: resource management (GR-037/051)

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the underlying ``httpx.AsyncClient`` (native-handle escape hatch).

        Raises:
            CapabilityNotSupported: For any type other than
                ``httpx.AsyncClient``.
        """
        if type_hint is httpx.AsyncClient:
            return self._client  # type: ignore[return-value]
        raise CapabilityNotSupported(
            f"Backend 'graph' does not expose native handle of type {type_hint.__name__}. "
            f"Supported: httpx.AsyncClient.",
            capability="unwrap",
            backend=self.name,
        )

    async def aclose(self) -> None:
        """Close the owned HTTP client, cancel pollers, and flush the auth cache.

        Safe to call multiple times. A caller-supplied ``http_client`` is left
        open — the caller owns it. Any in-flight copy/move monitor poller is
        cancelled cooperatively, and any upload session a ``write()`` left
        mid-chunk-loop is aborted via best-effort ``DELETE`` — every cleanup
        error is swallowed so ``close()`` never raises. The server-side copy /
        move continues (Graph monitor URLs have no cancel endpoint).
        """
        # GR-051: poller-cancel half + upload-session-abort half (mirrors GR-024).
        pollers = list(self._pending_pollers)
        for task in pollers:
            task.cancel()
        if pollers:
            # gather(return_exceptions) drains the cancelled tasks so neither a
            # CancelledError nor a "task was destroyed but pending" warning escapes
            # (filterwarnings=error would turn the latter into a failure).
            await asyncio.gather(*pollers, return_exceptions=True)
        self._pending_pollers.clear()
        for session_url in list(self._active_upload_sessions):
            await abort_upload_session(self._client, session_url, token_provider=self._token_provider)
        self._active_upload_sessions.clear()
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None
        flush = getattr(self._token_provider, "flush_cache", None)
        if callable(flush):
            flush()

    # endregion

    # region: data-plane reads (GR-012, GR-013, GR-031, GR-049)

    async def _get_item(self, path: str, *, scope: Literal["item", "probe"] = "item") -> dict[str, Any]:
        """Fetch the Graph ``driveItem`` body for *path* (one metadata GET).

        The single item-by-path metadata round trip shared by the read and
        type-probe operations. A missing item surfaces as ``NotFound`` (404
        ``itemNotFound`` at item scope, mapped by ``graph_send``); drive-scope,
        transport, and other failures map through the same primitive. The type
        probes pass ``scope="probe"`` so **every** 404 — including a
        drive-identity ``resourceNotFound`` — maps to ``NotFound`` and is
        suppressed to ``False`` instead of escaping as ``BackendUnavailable``.
        """
        response = await graph_send(
            self._client,
            "GET",
            self._item_url(path),
            token_provider=self._token_provider,
            path=path,
            scope=scope,
            retry=self._retry,
        )
        body: dict[str, Any] = response.json()
        return body

    async def _is_file_at(self, path: str) -> bool:
        """Fail-open file probe for the file-ancestor walk: ``True`` iff *path* is a file.

        A missing item or any transient metadata failure returns ``False`` so a
        confirming walk never masks the original error with a probe failure
        (mirrors the fail-open ``head_one`` contract in ``_flat_ns``).
        """
        try:
            item = await self._get_item(path)
        except RemoteStoreError:
            return False
        return is_file_item(item)

    async def _raise_if_existing_folder(self, path: str, *, verb: str) -> None:
        """Raise ``InvalidPath`` if *path* names an existing folder; else return.

        Live Graph rejects ``PUT /content`` to a folder with ``501 notSupported``
        and a move/copy onto a folder with a ``409`` that carries no folder facet,
        so neither reaches the body-based ``discriminate_write_conflict``. This
        confirming metadata GET (error-path only) restores the hierarchical-backend
        InvalidPath promise.
        """
        # ID-211 / BE-008: hierarchical backends own the folder-target InvalidPath promise.
        try:
            item = await self._get_item(path)
        except RemoteStoreError:
            return
        if is_folder_item(item):
            raise InvalidPath(f"Cannot {verb} — '{path}' names an existing folder", path=path, backend=self.name)

    async def _raise_if_file_ancestor(self, path: str) -> None:
        """Raise ``InvalidPath`` naming the file ancestor of *path*, if any; else return.

        Live Graph answers a write under a file ancestor with ``404`` and a
        move/copy under one with ``400 invalidRequest`` — neither the ``NotFound``
        nor the generic mapping the contract wants. This walk (error-path only)
        confirms an ancestor is a regular file and re-raises ``InvalidPath`` per
        the hierarchical-backend promise.

        Cost is O(depth) sequential metadata GETs, but only on an already-failed
        write/move/copy — never the happy path — so the deep-path penalty is a
        deliberate trade (mirrors the Azure HNS file-ancestor remap).
        """
        # ID-211 / ID-209: file-ancestor descent must surface as InvalidPath.
        await _acheck_no_file_ancestor(path, head_one=self._is_file_at, backend=self.name)

    async def _raise_move_copy_dest_error(self, response: httpx.Response, dst: str) -> None:
        """Raise the destination-conflict error for a move/copy *response*, if any.

        Live Graph signals a *dst* under a file ancestor with ``400 invalidRequest``
        and a *dst* onto an existing folder with a ``409`` carrying no folder facet,
        so neither the generic ``400`` mapping nor the body-based ``409``
        discriminator delivers the hierarchical-backend InvalidPath promise. A
        non-conflict response is left untouched for the caller to poll
        (``return_on`` surfaces only ``400`` / ``409`` here).
        """
        # ID-211 / BE-008: dst-is-folder and dst-under-file-ancestor -> InvalidPath.
        status = response.status_code
        if status == 400:
            await self._raise_if_file_ancestor(dst)
            body = response_json(response)
            code = (body.get("error") or {}).get("code") if isinstance(body, dict) else None
            raise classify_graph_error(status, code, path=dst, backend=self.name)
        if status == 409:
            await self._raise_if_existing_folder(dst, verb="move/copy to")
            raise discriminate_write_conflict(response_json(response), dst, backend=self.name)

    def _item_url(self, path: str) -> str:
        """Return the item-metadata endpoint for *path*.

        The drive root is the bare ``/root`` item; every other path uses the
        ``root:/{encoded}:`` path-addressing form. ``native_path('')`` yields the
        ``root:`` path-address form, which Graph rejects (400) for a standalone
        item GET, so the root is special-cased here exactly as in ``_children_url``.
        """
        native = self.native_path(path)
        if native == f"/drives/{self._drive_id}/root:":
            return f"{self._base_url}/drives/{self._drive_id}/root"
        return f"{self._base_url}{native}"

    def _note_range_incapable(self) -> None:
        """Record that this drive ignored/rejected ``Range`` (SharePoint range-fallback).

        Drive-scoped, not per-path: range capability is a tenant/drive property,
        so one mark per backend covers every path. ``get_file_info`` flags any
        ``FileInfo`` it returns with ``extra[graph.read.range_fallback]`` while
        the mark holds; a later honoured ranged read clears it via
        ``_note_range_capable``.
        """
        self._range_capable = False

    def _note_range_capable(self) -> None:
        """Record that this drive honoured a ranged read (``206``).

        Clears any prior range-incapable mark so the fallback flag tracks the
        most-recent observed behaviour rather than "ever fell back" (the
        self-heal that keeps the hint from going stale).
        """
        self._range_capable = True

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Stream file content from the pre-signed download URL.

        Fetches item metadata first (so the directory check happens before any
        byte is yielded), then streams the response body from
        ``@microsoft.graph.downloadUrl`` with no ``Range`` header (the URL is
        pre-signed, so no ``Authorization`` header is attached either). If the
        read is interrupted — the URL expires, or the connection drops mid-body —
        the stream re-fetches metadata for a fresh URL and resumes from the next
        unread byte with a ``Range`` request, provided the ``eTag`` is unchanged.

        Raises:
            NotFound: If the path does not exist.
            InvalidPath: If the path names a folder.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: If the download URL is missing, the file changed
                mid-read (``eTag`` mismatch), the pre-signed host returns a
                non-success status, or the download fails at the transport level
                (connect/read timeout, DNS, reset).
        """
        item = await self._get_item(path)
        if is_folder_item(item):
            raise InvalidPath(f"Cannot read — '{path}' is a folder", path=path, backend=self.name)
        async for chunk in stream_range(
            self._client,
            path,
            item,
            refetch=lambda: self._get_item(path),
            on_fallback=self._note_range_incapable,
            on_range_success=self._note_range_capable,
            retry=self._retry,
            backend=self.name,
        ):
            yield chunk

    async def _read_bytes(self, path: str, start: int, length: int | None = None) -> bytes:
        """Read the byte range ``[start, start+length)`` via the download URL.

        Internal range-read helper (not a public Store method): it services the
        non-seekable read pipeline and the spool fallback for ``read_seekable``.
        ``SEEKABLE_READ`` remains withheld. ``length=None`` reads to EOF. A start
        at or past EOF yields ``b""``; the download URL is pre-signed, so the
        range ``GET`` carries no ``Authorization`` header.

        Raises:
            NotFound: If the path does not exist.
            InvalidPath: If the path names a folder.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: As for ``read`` (missing URL, expiry, eTag change,
                host or transport failure).
            RemoteStoreError: A ``416`` provoked by a malformed (inverted) range.
        """
        item = await self._get_item(path)
        if is_folder_item(item):
            raise InvalidPath(f"Cannot read — '{path}' is a folder", path=path, backend=self.name)
        chunks = [
            chunk
            async for chunk in stream_range(
                self._client,
                path,
                item,
                start=start,
                length=length,
                refetch=lambda: self._get_item(path),
                on_fallback=self._note_range_incapable,
                on_range_success=self._note_range_capable,
                retry=self._retry,
                backend=self.name,
            )
        ]
        return b"".join(chunks)

    async def read_bytes(self, path: str) -> bytes:
        """Read full file content as bytes.

        Delegates to ``read`` so the directory check and not-found mapping live
        in one place.

        Raises:
            NotFound: If the path does not exist.
            InvalidPath: If the path names a folder.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: As for ``read`` (missing URL, expiry, eTag change,
                host or transport failure).
        """
        return b"".join([chunk async for chunk in self.read(path)])

    async def exists(self, path: str) -> bool:
        """Return ``True`` if a file or folder exists at *path*.

        Any 404 — including a drive-identity ``resourceNotFound`` — is
        suppressed to ``False``; never raises ``NotFound``. A misconfigured
        or deleted drive therefore probes as missing rather than raising;
        it surfaces on the first error-raising operation.

        Raises:
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On throttling, 5xx, or transport failure.
        """
        try:
            await self._get_item(path, scope="probe")
        except NotFound:
            return False
        return True

    async def is_file(self, path: str) -> bool:
        """Return ``True`` if *path* exists and carries the ``file`` facet.

        A missing item returns ``False`` (any 404 is suppressed, including a
        drive-identity ``resourceNotFound``).

        Raises:
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On throttling, 5xx, or transport failure.
        """
        try:
            item = await self._get_item(path, scope="probe")
        except NotFound:
            return False
        return is_file_item(item)

    async def is_folder(self, path: str) -> bool:
        """Return ``True`` if *path* exists and carries the ``folder`` facet.

        A missing item returns ``False`` (any 404 is suppressed, including a
        drive-identity ``resourceNotFound``). The drive root (``""``) carries
        the ``folder`` facet and reports ``True``.

        Raises:
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On throttling, 5xx, or transport failure.
        """
        try:
            item = await self._get_item(path, scope="probe")
        except NotFound:
            return False
        return is_folder_item(item)

    async def get_file_info(self, path: str) -> FileInfo:
        """Return file metadata mapped from the Graph ``driveItem`` body.

        ``file.hashes`` rides ``FileInfo.extra["graph.file.hashes"]``;
        ``metadata`` is ``None`` (user metadata is not declared) and ``digest``
        is left unset.

        Raises:
            NotFound: If the path does not exist.
            InvalidPath: If the path names a folder.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On throttling, 5xx, or transport failure.
        """
        item = await self._get_item(path)
        if is_folder_item(item):
            raise InvalidPath(f"Cannot get file info — '{path}' is a folder", path=path, backend=self.name)
        info = item_to_fileinfo(item, path)
        if self._range_capable is False:
            # A prior ranged read fell back because this drive ignored Range;
            # surface the drive-scoped signal on the FileInfo (GR-015). Cleared
            # by a later honoured ranged read.
            info.extra[RANGE_FALLBACK_FLAG] = True
        return info

    # endregion

    # region: data-plane listing (GR-014, GR-016)

    def _children_url(self, path: str) -> str:
        """Return the ``/children`` collection endpoint for the folder *path*.

        The drive root uses the bare ``/root/children`` form; every other folder
        uses the path-addressed ``root:/{encoded}:/children`` form.
        """
        native = self.native_path(path)
        if native == f"/drives/{self._drive_id}/root:":
            return f"{self._base_url}/drives/{self._drive_id}/root/children"
        return f"{self._base_url}{native}/children"

    async def _iter_child_items(self, path: str) -> AsyncIterator[dict[str, Any]]:
        """Yield each child ``driveItem`` under *path*, following pagination.

        A 404 on the *first* request (a missing folder, or a file path with no
        children collection) is suppressed to an empty iteration, so the public
        listing operations never raise ``NotFound`` for a bad path. A 404 raised
        mid-pagination (a later ``@odata.nextLink`` page) is a real error and
        propagates, rather than silently truncating the listing to the pages
        seen so far.
        """
        url = self._children_url(path)
        started = False
        try:
            async for page in iter_pages(
                self._client, url, token_provider=self._token_provider, path=path, retry=self._retry
            ):
                started = True
                value = page.get("value")
                if isinstance(value, list):
                    for raw in value:
                        if isinstance(raw, dict):
                            yield raw
        except NotFound:
            if started:
                raise
            return

    async def _walk_files(self, path: str, depth: int, limit: int | None) -> AsyncIterator[FileInfo]:
        """Yield files under *path*, descending while ``depth < limit``.

        ``limit is None`` means unbounded. A subfolder is entered only when the
        next level stays within the bound, so every yielded file sits at a depth
        ``<= limit`` — the inclusive depth boundary.
        """
        async for item in self._iter_child_items(path):
            name = item.get("name")
            if not isinstance(name, str):
                continue
            child = _child_key(path, name)
            if is_folder_item(item):
                if limit is None or depth < limit:
                    async for info in self._walk_files(child, depth + 1, limit):
                        yield info
            elif is_file_item(item):
                yield item_to_fileinfo(item, child)

    async def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Yield immediate files and folders under *path* in a single pass.

        Overrides the default (which would chain ``list_files`` + ``list_folders``
        and double the round-trips) to consume one ``/children`` response:
        ``folder``-faceted items become ``FolderEntry``, ``file``-faceted items
        become ``FileInfo``, in the order Graph returns them. A missing or file
        path yields nothing.

        Raises:
            PermissionDenied: If the token is rejected or lacks access
                (401/403), surfaced during iteration.
            BackendUnavailable: On throttling, 5xx, or transport failure,
                surfaced during iteration.
        """
        async for item in self._iter_child_items(path):
            name = item.get("name")
            if not isinstance(name, str):
                continue
            child = _child_key(path, name)
            if is_folder_item(item):
                yield FolderEntry(path=RemotePath(child), name=name)
            elif is_file_item(item):
                yield item_to_fileinfo(item, child)

    async def list_files(
        self, path: str, *, recursive: bool = False, max_depth: int | None = None
    ) -> AsyncIterator[FileInfo]:
        """List files under *path*.

        When ``max_depth`` is set it governs traversal depth and ``recursive`` is
        ignored; otherwise ``recursive=True`` walks the subtree unbounded and the
        default lists only immediate files. A missing or file path yields nothing.

        Raises:
            PermissionDenied: If the token is rejected or lacks access
                (401/403), surfaced during iteration.
            BackendUnavailable: On throttling, 5xx, or transport failure,
                surfaced during iteration.
        """
        if max_depth is not None:
            limit: int | None = max_depth
        elif recursive:
            limit = None
        else:
            limit = 0
        async for info in self._walk_files(path, 0, limit):
            yield info

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        """List immediate subfolders under *path*.

        A missing or file path yields nothing.

        Raises:
            PermissionDenied: If the token is rejected or lacks access
                (401/403), surfaced during iteration.
            BackendUnavailable: On throttling, 5xx, or transport failure,
                surfaced during iteration.
        """
        async for item in self._iter_child_items(path):
            name = item.get("name")
            if isinstance(name, str) and is_folder_item(item):
                yield FolderEntry(path=RemotePath(_child_key(path, name)), name=name)

    async def get_folder_info(self, path: str) -> FolderInfo:
        """Return aggregated folder metadata: recursive file count + total size.

        Validates the path first — a missing item raises ``NotFound`` and a file
        item raises ``InvalidPath``. ``file_count`` and ``total_size`` aggregate
        every file in the subtree; ``modified_at`` is the folder item's own
        timestamp.

        Raises:
            NotFound: If the path does not exist.
            InvalidPath: If the path names a file.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On throttling, 5xx, or transport failure.
        """
        item = await self._get_item(path)
        if not is_folder_item(item):
            raise InvalidPath(f"Cannot get folder info — '{path}' is a file", path=path, backend=self.name)
        file_count = 0
        total_size = 0
        async for info in self._walk_files(path, 0, None):
            file_count += 1
            total_size += info.size
        lmd = item.get("lastModifiedDateTime")
        modified_at = parse_graph_datetime(lmd) if isinstance(lmd, str) and lmd else None
        return FolderInfo(
            path=RemotePath.from_backend_path(path),
            file_count=file_count,
            total_size=total_size,
            modified_at=modified_at,
        )

    # endregion

    # region: data-plane writes (GR-018/019/039/040, BE-008)

    def _content_url(self, path: str) -> str:
        """Return the ``PUT /content`` endpoint for *path* (small-file write)."""
        return f"{self._base_url}{self.native_path(path)}/content"

    def _session_create_url(self, path: str) -> str:
        """Return the ``createUploadSession`` endpoint for *path* (large-file write)."""
        return f"{self._base_url}{self.native_path(path)}/createUploadSession"

    def _reject_user_metadata(self, metadata: Mapping[str, str] | None) -> None:
        """Re-raise the Store-layer user-metadata gate as defense-in-depth.

        The authoritative gate fires at the Store layer before the backend is
        entered; a non-empty ``metadata=`` only reaches here on a direct-backend
        call (the conformance suite invokes the backend without a Store
        wrapper). ``None`` / ``{}`` are no-ops per the empty-mapping carve-out.
        """
        # GR-018 metadata= gate (WR-010/WR-011); USER_METADATA is not declared.
        if metadata:
            raise CapabilityNotSupported(
                "Backend 'graph' does not support user metadata (USER_METADATA is not declared)",
                capability="USER_METADATA",
                backend=self.name,
            )

    def _require_writable_key(self, path: str) -> None:
        """Reject a write at the drive root — a file needs a name (path validity)."""
        if not path.strip("/"):
            raise InvalidPath(f"Cannot write to the drive root: {path!r}", path=path, backend=self.name)

    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write a file, creating intermediate folders implicitly.

        Content ``<= 4 MiB`` uses ``PUT /content``; larger content uploads via a
        chunked session. An ``AsyncIterator`` of unknown length is spooled to
        size it first (the session ``Content-Range`` needs a known total). The
        returned ``WriteResult`` is ``source="native"``, populated from the
        ``driveItem`` Graph returns. ``overwrite`` maps to Graph's
        ``@microsoft.graph.conflictBehavior`` (``replace`` vs ``fail``).

        Raises:
            AlreadyExists: If the file exists and ``overwrite=False``.
            InvalidPath: If the path names the drive root, an existing folder,
                or descends through a file ancestor.
            CapabilityNotSupported: If a non-empty ``metadata=`` reaches the
                backend directly (``USER_METADATA`` is not declared).
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On 5xx / throttling / transport failure, or a
                Graph contract gap (missing ``uploadUrl`` / ``nextExpectedRanges``).
            ResourceLocked: If the item is locked mid-session. The session
                stays valid server-side, but its credentialed URL is not
                exposed in the exception.
        """
        # GR-018 (small PUT) / GR-019 (upload session) / GR-039 (auto-mkdir);
        # native WriteResult per WR-004; 409 discrimination per BE-008 / ID-209.
        self._reject_user_metadata(metadata)
        self._require_writable_key(path)
        reader, total = await spool_content(content, path=path)
        try:
            if total <= _SMALL_FILE_MAX_SIZE:
                return await self._write_small(path, reader.read(), overwrite=overwrite, metadata=metadata)
            item = await upload_session(
                self._client,
                self._session_create_url(path),
                reader,
                total,
                path=path,
                token_provider=self._token_provider,
                chunk_size=self._upload_chunk_size,
                overwrite=overwrite,
                retry=self._retry,
                on_session_open=self._active_upload_sessions.add,
                on_session_close=self._active_upload_sessions.discard,
                backend=self.name,
            )
            return item_to_write_result(item, path, total, metadata)
        finally:
            reader.close()

    async def _write_small(
        self, path: str, data: bytes, *, overwrite: bool, metadata: Mapping[str, str] | None
    ) -> WriteResult:
        """``PUT /content`` for content already materialised in memory.

        The body is in-memory bytes (replayable), so the request rides the shared
        retry loop safely. A ``409`` is discriminated (folder / ancestor-file /
        already-exists) rather than mapped to a flat ``AlreadyExists``.
        """
        behavior = "replace" if overwrite else "fail"
        url = f"{self._content_url(path)}?@microsoft.graph.conflictBehavior={behavior}"
        response = await graph_send(
            self._client,
            "PUT",
            url,
            token_provider=self._token_provider,
            path=path,
            retry=self._retry,
            return_on=frozenset({404, 409, 501}),
            headers={"Content-Type": "application/octet-stream"},
            content=data,
        )
        status = response.status_code
        if status == 501:
            # PUT /content to a folder is the only 501 (notSupported) case — the
            # target is an existing folder. The hierarchical-backend contract wants
            # InvalidPath, not the generic mapping (ID-211, BE-008).
            raise InvalidPath(f"Cannot write — '{path}' names an existing folder", path=path, backend=self.name)
        if status == 404:
            # Graph auto-creates missing intermediate folders, so a write 404 is
            # almost always a regular file blocking an ancestor segment — name it as
            # InvalidPath (ID-209). If the walk finds no file ancestor, route the 404
            # back through the standard classifier so a drive-scope resourceNotFound
            # keeps its BackendUnavailable mapping (GR-031) instead of flattening to
            # NotFound.
            await self._raise_if_file_ancestor(path)
            body = response_json(response)
            code = (body.get("error") or {}).get("code") if isinstance(body, dict) else None
            raise classify_graph_error(status, code, path=path, backend=self.name)
        if status == 409:
            raise discriminate_write_conflict(response_json(response), path, backend=self.name)
        return item_to_write_result(response.json(), path, len(data), metadata)

    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Atomic write — delegates to ``write``.

        Graph's own write paths already provide the no-partial-content guarantee
        (``PUT /content`` is service-atomic; an upload session commits only on the
        final chunk), so no client-side temp-rename is taken. The ``WriteResult``
        shape, the ``metadata=`` gate, and the raised exceptions are inherited
        verbatim from ``write``.
        """
        return await self.write(path, content, overwrite=overwrite, metadata=metadata)

    # endregion

    # region: data-plane mutate (GR-025/027/041/042/043/044/056)

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file (Graph moves it to the recycle bin).

        Fetches the item first so a folder is rejected before any ``DELETE`` is
        issued (a bare ``DELETE`` on a folder would remove the folder and its
        contents). A missing item is ``NotFound`` unless ``missing_ok``.

        Raises:
            NotFound: If the file does not exist and ``missing_ok`` is ``False``.
            InvalidPath: If the path names a folder (use ``delete_folder``).
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On throttling, 5xx, or transport failure.
        """
        # GR-041: type-check via one GET, then DELETE the resolved item.
        try:
            item = await self._get_item(path)
        except NotFound:
            if missing_ok:
                return
            raise
        if is_folder_item(item):
            raise InvalidPath(f"Cannot delete — '{path}' is a folder", path=path, backend=self.name)
        await graph_send(
            self._client,
            "DELETE",
            self._item_url(path),
            token_provider=self._token_provider,
            path=path,
            retry=self._retry,
        )

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder, optionally requiring it to be empty.

        ``recursive=True`` is a single ``DELETE`` — Graph removes the folder and
        all contents atomically server-side. ``recursive=False`` first checks the
        folder is empty (via the item's ``folder.childCount``, falling back to a
        ``/children`` probe when the count is absent) and raises
        ``DirectoryNotEmpty`` if not.

        Raises:
            NotFound: If the folder does not exist and ``missing_ok`` is ``False``.
            InvalidPath: If the path names a file.
            DirectoryNotEmpty: If non-empty and ``recursive`` is ``False``.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On throttling, 5xx, or transport failure.
        """
        # GR-042 (recursive) / GR-043 (non-recursive empty-check).
        try:
            item = await self._get_item(path)
        except NotFound:
            if missing_ok:
                return
            raise
        if not is_folder_item(item):
            raise InvalidPath(f"Cannot delete folder — '{path}' is a file", path=path, backend=self.name)
        if not recursive and await self._folder_is_nonempty(path, item):
            raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)
        await graph_send(
            self._client,
            "DELETE",
            self._item_url(path),
            token_provider=self._token_provider,
            path=path,
            retry=self._retry,
        )

    async def _folder_is_nonempty(self, path: str, item: dict[str, Any]) -> bool:
        """Return ``True`` if the folder *item* has at least one child.

        Prefers the ``folder.childCount`` Graph returns on the metadata item; when
        absent (not an int), falls back to a single ``/children?$top=1`` probe — one
        bounded request, not a full default page (the folder already type-checked,
        so the probe never 404s).
        """
        child_count = (item.get("folder") or {}).get("childCount")
        if isinstance(child_count, int):
            return child_count > 0
        response = await graph_send(
            self._client,
            "GET",
            f"{self._children_url(path)}?$top=1",
            token_provider=self._token_provider,
            path=path,
            retry=self._retry,
        )
        body = response.json()
        value = body.get("value") if isinstance(body, dict) else None
        return bool(value)

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file, awaiting the async monitor to completion.

        Graph answers ``POST copy`` with ``202 Accepted`` and a ``Location``
        monitor URL; this polls it to a terminal state (bounded by
        ``copy_timeout``). ``src == dst`` short-circuits after a single
        existence-confirming ``GET``. A destination conflict surfaces as
        ``AlreadyExists`` (or ``InvalidPath`` for a folder / file-ancestor target)
        when ``overwrite`` is ``False``.

        Raises:
            NotFound: If ``src`` does not exist.
            InvalidPath: If ``src`` names a folder, or ``dst`` names an existing
                folder or descends through a file ancestor.
            AlreadyExists: If ``dst`` exists, ``src != dst``, and ``overwrite`` is
                ``False``.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On a ``202`` without a ``Location`` monitor URL, a
                ``copy_timeout`` expiry, or a transient/5xx failure.
        """
        # GR-025 (POST copy -> 202 monitor), GR-044 (self-copy short-circuit),
        # GR-056 (cross-drive is vacuous — parentReference resolves against the one
        # configured drive). BE-008 409 discrimination applies to the destination.
        # conflictBehavior is a QUERY parameter on the copy action (live-verified:
        # a body field is ignored, so overwrite=True 409'd until moved here).
        if await self._short_circuit_self_op(src, dst):
            return
        behavior = "replace" if overwrite else "fail"
        response = await graph_send(
            self._client,
            "POST",
            f"{self._base_url}{self.native_path(src)}/copy?@microsoft.graph.conflictBehavior={behavior}",
            token_provider=self._token_provider,
            path=src,
            retry=self._retry,
            return_on=frozenset({400, 409}),
            json=self._move_copy_body(dst),
        )
        await self._raise_move_copy_dest_error(response, dst)
        await self._await_async_operation(response, path=dst)

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file, awaiting the monitor when Graph goes async.

        Graph answers ``PATCH driveItem`` synchronously in most cases (``200``);
        a large-item move may return ``202`` with a monitor URL (the async trigger
        is item size / server-side replication, not crossing folders), which is
        polled to completion exactly as ``copy`` does. ``src == dst``
        short-circuits after one ``GET``. Item identity (id / eTag / property
        bag) is preserved by Graph; the backend issues no compensating writes.

        Raises:
            NotFound: If ``src`` does not exist.
            InvalidPath: If ``src`` names a folder, or ``dst`` names an existing
                folder or descends through a file ancestor.
            AlreadyExists: If ``dst`` exists, ``src != dst``, and ``overwrite`` is
                ``False``.
            PermissionDenied: If the token is rejected or lacks access to the
                item (401/403).
            BackendUnavailable: On a ``202`` without a ``Location`` monitor URL, a
                ``copy_timeout`` expiry, or a transient/5xx failure.
        """
        # GR-027 (PATCH -> sync 200 or 202 monitor), GR-044 (self-move),
        # GR-056 (cross-drive vacuous). BE-008 409 discrimination on the dest.
        if await self._short_circuit_self_op(src, dst):
            return
        behavior = "replace" if overwrite else "fail"
        response = await graph_send(
            self._client,
            "PATCH",
            f"{self._base_url}{self.native_path(src)}?@microsoft.graph.conflictBehavior={behavior}",
            token_provider=self._token_provider,
            path=src,
            retry=self._retry,
            return_on=frozenset({400, 409}),
            json=self._move_copy_body(dst),
        )
        await self._raise_move_copy_dest_error(response, dst)
        await self._await_async_operation(response, path=dst)

    async def _short_circuit_self_op(self, src: str, dst: str) -> bool:
        """Validate *src* for a move/copy and report whether it is a self-op no-op.

        Issues the single existence ``GET`` the self-op contract requires: a
        missing ``src`` is ``NotFound`` and a folder ``src`` is ``InvalidPath``,
        both raised before any mutation. Returns ``True`` when *src* and *dst*
        address the same item (the caller then short-circuits after this one
        GET), ``False`` otherwise. Equality is over the normalised
        ``native_path`` forms, not the raw strings, so a direct backend call
        like ``copy("/a.txt", "a.txt")`` is a no-op rather than a real request
        Graph would 409.
        """
        # BE-019 / BE-021 self-op preconditions; GR-044 single-GET short-circuit.
        src_item = await self._get_item(src)
        if is_folder_item(src_item):
            raise InvalidPath(f"Cannot move/copy — '{src}' is a folder", path=src, backend=self.name)
        return self.native_path(src) == self.native_path(dst)

    def _move_copy_body(self, dst: str) -> dict[str, Any]:
        """Build the ``parentReference`` + ``name`` body for a move / copy to *dst*.

        ``parentReference`` names the configured drive and the destination's
        parent folder by path — there is no syntax to address a different drive,
        so a cross-drive move/copy is structurally impossible. Both ``copy`` (POST
        action) and ``move`` (PATCH) carry ``@microsoft.graph.conflictBehavior`` as
        a query parameter, not in this body (live-verified for the copy action).
        """
        # GR-056: cross-drive is vacuous — parentReference binds to the one drive.
        parent, name = _split_parent(dst)
        return {
            "parentReference": {"driveId": self._drive_id, "path": self._parent_ref_path(parent)},
            "name": name,
        }

    def _parent_ref_path(self, parent_key: str) -> str:
        """Return the ``parentReference.path`` for the folder key *parent_key*.

        ``/drives/{drive_id}/root:`` for the drive root, otherwise
        ``/drives/{drive_id}/root:/{encoded_parent}`` (no trailing colon — the
        ``parentReference`` path form, unlike the item-address form).
        """
        root = f"/drives/{self._drive_id}/root:"
        segments = self._base_segments + [s for s in parent_key.split("/") if s]
        if not segments:
            return root
        encoded = "/".join(_encode_segment(s) for s in segments)
        return f"{root}/{encoded}"

    async def _await_async_operation(self, response: httpx.Response, *, path: str) -> None:
        """Drive a mutate response to completion: poll the monitor if async.

        A synchronous success (``200`` for a sync move) returns immediately. A
        ``202 Accepted`` (always for copy, sometimes for move) carries a
        ``Location`` monitor URL that is polled to a terminal state in a tracked
        task, so ``close()`` can cancel an in-flight poller. A ``202`` without a
        ``Location`` is a Graph contract gap.
        """
        # GR-051: the poller task is tracked so close() can cancel it mid-flight.
        if response.status_code != 202:
            return None  # explicit so it does not mix with the `return await` below
        monitor_url = response.headers.get("location")
        if not monitor_url:
            raise BackendUnavailable(
                f"Graph returned 202 Accepted without a Location monitor URL: {path}", path=path, backend=self.name
            )
        task: asyncio.Task[None] = asyncio.ensure_future(
            poll_monitor(monitor_url, self._client, timeout=self._copy_timeout, path=path, backend=self.name)
        )
        self._pending_pollers.add(task)
        try:
            # `return await` (not a bare `await task` statement) keeps the await as
            # part of a return — poll_monitor yields None, and the finally still
            # runs the discard before this method returns or unwinds on cancel.
            return await task
        finally:
            self._pending_pollers.discard(task)

    # endregion

    def __repr__(self) -> str:
        # GR-035: no token or secret is stored on the backend, so repr is
        # structurally credential-safe; the token_provider's own repr governs.
        return f"GraphBackend(drive_id={self._drive_id!r}, base_url={self._base_url!r})"
