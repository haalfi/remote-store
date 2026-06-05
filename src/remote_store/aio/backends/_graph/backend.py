"""``GraphBackend`` — the ``AsyncBackend`` implementation for Microsoft Graph.

This module lands the public surface and request/error foundation:
construction and validation, the capability declaration, path addressing and
segment encoding, the native-client escape hatch, the ``close()`` baseline, and
credential-safe ``repr``. The data-plane operation bodies (read / write /
delete / list / move / copy) are stubbed here and filled in by later steps;
they raise ``NotImplementedError`` until then.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, TypeVar
from urllib.parse import quote, unquote

import httpx

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy
from remote_store._errors import BackendUnavailable, CapabilityNotSupported, InvalidPath, NotFound
from remote_store._models import FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio.backends._graph.http import BACKEND_NAME, graph_send, iter_pages
from remote_store.aio.backends._graph.items import (
    download_url,
    is_file_item,
    is_folder_item,
    item_to_fileinfo,
    parse_graph_datetime,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

    from remote_store._models import FileInfo, WriteResult
    from remote_store._resolution import ResolutionPlan
    from remote_store.aio._types import AsyncWritableContent

    TokenProvider = Callable[[], str] | Callable[[], Awaitable[str]]

T = TypeVar("T")

_DEFAULT_BASE_URL = "https://graph.microsoft.com/v1.0"
_CHUNK_ALIGNMENT = 320 * 1024  # Graph's documented upload-chunk alignment (GR-020)
_DEFAULT_UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MiB (GR-001)

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

_STUB_MSG = "GraphBackend.{op} is not implemented yet"


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
            multiple of 320 KiB. Default 10 MiB.
        copy_timeout: Wall-clock budget for copy/move monitor polling, or
            ``None`` for no backend-imposed ceiling. When set, must be a
            positive float.
        client_options: Extra options passed through to the internal
            ``httpx.AsyncClient``. (When a future revision adds an explicit
            httpx-level constructor parameter, it takes precedence over a
            ``client_options`` key of the same name; the backend has no such
            parameter today, so this is passthrough only.)

    Raises:
        ValueError: For an empty ``drive_id``, a non-callable
            ``token_provider``, a non-aligned ``upload_chunk_size``, or a
            non-positive ``copy_timeout``.
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
        client_options: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(drive_id, str) or not drive_id.strip():
            raise ValueError("drive_id must be a non-empty string")
        if not callable(token_provider):
            raise ValueError("token_provider must be callable")
        if upload_chunk_size <= 0 or upload_chunk_size % _CHUNK_ALIGNMENT != 0:
            raise ValueError("upload_chunk_size must be a positive multiple of 320 KiB")
        if copy_timeout is not None and copy_timeout <= 0:
            raise ValueError("copy_timeout must be a positive float or None")

        self._drive_id = drive_id
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client
        self._owned_client: httpx.AsyncClient | None = None
        self._retry = retry if retry is not None else RetryPolicy()
        self._upload_chunk_size = upload_chunk_size
        self._copy_timeout = copy_timeout
        self._client_options = client_options or {}

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
        (Graph's drive-root form, no trailing colon delimiter).
        """
        root = f"/drives/{self._drive_id}/root:"
        segments = [s for s in path.split("/") if s]
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
        return "/".join(unquote(seg) for seg in rest.split("/"))

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
        """Close the owned HTTP client and flush the auth cache.

        Safe to call multiple times. A caller-supplied ``http_client`` is left
        open — the caller owns it. The monitor-poller-cancel and
        upload-session-abort behaviours are layered on by later steps, once
        those subsystems exist.
        """
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None
        flush = getattr(self._token_provider, "flush_cache", None)
        if callable(flush):
            flush()

    # endregion

    # region: data-plane reads (GR-012, GR-013, GR-031, GR-049)

    async def _get_item(self, path: str) -> dict[str, Any]:
        """Fetch the Graph ``driveItem`` body for *path* (one metadata GET).

        The single item-by-path metadata round trip shared by the read and
        type-probe operations. A missing item surfaces as ``NotFound`` (404
        ``itemNotFound`` at item scope, mapped by ``graph_send``); drive-scope,
        transport, and other failures map through the same primitive.
        """
        response = await graph_send(
            self._client, "GET", self._item_url(path), token_provider=self._token_provider, path=path, scope="item"
        )
        body: dict[str, Any] = response.json()
        return body

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

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Stream file content from the pre-signed download URL.

        Fetches item metadata first (so the directory check happens before any
        byte is yielded), then streams the response body from
        ``@microsoft.graph.downloadUrl``. The download URL is pre-signed, so no
        ``Authorization`` header is attached.

        Raises:
            NotFound: If the path does not exist.
            InvalidPath: If the path names a folder.
            BackendUnavailable: If the download URL is missing, the pre-signed
                host returns a non-success status, or the download fails at the
                transport level (connect/read timeout, DNS, reset).
        """
        item = await self._get_item(path)
        if is_folder_item(item):
            raise InvalidPath(f"Cannot read — '{path}' is a folder", path=path, backend=self.name)
        url = download_url(item)
        if url is None:
            # A file item should always carry a download URL (even 0-byte files);
            # its absence is a Graph contract gap, not a silent empty read.
            raise BackendUnavailable(f"Graph returned no download URL for: {path}", path=path, backend=self.name)
        # The metadata GET rides graph_send, but this body stream goes direct to
        # the pre-signed host, so transport errors are mapped here per GR-033.
        try:
            async with self._client.stream("GET", url) as response:
                if not response.is_success:
                    await response.aread()
                    raise BackendUnavailable(
                        f"Graph download failed ({response.status_code}): {path}", path=path, backend=self.name
                    )
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.TransportError as exc:
            raise BackendUnavailable(f"Graph download transport error: {exc}", path=path, backend=self.name) from None

    async def read_bytes(self, path: str) -> bytes:
        """Read full file content as bytes.

        Delegates to ``read`` so the directory check and not-found mapping live
        in one place.

        Raises:
            NotFound: If the path does not exist.
            InvalidPath: If the path names a folder.
        """
        return b"".join([chunk async for chunk in self.read(path)])

    async def exists(self, path: str) -> bool:
        """Return ``True`` if a file or folder exists at *path*.

        A 404 ``itemNotFound`` is suppressed to ``False``; never raises
        ``NotFound``.
        """
        try:
            await self._get_item(path)
        except NotFound:
            return False
        return True

    async def is_file(self, path: str) -> bool:
        """Return ``True`` if *path* exists and carries the ``file`` facet.

        A missing item returns ``False`` (the 404 is suppressed).
        """
        try:
            item = await self._get_item(path)
        except NotFound:
            return False
        return is_file_item(item)

    async def is_folder(self, path: str) -> bool:
        """Return ``True`` if *path* exists and carries the ``folder`` facet.

        A missing item returns ``False`` (the 404 is suppressed). The drive root
        (``""``) carries the ``folder`` facet and reports ``True``.
        """
        try:
            item = await self._get_item(path)
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
        """
        item = await self._get_item(path)
        if is_folder_item(item):
            raise InvalidPath(f"Cannot get file info — '{path}' is a folder", path=path, backend=self.name)
        return item_to_fileinfo(item, path)

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

        A 404 at *path* (a missing folder, or a file path with no children
        collection) is suppressed to an empty iteration, so the public listing
        operations never raise ``NotFound`` for a bad path.
        """
        url = self._children_url(path)
        try:
            async for page in iter_pages(self._client, url, token_provider=self._token_provider, path=path):
                value = page.get("value")
                if isinstance(value, list):
                    for raw in value:
                        if isinstance(raw, dict):
                            yield raw
        except NotFound:
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

    # region: data-plane operations — stubbed (GR-WRITE / GR-MUTATE)

    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write a file. Not implemented yet (write path)."""
        raise NotImplementedError(_STUB_MSG.format(op="write"))

    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Atomic write. Not implemented yet (write path)."""
        raise NotImplementedError(_STUB_MSG.format(op="write_atomic"))

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file. Not implemented yet (mutate path)."""
        raise NotImplementedError(_STUB_MSG.format(op="delete"))

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder. Not implemented yet (mutate path)."""
        raise NotImplementedError(_STUB_MSG.format(op="delete_folder"))

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename. Not implemented yet (mutate path)."""
        raise NotImplementedError(_STUB_MSG.format(op="move"))

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy. Not implemented yet (mutate path)."""
        raise NotImplementedError(_STUB_MSG.format(op="copy"))

    # endregion

    def __repr__(self) -> str:
        # GR-035: no token or secret is stored on the backend, so repr is
        # structurally credential-safe; the token_provider's own repr governs.
        return f"GraphBackend(drive_id={self._drive_id!r}, base_url={self._base_url!r})"
